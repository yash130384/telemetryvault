import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from server.config import UDP_HOST, UDP_PORT, BASE_DIR, ACC_ENABLED
from server.db import init_db, close_db
from server.ingest import telemetry_manager, TelemetryUDPProtocol
from server.acc_client import acc_client
from server.api import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("telemetryvault")

udp_transport = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global udp_transport
    logger.info("Starting TelemetryVault service...")
    
    # Initialize DB pool and run migrations
    await init_db()
    
    # Start ingestion background tasks
    await telemetry_manager.start()

    # Start UDP listener
    loop = asyncio.get_running_loop()
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: TelemetryUDPProtocol(telemetry_manager),
            local_addr=(UDP_HOST, UDP_PORT)
        )
        udp_transport = transport
        logger.info(f"UDP Telemetry listener started successfully on {UDP_HOST}:{UDP_PORT}")
    except Exception as e:
        logger.error(f"Failed to bind UDP port {UDP_PORT}: {e}", exc_info=True)

    # Start native ACC UDP broadcasting client if enabled
    if ACC_ENABLED:
        try:
            await acc_client.start()
        except Exception as e:
            logger.error(f"Failed to start ACC client: {e}", exc_info=True)

    yield

    logger.info("Shutting down TelemetryVault...")
    if ACC_ENABLED:
        try:
            await acc_client.stop()
        except Exception as e:
            logger.error(f"Error stopping ACC client: {e}", exc_info=True)

    if udp_transport:
        udp_transport.close()
    await telemetry_manager.stop()
    await close_db()
    logger.info("Shutdown complete.")

app = FastAPI(title="TelemetryVault", lifespan=lifespan)

# Include REST API
app.include_router(api_router)

# WebSocket endpoint for real-time live telemetry
@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    telemetry_manager.register_client(websocket)
    # Send current status immediately upon connect
    try:
        if telemetry_manager.latest_frame:
            await websocket.send_json(telemetry_manager.latest_frame)
        while True:
            # Keep-alive receive loop
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        telemetry_manager.unregister_client(websocket)

# Web Static & HTML Routes
web_dir = BASE_DIR / "web"

@app.get("/")
async def serve_index():
    return FileResponse(web_dir / "index.html")

@app.get("/analysis")
async def serve_analysis():
    return FileResponse(web_dir / "analysis.html")

app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="root_static")
