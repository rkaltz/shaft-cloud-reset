from __future__ import annotations

from math import pi, sqrt
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Golf Shaft Design Studio", version="1.0")


def analyze_shaft(target_cpm: float = 255.0, head_weight_g: float = 205.0) -> dict[str, Any]:
    material = {
        "name": "Mitsubishi MR70",
        "e1_pa": 161e9,
        "e2_pa": 8.7e9,
        "g12_pa": 4.5e9,
        "density_kg_m3": 1600.0,
    }
    elements = [
        {"length_m": 0.254, "od_m": 0.015, "id_m": 0.013},
        {"length_m": 0.254, "od_m": 0.013, "id_m": 0.011},
        {"length_m": 0.254, "od_m": 0.011, "id_m": 0.009},
        {"length_m": 0.254, "od_m": 0.009, "id_m": 0.007},
    ]
    length = sum(e["length_m"] for e in elements)
    avg_ei = sum(
        material["e1_pa"] * (pi / 64.0) * (e["od_m"] ** 4 - e["id_m"] ** 4) * e["length_m"]
        for e in elements
    ) / length
    mass_kg = sum(
        pi * (e["od_m"] ** 2 - e["id_m"] ** 2) / 4.0 * e["length_m"] * material["density_kg_m3"]
        for e in elements
    )
    overall_cpm = 14.7 * sqrt(avg_ei / ((head_weight_g / 1000.0) * length**3))
    stations = [41, 36, 31, 26, 21, 16, 11]
    zone_profile = [
        {
            "station_in": station,
            "cpm": 8.5 * sqrt(avg_ei / (0.255 * (station * 0.0254) ** 3)),
        }
        for station in stations
    ]
    return {
        "target_cpm": target_cpm,
        "overall_cpm": overall_cpm,
        "cpm_error": overall_cpm - target_cpm,
        "mass_g": mass_kg * 1000.0,
        "tip_deflection_mm_100n": 100.0 * length**3 / (3.0 * avg_ei) * 1000.0,
        "zone_profile": zone_profile,
        "experimental_methods": [
            "Tubular braid",
            "Filament winding",
            "3D multi-axial hybrid weave",
            "Automated tape winding",
        ],
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
<!doctype html>
<html>
<head>
  <title>Golf Shaft Design Studio</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f4f7f6; color: #17211f; }
    header { background: #0f3d38; color: white; padding: 24px; }
    main { padding: 24px; display: grid; grid-template-columns: 320px 1fr; gap: 18px; }
    section { background: white; border: 1px solid #dbe4e1; border-radius: 8px; padding: 18px; }
    label { display: block; margin-top: 12px; font-weight: bold; }
    input, button { width: 100%; box-sizing: border-box; padding: 10px; margin-top: 6px; }
    button { background: #17695f; color: white; border: 0; border-radius: 6px; font-weight: bold; cursor: pointer; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; }
    .card { background: #eef5f3; border-radius: 8px; padding: 12px; }
    .card strong { display: block; font-size: 22px; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; margin-top: 14px; }
    th, td { border-bottom: 1px solid #e2ebe8; padding: 9px; text-align: left; }
    pre { background: #17211f; color: #d7fff6; padding: 12px; border-radius: 8px; overflow: auto; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } .cards { grid-template-columns: 1fr 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Golf Shaft Design Studio</h1>
    <p>CPM-first cloud prototype for composite golf shaft design.</p>
  </header>
  <main>
    <section>
      <h2>Inputs</h2>
      <label>Target CPM</label>
      <input id="target" type="number" value="255">
      <label>Head Weight (g)</label>
      <input id="head" type="number" value="205">
      <button onclick="run()">Analyze Shaft</button>
      <p><a href="/docs">Developer API tester</a></p>
    </section>
    <section>
      <h2>Results</h2>
      <div class="cards">
        <div class="card">Overall CPM<strong id="cpm">-</strong></div>
        <div class="card">CPM Error<strong id="error">-</strong></div>
        <div class="card">Mass<strong id="mass">-</strong></div>
        <div class="card">Deflection<strong id="deflection">-</strong></div>
      </div>
      <h3>7-Zone CPM Profile</h3>
      <table><thead><tr><th>Station</th><th>CPM</th></tr></thead><tbody id="zones"></tbody></table>
      <h3>Experimental Library</h3>
      <pre id="methods"></pre>
    </section>
  </main>
  <script>
    async function run() {
      const target = document.getElementById('target').value;
      const head = document.getElementById('head').value;
      const res = await fetch(`/api/analyze?target_cpm=${target}&head_weight_g=${head}`);
      const data = await res.json();
      document.getElementById('cpm').textContent = data.overall_cpm.toFixed(1);
      document.getElementById('error').textContent = data.cpm_error.toFixed(1);
      document.getElementById('mass').textContent = data.mass_g.toFixed(1) + ' g';
      document.getElementById('deflection').textContent = data.tip_deflection_mm_100n.toFixed(1) + ' mm';
      document.getElementById('zones').innerHTML = data.zone_profile.map(
        z => `<tr><td>${z.station_in}"</td><td>${z.cpm.toFixed(1)}</td></tr>`
      ).join('');
      document.getElementById('methods').textContent = JSON.stringify(data.experimental_methods, null, 2);
    }
    run();
  </script>
</body>
</html>
"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/analyze")
def api_analyze(target_cpm: float = 255.0, head_weight_g: float = 205.0) -> dict[str, Any]:
    return analyze_shaft(target_cpm=target_cpm, head_weight_g=head_weight_g)

