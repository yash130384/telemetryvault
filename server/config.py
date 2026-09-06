import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
load_dotenv(BASE_DIR / ".env")

def _get_default_database_url() -> str:
    agy_path = BASE_DIR / "AGY.md"
    if agy_path.exists():
        try:
            content = agy_path.read_text()
            m = re.search(r"postgresql://teleuser:([^@\s]+)@127\.0\.0\.1:5432/telemetryvault", content)
            if m:
                return m.group(0)
        except Exception:
            pass
    return "postgresql://teleuser:teleuser@127.0.0.1:5432/telemetryvault"

DATABASE_URL = os.environ.get("DATABASE_URL") or _get_default_database_url()
UDP_HOST = os.environ.get("UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.environ.get("UDP_PORT", 20000))
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", 8000))
SESSION_IDLE_TIMEOUT = float(os.environ.get("SESSION_IDLE_TIMEOUT", 30.0))
