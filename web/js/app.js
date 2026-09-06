import { fetchHealth, fetchTracks, fetchSessions, deleteSession, formatLapTime, formatDateTime } from "./api.js";

let currentTrackFilter = "";
let currentSearch = "";

async function updateHealth() {
  try {
    const health = await fetchHealth();
    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("status-text");
    const liveBanner = document.getElementById("live-banner");

    if (health.active_session && health.active_session.is_active) {
      if (statusDot) {
        statusDot.className = "status-dot";
        statusDot.classList.remove("idle");
      }
      if (statusText) statusText.textContent = `REC SESSION #${health.active_session.session_id}`;
      
      // Update or show live banner
      if (liveBanner) {
        liveBanner.style.display = "flex";
        document.getElementById("live-session-id").textContent = `#${health.active_session.session_id}`;
        document.getElementById("live-frame-count").textContent = `${health.active_session.frame_count} frames`;
        document.getElementById("live-lap-count").textContent = `Lap ${health.active_session.current_lap || 1}`;
        const liveBtn = document.getElementById("live-analysis-btn");
        if (liveBtn) liveBtn.href = `/analysis?session_id=${health.active_session.session_id}&live=1`;
      }
    } else {
      if (statusDot) {
        statusDot.className = "status-dot idle";
      }
      if (statusText) statusText.textContent = "IDLE (WAITING UDP)";
      if (liveBanner) liveBanner.style.display = "none";
    }
  } catch (e) {
    console.error("Health check error:", e);
  }
}

async function loadTracks() {
  try {
    const tracks = await fetchTracks();
    const select = document.getElementById("filter-track");
    if (!select) return;

    // Preserve selection
    const curr = select.value;
    select.innerHTML = '<option value="">All Tracks</option>';
    tracks.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.track;
      opt.textContent = `${t.track.toUpperCase()} (${t.session_count})`;
      select.appendChild(opt);
    });
    select.value = curr;
  } catch (e) {
    console.error("Failed to load tracks:", e);
  }
}

async function loadSessions() {
  const container = document.getElementById("sessions-tbody");
  const emptyState = document.getElementById("empty-state");
  if (!container) return;

  try {
    const sessions = await fetchSessions(currentTrackFilter);
    let filtered = sessions;

    if (currentSearch.trim()) {
      const q = currentSearch.toLowerCase();
      filtered = sessions.filter(s =>
        (s.car && s.car.toLowerCase().includes(q)) ||
        (s.driver && s.driver.toLowerCase().includes(q)) ||
        (s.track && s.track.toLowerCase().includes(q))
      );
    }

    if (!filtered.length) {
      container.innerHTML = "";
      if (emptyState) emptyState.style.display = "block";
      return;
    }

    if (emptyState) emptyState.style.display = "none";

    container.innerHTML = filtered.map(s => {
      const durMin = (s.duration_seconds / 60).toFixed(1);
      const bestLapStr = s.best_lap_time_ms ? formatLapTime(s.best_lap_time_ms) : "--:--.---";
      const statusBadge = s.is_active
        ? '<span class="status-badge" style="border-color: var(--accent-green); color: var(--accent-green);">● LIVE</span>'
        : '<span style="color: var(--text-muted);">Ended</span>';

      return `
        <tr>
          <td><span class="track-badge">${s.track}</span></td>
          <td>
            <div style="font-weight: 600;">${s.car}</div>
            <div style="font-size: 0.8rem; color: var(--text-secondary);">${s.driver}</div>
          </td>
          <td>
            <div class="time-mono">${formatDateTime(s.started_at)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${durMin} min (${s.frame_count.toLocaleString()} frames)</div>
          </td>
          <td>
            <span class="time-mono">${s.total_laps}</span>
          </td>
          <td>
            <span class="best-lap">${bestLapStr}</span>
          </td>
          <td>${statusBadge}</td>
          <td style="text-align: right;">
            <a href="/analysis?session_id=${s.id}" class="btn btn-primary" style="padding: 0.35rem 0.75rem; margin-right: 0.5rem;">
              Analyze
            </a>
            <button class="btn btn-danger btn-delete" data-id="${s.id}" style="padding: 0.35rem 0.5rem;" title="Delete Session">
              ✕
            </button>
          </td>
        </tr>
      `;
    }).join("");

    // Attach delete listeners
    container.querySelectorAll(".btn-delete").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const id = e.currentTarget.dataset.id;
        if (confirm(`Delete session #${id} and all its telemetry data?`)) {
          await deleteSession(id);
          await loadSessions();
          await loadTracks();
        }
      });
    });

  } catch (e) {
    console.error("Failed to load sessions:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const trackFilter = document.getElementById("filter-track");
  if (trackFilter) {
    trackFilter.addEventListener("change", (e) => {
      currentTrackFilter = e.target.value;
      loadSessions();
    });
  }

  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearch = e.target.value;
      loadSessions();
    });
  }

  const refreshBtn = document.getElementById("btn-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadSessions();
      loadTracks();
      updateHealth();
    });
  }

  // Initial load
  updateHealth();
  loadTracks();
  loadSessions();

  // Poll status every 3s
  setInterval(updateHealth, 3000);
});
