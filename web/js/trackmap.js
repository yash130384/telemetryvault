// Interactive 2D Canvas Track Map with Heatmap Coloration & Car Position Cursor

export class TrackMapRenderer {
  constructor(canvasId, onPointSelected = null) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext("2d");
    this.onPointSelected = onPointSelected;

    this.points = [];
    this.mode = "speed"; // 'speed' | 'throttle' | 'brake' | 'gear'
    this.carIndex = 0;

    this.bounds = { minX: 0, maxX: 1, minZ: 0, maxZ: 1, rangeX: 1, rangeZ: 1 };
    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;

    this._setupResize();
    this._setupEvents();
  }

  _setupResize() {
    const resize = () => {
      const rect = this.canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      this.canvas.width = rect.width * dpr;
      this.canvas.height = rect.height * dpr;
      this.render();
    };
    window.addEventListener("resize", resize);
    // Initial size
    setTimeout(resize, 50);
  }

  _setupEvents() {
    this.canvas.addEventListener("mousemove", (e) => {
      if (!this.points.length) return;
      const rect = this.canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const mouseX = (e.clientX - rect.left) * dpr;
      const mouseY = (e.clientY - rect.top) * dpr;

      let closestIdx = -1;
      let minSqDist = Infinity;

      for (let i = 0; i < this.points.length; i++) {
        const p = this._project(this.points[i].coord_x, this.points[i].coord_z);
        const dx = p.x - mouseX;
        const dy = p.y - mouseY;
        const sq = dx * dx + dy * dy;
        if (sq < minSqDist) {
          minSqDist = sq;
          closestIdx = i;
        }
      }

      if (closestIdx !== -1 && minSqDist < 1600) { // 40px threshold
        if (this.onPointSelected) {
          this.onPointSelected(closestIdx, this.points[closestIdx]);
        }
      }
    });

    this.canvas.addEventListener("click", (e) => {
      if (!this.points.length) return;
      const rect = this.canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const mouseX = (e.clientX - rect.left) * dpr;
      const mouseY = (e.clientY - rect.top) * dpr;

      let closestIdx = -1;
      let minSqDist = Infinity;

      for (let i = 0; i < this.points.length; i++) {
        const p = this._project(this.points[i].coord_x, this.points[i].coord_z);
        const sq = (p.x - mouseX)**2 + (p.y - mouseY)**2;
        if (sq < minSqDist) {
          minSqDist = sq;
          closestIdx = i;
        }
      }

      if (closestIdx !== -1 && this.onPointSelected) {
        this.onPointSelected(closestIdx, this.points[closestIdx]);
      }
    });
  }

  setPoints(points) {
    this.points = points || [];
    if (!this.points.length) {
      this.render();
      return;
    }

    let minX = Infinity, maxX = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;

    for (const p of this.points) {
      const x = p.coord_x;
      const z = p.coord_z;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }

    this.bounds = {
      minX, maxX, minZ, maxZ,
      rangeX: Math.max(maxX - minX, 10.0),
      rangeZ: Math.max(maxZ - minZ, 10.0)
    };

    this.carIndex = 0;
    this.render();
  }

  setMode(mode) {
    this.mode = mode;
    this.render();
  }

  setCarPosition(index) {
    if (index >= 0 && index < this.points.length) {
      this.carIndex = index;
      this.render();
    }
  }

  _project(x, z) {
    const pad = 40 * (window.devicePixelRatio || 1);
    const w = this.canvas.width - pad * 2;
    const h = this.canvas.height - pad * 2;

    const scaleX = w / this.bounds.rangeX;
    const scaleZ = h / this.bounds.rangeZ;
    const s = Math.min(scaleX, scaleZ);

    const cx = (this.bounds.minX + this.bounds.maxX) / 2;
    const cz = (this.bounds.minZ + this.bounds.maxZ) / 2;

    const px = this.canvas.width / 2 + (x - cx) * s;
    const pz = this.canvas.height / 2 - (z - cz) * s; // Invert Z for screen coords

    return { x: px, y: pz };
  }

  _getColor(p) {
    if (this.mode === "throttle") {
      const t = Math.max(0, Math.min(1, p.throttle || 0));
      return `rgb(${Math.round(20 + t * 0)}, ${Math.round(40 + t * 215)}, ${Math.round(60 + t * 50)})`;
    }
    if (this.mode === "brake") {
      const b = Math.max(0, Math.min(1, p.brake || 0));
      return `rgb(${Math.round(50 + b * 205)}, ${Math.round(40 * (1 - b))}, ${Math.round(40 * (1 - b))})`;
    }
    if (this.mode === "gear") {
      const g = p.gear || 1;
      const gearColors = {
        1: "#0055ff", 2: "#00d4ff", 3: "#00e676", 4: "#ffff00", 5: "#ff9100", 6: "#d500f9"
      };
      return gearColors[g] || "#00d4ff";
    }

    // Default: speed heatmap
    const spd = p.speed || 0;
    // 60 km/h to 270 km/h
    const norm = Math.max(0, Math.min(1, (spd - 60) / 210));
    return this._turboColormap(norm);
  }

  _turboColormap(t) {
    // Smooth blue -> cyan -> green -> yellow -> red
    let r, g, b;
    if (t < 0.25) {
      const f = t / 0.25;
      r = 0; g = Math.round(f * 200); b = 255;
    } else if (t < 0.5) {
      const f = (t - 0.25) / 0.25;
      r = 0; g = 255; b = Math.round(255 * (1 - f));
    } else if (t < 0.75) {
      const f = (t - 0.5) / 0.25;
      r = Math.round(f * 255); g = 255; b = 0;
    } else {
      const f = (t - 0.75) / 0.25;
      r = 255; g = Math.round(255 * (1 - f * 0.8)); b = 0;
    }
    return `rgb(${r}, ${g}, ${b})`;
  }

  render() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!this.points.length) {
      ctx.fillStyle = "#57606a";
      ctx.font = "14px monospace";
      ctx.textAlign = "center";
      ctx.fillText("No track map data loaded", w / 2, h / 2);
      return;
    }

    const dpr = window.devicePixelRatio || 1;

    // Draw track shadow/outer glow
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = 10 * dpr;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.4)";
    ctx.beginPath();
    for (let i = 0; i < this.points.length; i++) {
      const p = this._project(this.points[i].coord_x, this.points[i].coord_z);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();

    // Draw segments colored by heatmap
    ctx.lineWidth = 4.5 * dpr;
    for (let i = 0; i < this.points.length - 1; i++) {
      const p1 = this._project(this.points[i].coord_x, this.points[i].coord_z);
      const p2 = this._project(this.points[i + 1].coord_x, this.points[i + 1].coord_z);

      ctx.strokeStyle = this._getColor(this.points[i]);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
    }

    // Draw Start / Finish Line
    if (this.points.length > 2) {
      const sf = this._project(this.points[0].coord_x, this.points[0].coord_z);
      const next = this._project(this.points[2].coord_x, this.points[2].coord_z);
      const dx = next.x - sf.x;
      const dy = next.y - sf.y;
      const len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len * (12 * dpr);
      const ny = dx / len * (12 * dpr);

      ctx.lineWidth = 3.5 * dpr;
      ctx.strokeStyle = "#ffffff";
      ctx.beginPath();
      ctx.moveTo(sf.x - nx, sf.y - ny);
      ctx.lineTo(sf.x + nx, sf.y + ny);
      ctx.stroke();

      // S/F badge text
      ctx.fillStyle = "#00e676";
      ctx.font = `bold ${10 * dpr}px monospace`;
      ctx.textAlign = "center";
      ctx.fillText("S/F", sf.x - nx * 1.5, sf.y - ny * 1.5);
    }

    // Draw Car Position Marker
    if (this.carIndex >= 0 && this.carIndex < this.points.length) {
      const car = this.points[this.carIndex];
      const proj = this._project(car.coord_x, car.coord_z);

      // Pulse ring
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, 10 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(0, 212, 255, 0.25)";
      ctx.fill();

      // Outer ring
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, 6 * dpr, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2 * dpr;
      ctx.stroke();

      // Inner dot
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, 4 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = "#00d4ff";
      ctx.fill();
    }
  }
}
