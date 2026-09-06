// Multi-panel telemetry time-series charts with synchronized crosshairs

export class TelemetryCharts {
  constructor(onCursorChange = null) {
    this.onCursorChange = onCursorChange;
    this.charts = {};
    this.frames = [];
    this.cursorIndex = -1;
  }

  destroy() {
    Object.values(this.charts).forEach(c => {
      try { c.destroy(); } catch (e) {}
    });
    this.charts = {};
  }

  loadSingleLap(frames) {
    this.destroy();
    this.frames = frames || [];
    if (!this.frames.length) return;

    // Build x-axis labels: distance % or seconds
    const labels = this.frames.map((f, i) => {
      if (f.track_pos !== undefined) {
        return (f.track_pos * 100).toFixed(1) + "%";
      }
      return (f.lap_time_ms / 1000).toFixed(1) + "s";
    });

    const commonOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        mode: "index",
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            boxWidth: 12,
            font: { family: "monospace", size: 10 },
            color: "#8b949e"
          }
        },
        tooltip: {
          enabled: true,
          backgroundColor: "#121722",
          titleFont: { family: "monospace" },
          bodyFont: { family: "monospace" },
          borderColor: "#1f2738",
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: "#161b26" },
          ticks: {
            color: "#57606a",
            font: { family: "monospace", size: 9 },
            maxTicksLimit: 12
          }
        },
        y: {
          grid: { color: "#161b26" },
          ticks: {
            color: "#8b949e",
            font: { family: "monospace", size: 10 }
          }
        }
      },
      onHover: (event, elements) => {
        if (elements && elements.length > 0) {
          const idx = elements[0].index;
          if (idx !== this.cursorIndex) {
            this.cursorIndex = idx;
            if (this.onCursorChange) {
              this.onCursorChange(idx, this.frames[idx]);
            }
          }
        }
      }
    };

    // 1. Speed Chart
    const ctxSpeed = document.getElementById("chart-speed")?.getContext("2d");
    if (ctxSpeed) {
      this.charts.speed = new window.Chart(ctxSpeed, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: "Speed (km/h)",
            data: this.frames.map(f => Math.round(f.speed)),
            borderColor: "#00d4ff",
            backgroundColor: "rgba(0, 212, 255, 0.05)",
            borderWidth: 2,
            fill: true,
            pointRadius: 0
          }]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            y: { ...commonOptions.scales.y, min: 0, suggestedMax: 280 }
          }
        }
      });
    }

    // 2. Throttle & Brake Chart
    const ctxPedals = document.getElementById("chart-pedals")?.getContext("2d");
    if (ctxPedals) {
      this.charts.pedals = new window.Chart(ctxPedals, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Throttle (%)",
              data: this.frames.map(f => Math.round((f.throttle || 0) * 100)),
              borderColor: "#00e676",
              backgroundColor: "rgba(0, 230, 118, 0.1)",
              borderWidth: 1.8,
              fill: true,
              pointRadius: 0
            },
            {
              label: "Brake (%)",
              data: this.frames.map(f => Math.round((f.brake || 0) * 100)),
              borderColor: "#ff1744",
              backgroundColor: "rgba(255, 23, 68, 0.1)",
              borderWidth: 1.8,
              fill: true,
              pointRadius: 0
            }
          ]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            y: { ...commonOptions.scales.y, min: 0, max: 100 }
          }
        }
      });
    }

    // 3. Gear & RPM
    const ctxGearRpm = document.getElementById("chart-gear-rpm")?.getContext("2d");
    if (ctxGearRpm) {
      this.charts.gearRpm = new window.Chart(ctxGearRpm, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "RPM",
              data: this.frames.map(f => f.rpm),
              borderColor: "#ffab00",
              borderWidth: 1.5,
              pointRadius: 0,
              yAxisID: "yRpm"
            },
            {
              label: "Gear",
              data: this.frames.map(f => f.gear),
              borderColor: "#d500f9",
              borderWidth: 2,
              stepped: true,
              pointRadius: 0,
              yAxisID: "yGear"
            }
          ]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            yRpm: {
              type: "linear",
              position: "left",
              grid: { color: "#161b26" },
              ticks: { color: "#ffab00", font: { family: "monospace" } },
              min: 0,
              suggestedMax: 9000
            },
            yGear: {
              type: "linear",
              position: "right",
              grid: { drawOnChartArea: false },
              ticks: { color: "#d500f9", font: { family: "monospace" }, stepSize: 1 },
              min: 0,
              max: 7
            }
          }
        }
      });
    }

    // 4. Steering & Lateral G
    const ctxSteer = document.getElementById("chart-steer")?.getContext("2d");
    if (ctxSteer) {
      this.charts.steer = new window.Chart(ctxSteer, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Steering Angle (°)",
              data: this.frames.map(f => Number((f.steer || 0).toFixed(1))),
              borderColor: "#00d4ff",
              borderWidth: 1.5,
              pointRadius: 0,
              yAxisID: "ySteer"
            },
            {
              label: "Lat G",
              data: this.frames.map(f => Number((f.g_force_lat || 0).toFixed(2))),
              borderColor: "#e6edf3",
              borderWidth: 1.2,
              borderDash: [4, 4],
              pointRadius: 0,
              yAxisID: "yG"
            }
          ]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            ySteer: {
              type: "linear",
              position: "left",
              grid: { color: "#161b26" },
              ticks: { color: "#00d4ff", font: { family: "monospace" } }
            },
            yG: {
              type: "linear",
              position: "right",
              grid: { drawOnChartArea: false },
              ticks: { color: "#e6edf3", font: { family: "monospace" } }
            }
          }
        }
      });
    }

    // 5. Tyres Temperatures
    const ctxTyres = document.getElementById("chart-tyres")?.getContext("2d");
    if (ctxTyres) {
      this.charts.tyres = new window.Chart(ctxTyres, {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: "FL Temp (°C)", data: this.frames.map(f => f.tyre_temp_fl), borderColor: "#00e676", borderWidth: 1.5, pointRadius: 0 },
            { label: "FR Temp (°C)", data: this.frames.map(f => f.tyre_temp_fr), borderColor: "#00d4ff", borderWidth: 1.5, pointRadius: 0 },
            { label: "RL Temp (°C)", data: this.frames.map(f => f.tyre_temp_rl), borderColor: "#ffab00", borderWidth: 1.5, pointRadius: 0 },
            { label: "RR Temp (°C)", data: this.frames.map(f => f.tyre_temp_rr), borderColor: "#ff1744", borderWidth: 1.5, pointRadius: 0 }
          ]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            y: { ...commonOptions.scales.y, min: 60, suggestedMax: 110 }
          }
        }
      });
    }
  }

  loadComparison(comparisonData) {
    this.destroy();
    const data = comparisonData.data || [];
    if (!data.length) return;

    const labels = data.map(d => (d.pos * 100).toFixed(1) + "%");

    const commonOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        mode: "index",
        intersect: false
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: { boxWidth: 12, font: { family: "monospace", size: 10 }, color: "#8b949e" }
        }
      },
      scales: {
        x: {
          grid: { color: "#161b26" },
          ticks: { color: "#57606a", font: { family: "monospace", size: 9 }, maxTicksLimit: 12 }
        },
        y: {
          grid: { color: "#161b26" },
          ticks: { color: "#8b949e", font: { family: "monospace", size: 10 } }
        }
      }
    };

    // 1. Delta-T Chart (Seconds gained / lost)
    const ctxDelta = document.getElementById("chart-compare-delta")?.getContext("2d");
    if (ctxDelta) {
      this.charts.compareDelta = new window.Chart(ctxDelta, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: `Delta-T (Lap ${comparisonData.lap2} vs Lap ${comparisonData.lap1}) [s]`,
            data: data.map(d => d.delta_t_s),
            borderColor: "#ffab00",
            backgroundColor: "rgba(255, 171, 0, 0.1)",
            borderWidth: 2,
            fill: true,
            pointRadius: 0
          }]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            y: {
              ...commonOptions.scales.y,
              title: { display: true, text: "Time Delta (s)", color: "#ffab00" }
            }
          }
        }
      });
    }

    // 2. Speed Comparison
    const ctxCompSpeed = document.getElementById("chart-compare-speed")?.getContext("2d");
    if (ctxCompSpeed) {
      this.charts.compareSpeed = new window.Chart(ctxCompSpeed, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: `Lap ${comparisonData.lap1} Speed (km/h)`,
              data: data.map(d => d.speed1),
              borderColor: "#00e676",
              borderWidth: 2,
              pointRadius: 0
            },
            {
              label: `Lap ${comparisonData.lap2} Speed (km/h)`,
              data: data.map(d => d.speed2),
              borderColor: "#00d4ff",
              borderWidth: 2,
              borderDash: [5, 3],
              pointRadius: 0
            }
          ]
        },
        options: commonOptions
      });
    }

    // 3. Pedals Comparison
    const ctxCompPedals = document.getElementById("chart-compare-pedals")?.getContext("2d");
    if (ctxCompPedals) {
      this.charts.comparePedals = new window.Chart(ctxCompPedals, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: `Lap ${comparisonData.lap1} Throttle (%)`,
              data: data.map(d => Math.round(d.throttle1 * 100)),
              borderColor: "#00e676",
              borderWidth: 1.5,
              pointRadius: 0
            },
            {
              label: `Lap ${comparisonData.lap2} Throttle (%)`,
              data: data.map(d => Math.round(d.throttle2 * 100)),
              borderColor: "#00d4ff",
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 0
            },
            {
              label: `Lap ${comparisonData.lap1} Brake (%)`,
              data: data.map(d => Math.round(d.brake1 * 100)),
              borderColor: "#ff1744",
              borderWidth: 1.5,
              pointRadius: 0
            },
            {
              label: `Lap ${comparisonData.lap2} Brake (%)`,
              data: data.map(d => Math.round(d.brake2 * 100)),
              borderColor: "#ffab00",
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 0
            }
          ]
        },
        options: {
          ...commonOptions,
          scales: {
            ...commonOptions.scales,
            y: { ...commonOptions.scales.y, min: 0, max: 100 }
          }
        }
      });
    }
  }
}
