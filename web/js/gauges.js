// Live Racing HUD Gauges & Dynamic Readouts

export class GaugesHUD {
  constructor() {
    this.elSpeed = document.getElementById("hud-speed");
    this.elGear = document.getElementById("hud-gear");
    this.elRpm = document.getElementById("hud-rpm");
    this.elMaxRpm = document.getElementById("hud-max-rpm");
    this.elRpmBar = document.getElementById("hud-rpm-bar");
    this.elThrottleBar = document.getElementById("hud-throttle-bar");
    this.elThrottleVal = document.getElementById("hud-throttle-val");
    this.elBrakeBar = document.getElementById("hud-brake-bar");
    this.elBrakeVal = document.getElementById("hud-brake-val");
    this.elSteer = document.getElementById("hud-steer");
    this.elGLat = document.getElementById("hud-g-lat");
    this.elGLon = document.getElementById("hud-g-lon");

    this.tyreElements = {
      fl: {
        temp: document.getElementById("tyre-temp-fl"),
        press: document.getElementById("tyre-press-fl"),
        brake: document.getElementById("brake-temp-fl"),
        box: document.getElementById("tyre-box-fl")
      },
      fr: {
        temp: document.getElementById("tyre-temp-fr"),
        press: document.getElementById("tyre-press-fr"),
        brake: document.getElementById("brake-temp-fr"),
        box: document.getElementById("tyre-box-fr")
      },
      rl: {
        temp: document.getElementById("tyre-temp-rl"),
        press: document.getElementById("tyre-press-rl"),
        brake: document.getElementById("brake-temp-rl"),
        box: document.getElementById("tyre-box-rl")
      },
      rr: {
        temp: document.getElementById("tyre-temp-rr"),
        press: document.getElementById("tyre-press-rr"),
        brake: document.getElementById("brake-temp-rr"),
        box: document.getElementById("tyre-box-rr")
      }
    };
  }

  update(frame) {
    if (!frame) return;

    // Speed
    const spd = frame.speed !== undefined ? Math.round(frame.speed) : 0;
    if (this.elSpeed) this.elSpeed.textContent = spd;

    // Gear
    if (this.elGear) {
      let g = frame.gear;
      if (g === 0) g = "N";
      else if (g === -1) g = "R";
      this.elGear.textContent = g;
    }

    // RPM & Shift lights
    const rpm = frame.rpm || 0;
    const maxRpm = frame.max_rpm || 8500;
    if (this.elRpm) this.elRpm.textContent = rpm.toLocaleString();
    if (this.elMaxRpm) this.elMaxRpm.textContent = maxRpm.toLocaleString();

    if (this.elRpmBar) {
      const pct = Math.min(100, Math.max(0, (rpm / maxRpm) * 100));
      this.elRpmBar.style.width = `${pct}%`;
      if (pct >= 95) {
        this.elRpmBar.classList.add("shift-flash");
      } else {
        this.elRpmBar.classList.remove("shift-flash");
      }
    }

    // Pedals
    const thr = Math.min(100, Math.max(0, Math.round((frame.throttle || 0) * 100)));
    const brk = Math.min(100, Math.max(0, Math.round((frame.brake || 0) * 100)));

    if (this.elThrottleBar) this.elThrottleBar.style.width = `${thr}%`;
    if (this.elThrottleVal) this.elThrottleVal.textContent = `${thr}%`;
    if (this.elBrakeBar) this.elBrakeBar.style.width = `${brk}%`;
    if (this.elBrakeVal) this.elBrakeVal.textContent = `${brk}%`;

    // Steering
    if (this.elSteer) {
      const st = (frame.steer || 0).toFixed(1);
      this.elSteer.textContent = `${st > 0 ? "+" : ""}${st}°`;
    }

    // G-Forces
    if (this.elGLat) {
      const glat = (frame.g_force_lat !== undefined ? frame.g_force_lat : (frame.g_lat || 0)).toFixed(2);
      this.elGLat.textContent = `${glat}G`;
    }
    if (this.elGLon) {
      const glon = (frame.g_force_lon !== undefined ? frame.g_force_lon : (frame.g_lon || 0)).toFixed(2);
      this.elGLon.textContent = `${glon}G`;
    }

    // 4 Tyres
    this._updateTyreCorner("fl", frame.tyre_temp_fl ?? frame.tyre_temp?.[0], frame.tyre_press_fl ?? frame.tyre_press?.[0], frame.brake_temp_fl ?? frame.brake_temp?.[0]);
    this._updateTyreCorner("fr", frame.tyre_temp_fr ?? frame.tyre_temp?.[1], frame.tyre_press_fr ?? frame.tyre_press?.[1], frame.brake_temp_fr ?? frame.brake_temp?.[1]);
    this._updateTyreCorner("rl", frame.tyre_temp_rl ?? frame.tyre_temp?.[2], frame.tyre_press_rl ?? frame.tyre_press?.[2], frame.brake_temp_rl ?? frame.brake_temp?.[2]);
    this._updateTyreCorner("rr", frame.tyre_temp_rr ?? frame.tyre_temp?.[3], frame.tyre_press_rr ?? frame.tyre_press?.[3], frame.brake_temp_rr ?? frame.brake_temp?.[3]);
  }

  _updateTyreCorner(corner, temp, press, brake) {
    const el = this.tyreElements[corner];
    if (!el) return;

    if (temp !== undefined && el.temp) {
      el.temp.textContent = `${Math.round(temp)}°C`;
      // Color based on temperature
      let col = "#00e676"; // optimal
      if (temp < 75) col = "#00d4ff"; // cold
      else if (temp > 95) col = "#ff1744"; // overheated
      else if (temp > 90) col = "#ffab00"; // warm
      el.temp.style.color = col;
      if (el.box) el.box.style.borderLeftColor = col;
    }

    if (press !== undefined && el.press) {
      el.press.textContent = `${Number(press).toFixed(1)} PSI`;
    }

    if (brake !== undefined && el.brake) {
      el.brake.textContent = `${Math.round(brake)}°C`;
      if (brake > 550) el.brake.style.color = "#ff1744";
      else el.brake.style.color = "var(--text-secondary)";
    }
  }
}
