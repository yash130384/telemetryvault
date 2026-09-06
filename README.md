# ⚡ TelemetryVault

A high-performance web application and telemetry vault for recording, analyzing, and comparing **Assetto Corsa Competizione (ACC)** race telemetry. Built specifically for Raspberry Pi (Debian ARM64) with a dark "racing-engineer" dashboard aesthetic.

---

## 🏎️ Features

- **ACC UDP Telemetry Ingestion**: Listens on configurable UDP port (`20000` default) for real-time JSON frames (`acs_` broadcast format).
- **Session Auto-Management**:
  - Auto-starts a new session on the first incoming telemetry packet.
  - Automatically finalizes and closes sessions after ~30s of silence.
  - Automatically detects lap completions, lap times, sector data, and session best laps.
- **High-Throughput Storage**: Non-blocking asynchronous batch ingestion into PostgreSQL via `asyncpg` binary protocol.
- **Racing Engineer Dashboard (Renningenieur UI)**:
  - **Interactive Track Map**: Rendered on HTML5 2D Canvas with 4 heatmap coloration modes (*Speed*, *Throttle*, *Brake*, *Gear*), start/finish line marker, and dynamic car position cursor.
  - **Live Gauges HUD**: Digital speedometer, large gear indicator, progressive LED shift lights tachometer, throttle/brake pedal bars, steering angle, and 4-wheel tire HUD (*core temps, pressures, brake disc heat with dynamic thermal coloring*).
  - **Synchronized Time-Series Charts**: Multi-panel telemetry traces (*Speed, Throttle/Brake, Gear/RPM, Steering/Lat-G, Tire Temps*) with synchronized hover crosshairs.
  - **Interactive Replay & Scrubber**: Playback at 1x, 2x, 5x speed or scrub through any frame along the lap.
  - **Lap Comparison Suite (Delta-T)**: Overlays any two laps (e.g. *Selected Lap vs Best Lap*) normalized by distance, displaying exact time deltas, speed deltas, and pedal input comparison.
  - **Real-Time Live Streaming**: WebSocket connection (`/ws/live`) to monitor live laps from the pit wall in real time.

---

## 🛠️ Tech Stack & Constraints

- **Host**: Raspberry Pi, Debian 13 (trixie) ARM64, Python 3.11/3.13.
- **Backend**: Python 3, FastAPI, Uvicorn, asyncpg (no Docker).
- **Database**: PostgreSQL 17 (`telemetryvault`).
- **Frontend**: Plain HTML5, CSS3, ES modules, Chart.js, HTML5 2D Canvas (no npm/webpack build step, ultra-lightweight).

---

## 🚀 Quick Start

### 1. Start the TelemetryVault Server

Run the startup script:

```bash
bash run.sh
```

This will:
1. Ensure the Python virtual environment (`.venv`) is activated.
2. Verify PostgreSQL connectivity and apply schema migrations idempotently.
3. Start the FastAPI HTTP server on `http://0.0.0.0:8000`.
4. Start the UDP telemetry listener on `0.0.0.0:20000`.

Open your browser at: **[http://localhost:8000](http://localhost:8000)**

---

### 2. Inject Sample Telemetry (Simulator)

TelemetryVault includes a realistic ACC physics simulator (`simulator.py`) that models hotlaps around Circuit de Spa-Francorchamps:

```bash
# Fast ingestion of 2 complete hotlaps (~2 min of driving data in ~3 seconds)
.venv/bin/python simulator.py --fast --laps 2

# Or simulate in real time (20 Hz UDP packets) to watch live HUD gauges:
.venv/bin/python simulator.py --hz 20 --speed-multiplier 1.0 --laps 2
```

Command options:
- `--laps <N>`: Number of laps to simulate (default: 2).
- `--fast`: Ingests telemetry immediately without real-time delays.
- `--speed-multiplier <N>`: Run real-time simulation at 2x, 5x, etc.
- `--car <name>`: Car model name (default: "Ferrari 296 GT3").
- `--driver <name>`: Driver name.
- `--port <N>`: Target UDP port (default: 20000).

---

## ⚙️ Configuration

Environment variables can be configured in `.env` or passed via system environment:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection URI | `postgresql://teleuser:***@127.0.0.1:5432/telemetryvault` |
| `UDP_HOST` | Host interface for UDP listener | `0.0.0.0` |
| `UDP_PORT` | Port for ACC UDP broadcast | `20000` |
| `HTTP_HOST` | Host interface for FastAPI web server | `0.0.0.0` |
| `HTTP_PORT` | Port for FastAPI web server | `8000` |
| `SESSION_IDLE_TIMEOUT` | Idle seconds before closing session | `30.0` |

---

## 📂 Project Structure

```
telemetryvault/
├── migrations/
│   └── 001_initial_schema.sql  # Idempotent PostgreSQL schema migration
├── server/
│   ├── api.py                  # REST API routes & comparison algorithms
│   ├── config.py               # Environment & configuration loader
│   ├── db.py                   # Asyncpg connection pool & migration runner
│   ├── ingest.py               # UDP listener, frame parser & session manager
│   ├── main.py                 # FastAPI application lifespan & static mounts
│   └── models.py               # Pydantic data models
├── web/
│   ├── index.html              # Sessions overview & filter dashboard
│   ├── analysis.html           # Racing engineer analysis suite
│   ├── css/
│   │   └── style.css           # Dark race engineering theme
│   └── js/
│       ├── api.js              # REST API client
│       ├── app.js              # Overview page controller
│       ├── analysis.js         # Analysis suite & playback controller
│       ├── charts.js           # Multi-panel Chart.js telemetry traces
│       ├── gauges.js           # Live tachometer, pedals & tire HUD
│       ├── trackmap.js         # Canvas trackmap renderer with heatmaps
│       └── vendor/
│           └── chart.umd.min.js# Offline Chart.js bundle
├── simulator.py                # ACC UDP hotlap telemetry simulator
├── run.sh                      # One-command server startup script
├── requirements.txt            # Python dependencies
└── README.md                   # Documentation
```

---

## 🏁 Connecting Real ACC Game Telemetry

To stream telemetry from Assetto Corsa Competizione to TelemetryVault:
1. In ACC, enable telemetry UDP broadcasting or configure your telemetry bridge (e.g. `Out Acc Apps` / `acs_` SDK) to broadcast to the Raspberry Pi's IP address on UDP port `20000`.
2. As soon as you leave the pit garage, TelemetryVault automatically detects the vehicle, track, driver, and begins recording.
3. View real-time telemetry live at `http://<raspberry-pi-ip>:8000/`.
