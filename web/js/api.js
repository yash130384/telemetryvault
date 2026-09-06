// API helper methods for TelemetryVault

export async function fetchHealth() {
  const res = await fetch("/api/health");
  return await res.json();
}

export async function fetchTracks() {
  const res = await fetch("/api/tracks");
  return await res.json();
}

export async function fetchSessions(track = null, limit = 50, offset = 0) {
  let url = `/api/sessions?limit=${limit}&offset=${offset}`;
  if (track) url += `&track=${encodeURIComponent(track)}`;
  const res = await fetch(url);
  return await res.json();
}

export async function fetchSession(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}`);
  if (!res.ok) throw new Error("Session not found");
  return await res.json();
}

export async function fetchSessionLaps(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}/laps`);
  return await res.json();
}

export async function fetchTelemetry(sessionId, lapNumber = null, step = 1) {
  let url = `/api/sessions/${sessionId}/telemetry?step=${step}`;
  if (lapNumber !== null && lapNumber !== undefined) {
    url += `&lap_number=${lapNumber}`;
  }
  const res = await fetch(url);
  return await res.json();
}

export async function fetchTrackmap(sessionId, lapNumber = null) {
  let url = `/api/sessions/${sessionId}/trackmap`;
  if (lapNumber !== null && lapNumber !== undefined) {
    url += `&lap_number=${lapNumber}`;
  }
  const res = await fetch(url);
  return await res.json();
}

export async function fetchLapComparison(sessionId, lap1, lap2, samples = 400) {
  const url = `/api/sessions/${sessionId}/compare?lap1=${lap1}&lap2=${lap2}&samples=${samples}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Lap comparison data unavailable");
  return await res.json();
}

export async function deleteSession(sessionId) {
  const res = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
  return await res.json();
}

export function formatLapTime(ms) {
  if (!ms || ms <= 0) return "--:--.---";
  const totalSec = ms / 1000.0;
  const mins = Math.floor(totalSec / 60);
  const secs = (totalSec % 60).toFixed(3);
  const padSecs = (totalSec % 60) < 10 ? "0" + secs : secs;
  return `${mins}:${padSecs}`;
}

export function formatDateTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}
