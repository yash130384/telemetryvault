import { fetchSession, fetchSessionLaps, fetchTelemetry, fetchTrackmap, fetchLapComparison, formatLapTime, formatDateTime } from "./api.js";
import { TrackMapRenderer } from "./trackmap.js";
import { GaugesHUD } from "./gauges.js";
import { TelemetryCharts } from "./charts.js";

// State
let sessionId = null;
let sessionData = null;
let lapsData = [];
let currentLapNumber = null;
let currentFrames = [];
let trackmapPoints = [];
let activeMode = "single"; // 'single' | 'compare'
let isPlaying = false;
let playSpeed = 1.0;
let playInterval = null;
let currentFrameIndex = 0;

// Subsystems
let trackmap = null;
let hud = null;
let charts = null;
let liveWs = null;

function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

async function init() {
  sessionId = getQueryParam("session_id");
  if (!sessionId) {
    alert("No session ID specified in URL.");
    window.location.href = "/";
    return;
  }

  // Initialize UI components
  hud = new GaugesHUD();

  trackmap = new TrackMapRenderer("trackmap-canvas", (idx, pt) => {
    // On track point hover/click
    setFrameIndex(idx);
  });

  charts = new TelemetryCharts((idx, frame) => {
    // On chart crosshair hover
    setFrameIndex(idx, false);
  });

  setupEventListeners();
  await loadSessionData();

  // If live mode requested or active session, connect WebSocket
  if (getQueryParam("live") === "1" || sessionData?.is_active) {
    initLiveWebSocket();
  }
}

function setupEventListeners() {
  // Mode Switcher
  const tabSingle = document.getElementById("tab-single");
  const tabCompare = document.getElementById("tab-compare");
  const singleContainer = document.getElementById("single-lap-container");
  const compareContainer = document.getElementById("compare-container");

  tabSingle?.addEventListener("click", () => {
    activeMode = "single";
    tabSingle.classList.add("active");
    tabCompare?.classList.remove("active");
    if (singleContainer) singleContainer.style.display = "block";
    if (compareContainer) compareContainer.style.display = "none";
    loadLapTelemetry();
  });

  tabCompare?.addEventListener("click", () => {
    activeMode = "compare";
    tabCompare.classList.add("active");
    tabSingle?.classList.remove("active");
    if (singleContainer) singleContainer.style.display = "none";
    if (compareContainer) compareContainer.style.display = "block";
    loadComparisonData();
  });

  // Lap Selector
  const lapSelect = document.getElementById("select-lap");
  lapSelect?.addEventListener("change", (e) => {
    const val = e.target.value;
    currentLapNumber = val === "all" ? null : parseInt(val, 10);
    loadLapTelemetry();
    loadTrackmapData();
  });

  // Compare Selectors
  document.getElementById("compare-lap-1")?.addEventListener("change", loadComparisonData);
  document.getElementById("compare-lap-2")?.addEventListener("change", loadComparisonData);

  // Heatmap Mode Buttons
  document.querySelectorAll("[data-map-mode]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll("[data-map-mode]").forEach(b => b.classList.remove("active"));
      e.currentTarget.classList.add("active");
      const mode = e.currentTarget.dataset.mapMode;
      trackmap.setMode(mode);
    });
  });

  // Replay Controls
  const btnPlay = document.getElementById("btn-play");
  btnPlay?.addEventListener("click", togglePlayback);

  const scrubber = document.getElementById("scrubber-slider");
  scrubber?.addEventListener("input", (e) => {
    pausePlayback();
    setFrameIndex(parseInt(e.target.value, 10));
  });

  // Playback Speed Buttons
  document.querySelectorAll("[data-speed]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll("[data-speed]").forEach(b => b.classList.remove("active"));
      e.currentTarget.classList.add("active");
      playSpeed = parseFloat(e.currentTarget.dataset.speed);
      if (isPlaying) {
        startPlayback();
      }
    });
  });
}

async function loadSessionData() {
  try {
    sessionData = await fetchSession(sessionId);
    lapsData = sessionData.laps || [];

    // Populate header chips
    document.getElementById("chip-track").textContent = (sessionData.track || "unknown").toUpperCase();
    document.getElementById("chip-car").textContent = sessionData.car || "GT3";
    document.getElementById("chip-driver").textContent = sessionData.driver || "Driver";
    document.getElementById("chip-date").textContent = formatDateTime(sessionData.started_at);
    document.getElementById("chip-best-lap").textContent = sessionData.best_lap_time_ms
      ? formatLapTime(sessionData.best_lap_time_ms)
      : "--:--.---";

    // Populate Lap Dropdown
    const selectLap = document.getElementById("select-lap");
    const comp1 = document.getElementById("compare-lap-1");
    const comp2 = document.getElementById("compare-lap-2");

    if (selectLap) {
      selectLap.innerHTML = '<option value="all">All Laps (Overview)</option>';
      lapsData.forEach(l => {
        const timeStr = formatLapTime(l.lap_time_ms);
        const opt = document.createElement("option");
        opt.value = l.lap_number;
        opt.textContent = `Lap ${l.lap_number} (${timeStr})`;
        selectLap.appendChild(opt);
      });
    }

    if (comp1 && comp2) {
      comp1.innerHTML = "";
      comp2.innerHTML = "";
      lapsData.forEach(l => {
        const timeStr = formatLapTime(l.lap_time_ms);
        comp1.innerHTML += `<option value="${l.lap_number}">Lap ${l.lap_number} (${timeStr})</option>`;
        comp2.innerHTML += `<option value="${l.lap_number}">Lap ${l.lap_number} (${timeStr})</option>`;
      });

      // Default comparison: Lap 1 vs Lap 2, or best lap
      if (lapsData.length >= 2) {
        comp1.value = lapsData[0].lap_number;
        comp2.value = lapsData[1].lap_number;
      }
    }

    // Default select best lap or Lap 1
    if (lapsData.length > 0) {
      let bestLap = lapsData[0].lap_number;
      let minTime = lapsData[0].lap_time_ms || Infinity;
      lapsData.forEach(l => {
        if (l.lap_time_ms && l.lap_time_ms < minTime) {
          minTime = l.lap_time_ms;
          bestLap = l.lap_number;
        }
      });
      currentLapNumber = bestLap;
      if (selectLap) selectLap.value = bestLap;
    }

    renderLapsTable();
    await loadTrackmapData();
    await loadLapTelemetry();

  } catch (e) {
    console.error("Failed to load session:", e);
    alert("Could not load session telemetry: " + e.message);
  }
}

function renderLapsTable() {
  const tbody = document.getElementById("laps-table-body");
  if (!tbody) return;

  const bestLapMs = sessionData.best_lap_time_ms;

  tbody.innerHTML = lapsData.map(l => {
    const isBest = bestLapMs && l.lap_time_ms === bestLapMs;
    const deltaMs = (l.lap_time_ms && bestLapMs) ? l.lap_time_ms - bestLapMs : null;
    let deltaStr = "--";
    if (isBest) deltaStr = '<span class="best-lap">BEST LAP</span>';
    else if (deltaMs !== null) deltaStr = `+${(deltaMs / 1000).toFixed(3)}s`;

    return `
      <tr style="cursor: pointer;" data-lap="${l.lap_number}" class="${l.lap_number === currentLapNumber ? 'table-active' : ''}">
        <td class="time-mono"><strong>Lap ${l.lap_number}</strong></td>
        <td class="time-mono ${isBest ? 'best-lap' : ''}">${formatLapTime(l.lap_time_ms)}</td>
        <td class="time-mono">${deltaStr}</td>
        <td class="time-mono">${Math.round(l.max_speed || 0)} km/h</td>
        <td class="time-mono">${Math.round(l.avg_speed || 0)} km/h</td>
        <td style="color: var(--text-muted);">${(l.frame_count || 0).toLocaleString()}</td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("tr").forEach(row => {
    row.addEventListener("click", () => {
      const lap = parseInt(row.dataset.lap, 10);
      currentLapNumber = lap;
      const selectLap = document.getElementById("select-lap");
      if (selectLap) selectLap.value = lap;
      loadLapTelemetry();
      loadTrackmapData();
      renderLapsTable();
    });
  });
}

async function loadTrackmapData() {
  try {
    const res = await fetchTrackmap(sessionId, currentLapNumber);
    trackmapPoints = res.points || [];
    trackmap.setPoints(trackmapPoints);

    // Update trackmap stats
    if (trackmapPoints.length > 0) {
      let maxSpd = 0;
      let minSpd = Infinity;
      trackmapPoints.forEach(p => {
        if (p.speed > maxSpd) maxSpd = p.speed;
        if (p.speed < minSpd) minSpd = p.speed;
      });
      document.getElementById("map-max-speed").textContent = `${Math.round(maxSpd)} km/h`;
      document.getElementById("map-min-speed").textContent = `${Math.round(minSpd)} km/h`;
    }
  } catch (e) {
    console.error("Failed to load trackmap data:", e);
  }
}

async function loadLapTelemetry() {
  try {
    const step = currentLapNumber === null ? 2 : 1;
    currentFrames = await fetchTelemetry(sessionId, currentLapNumber, step);

    const scrubber = document.getElementById("scrubber-slider");
    if (scrubber) {
      scrubber.min = 0;
      scrubber.max = Math.max(0, currentFrames.length - 1);
      scrubber.value = 0;
    }

    charts.loadSingleLap(currentFrames);

    if (currentFrames.length > 0) {
      setFrameIndex(0);
    }
  } catch (e) {
    console.error("Failed to load telemetry frames:", e);
  }
}

async function loadComparisonData() {
  const comp1 = document.getElementById("compare-lap-1");
  const comp2 = document.getElementById("compare-lap-2");
  if (!comp1 || !comp2) return;

  const lap1 = parseInt(comp1.value, 10);
  const lap2 = parseInt(comp2.value, 10);

  if (isNaN(lap1) || isNaN(lap2)) return;

  try {
    const compData = await fetchLapComparison(sessionId, lap1, lap2);
    charts.loadComparison(compData);

    // Calculate net delta
    const l1 = lapsData.find(l => l.lap_number === lap1);
    const l2 = lapsData.find(l => l.lap_number === lap2);
    if (l1 && l2 && l1.lap_time_ms && l2.lap_time_ms) {
      const diffSec = (l2.lap_time_ms - l1.lap_time_ms) / 1000.0;
      const elDelta = document.getElementById("compare-net-delta");
      if (elDelta) {
        elDelta.textContent = `${diffSec > 0 ? "+" : ""}${diffSec.toFixed(3)}s`;
        elDelta.className = `delta-stat ${diffSec > 0 ? "positive" : "negative"}`;
      }
      document.getElementById("compare-time-1").textContent = formatLapTime(l1.lap_time_ms);
      document.getElementById("compare-time-2").textContent = formatLapTime(l2.lap_time_ms);
    }
  } catch (e) {
    console.error("Failed to load comparison:", e);
  }
}

function setFrameIndex(idx, updateScrubber = true) {
  if (idx < 0 || idx >= currentFrames.length) return;
  currentFrameIndex = idx;
  const frame = currentFrames[idx];

  // Update HUD
  hud.update(frame);

  // Update Trackmap marker
  if (trackmapPoints.length > 0) {
    // Map frame to nearest trackmap point by normalized track_pos
    const pos = frame.track_pos || 0;
    const mapIdx = Math.min(trackmapPoints.length - 1, Math.floor(pos * trackmapPoints.length));
    trackmap.setCarPosition(mapIdx);
  }

  // Update Scrubber slider
  if (updateScrubber) {
    const scrubber = document.getElementById("scrubber-slider");
    if (scrubber) scrubber.value = idx;
  }

  // Update scrubber time text
  const timeEl = document.getElementById("scrubber-time");
  if (timeEl) {
    const sec = ((frame.lap_time_ms || 0) / 1000.0).toFixed(2);
    const posPct = ((frame.track_pos || 0) * 100).toFixed(1);
    timeEl.textContent = `${sec}s (${posPct}%)`;
  }
}

function togglePlayback() {
  if (isPlaying) pausePlayback();
  else startPlayback();
}

function startPlayback() {
  if (!currentFrames.length) return;
  isPlaying = true;
  const btnPlay = document.getElementById("btn-play");
  if (btnPlay) btnPlay.textContent = "⏸ Pause";

  if (playInterval) clearInterval(playInterval);

  // Base 20 Hz replay = 50ms interval adjusted by playSpeed
  const intervalMs = Math.max(10, Math.round(50 / playSpeed));

  playInterval = setInterval(() => {
    let nextIdx = currentFrameIndex + 1;
    if (nextIdx >= currentFrames.length) {
      nextIdx = 0; // Loop playback
    }
    setFrameIndex(nextIdx);
  }, intervalMs);
}

function pausePlayback() {
  isPlaying = false;
  const btnPlay = document.getElementById("btn-play");
  if (btnPlay) btnPlay.textContent = "▶ Play";
  if (playInterval) {
    clearInterval(playInterval);
    playInterval = null;
  }
}

function initLiveWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  liveWs = new WebSocket(wsUrl);

  liveWs.onopen = () => {
    console.log("Connected to live telemetry stream");
    const badge = document.getElementById("live-stream-badge");
    if (badge) badge.style.display = "inline-flex";
  };

  liveWs.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && data.session_id == sessionId) {
        hud.update(data);
        if (trackmapPoints.length > 0 && data.track_pos !== undefined) {
          const mapIdx = Math.min(trackmapPoints.length - 1, Math.floor(data.track_pos * trackmapPoints.length));
          trackmap.setCarPosition(mapIdx);
        }
      }
    } catch (e) {
      console.error("WebSocket message parse error:", e);
    }
  };

  liveWs.onclose = () => {
    const badge = document.getElementById("live-stream-badge");
    if (badge) badge.style.display = "none";
  };
}

document.addEventListener("DOMContentLoaded", init);
