# TelemetryVault

Web app for recording and analyzing Assetto Corsa Competizione (ACC) telemetry.

## Hard constraints (do not deviate)
- Runs on this machine: Raspberry Pi, Debian 13 (trixie), ARM64, Python 3.11.
- Backend: **Python / FastAPI** + **asyncpg**. No Docker (not installed on this Pi).
- Frontend: plain HTML/CSS/ES modules served by FastAPI. No heavy JS build tooling (no npm/webpack) — keep it Pi-friendly.
- Database: **PostgreSQL 17**, already installed and running on this host.
  - Host: 127.0.0.1, Port: 5432
  - Database: `telemetryvault`, User: `teleuser`, Password: `***`
  - Connection string: `postgresql://teleuser:***@127.0.0.1:5432/telemetryvault`
- Git: commit your work; the `origin` remote is already configured with credentials (github.com/yash130384/telemetryvault). Push to `main`.
- Never print the DB password or PAT in logs or in the final summary.

## What the app does
1. **UDP ingestion**: ACC sends out-car telemetry over UDP broadcast (Out Acc Apps / `acs_` SDK, typical port 20000, JSON per frame: speed, rpm, gear, throttle, brake, steering, throttle/brake input, driftnormalized, gearInputsNormal, performance metrics, yawRate, velocity, carCoordH, track position, tire surfaces/loads/pressures/temps, fuel, engine warnings, etc.). The app listens on a configurable UDP port (default 20000) and writes every frame to Postgres.
2. **Sessions**: a "session" auto-starts on first frame after idle and closes after ~30s without frames. Each session records: date/time, track (from config file if available), car, driver name, frame count, duration.
3. **Storage**: time-series tables (telemetry_frames linked to sessions), with an index suitable for range queries per session.

## Web UI (racing-engineer style)
- **Overview**: list of sessions grouped/filtered by track and session date; select one to analyze.
- **Session analysis view** ("renningenieur"):
  - Track map: position trace (x/y from velocity+angle integration or carCoord data), heat-colored by speed/throttle/brake.
  - Live-style gauges: speed, rpm, gear, throttle, brake, steering angle.
  - Time-series charts: speed, throttle/brake, steering, gear, rpm, tire temps/pressures per corner, lap traces overlaid for comparison (best lap vs selected lap).
  - Delta/consistency: lap times table, sector-style splits if derivable from position crossing.
- Polished, dark "engineering dashboard" aesthetic. Charts can use a CDN lib (e.g. Chart.js or ECharts) or hand-rolled canvas — your call, but keep it lightweight.

## Project layout (suggestion, you own the final call)
```
telemetryvault/
  server/          FastAPI app (ingest.py for UDP listener, api.py, db.py, models/)
  web/             static frontend (index.html, analysis.html, js/, css/)
  migrations/      plain .sql schema files applied at startup
  run.sh           starts uvicorn + UDP listener on the Pi
  AGY.md           this file
```

## Definition of done (verify before finishing)
- `bash run.sh` starts cleanly; web UI reachable at http://localhost:8000.
- Injected sample telemetry (write a small simulator script that sends realistic ACC-style JSON UDP frames for ~2 min worth of a hotlap) shows up: session auto-created, frames in Postgres, session visible in UI, charts and track map render with real data.
- Migrations are idempotent; schema in `migrations/`.
- README.md with run instructions.
- Everything committed and pushed to `main`.
