from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, degrees, log10, pi, radians, sin, sqrt
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Golf Shaft Design Studio", version="1.0")


@dataclass
class Material:
    name: str
    e1_pa: float
    e2_pa: float
    g12_pa: float
    nu12: float
    density_kg_m3: float
    cost_per_kg: float


@dataclass
class Ply:
    angle_deg: float
    thickness_m: float


@dataclass
class Segment:
    name: str
    length_m: float
    outer_diameter_m: float
    inner_diameter_m: float
    layup: list[Ply]


MATERIALS: dict[str, Material] = {
    "Mitsubishi MR70": Material("Mitsubishi MR70", 161e9, 8.7e9, 4.5e9, 0.32, 1600.0, 95.0),
    "Toray T1100G": Material("Toray T1100G", 215e9, 8.5e9, 4.2e9, 0.33, 1580.0, 125.0),
    "Hexcel IM7": Material("Hexcel IM7", 276e9, 14.0e9, 5.2e9, 0.31, 1620.0, 140.0),
}

MANUFACTURING_METHODS: dict[str, dict[str, Any]] = {
    "roll_wrapped": {
        "name": "Roll-wrapped prepreg",
        "torsion_factor": 1.0,
        "mass_factor": 1.0,
        "cost_factor": 1.0,
        "note": "Baseline OEM-style flag wrap around mandrel.",
    },
    "tubular_braid": {
        "name": "Seamless tubular braid",
        "torsion_factor": 1.18,
        "mass_factor": 1.04,
        "cost_factor": 1.45,
        "note": "Continuous braided tube with reduced lap-seam/spine behavior.",
    },
    "filament_winding": {
        "name": "Filament winding",
        "torsion_factor": 1.15,
        "mass_factor": 1.02,
        "cost_factor": 1.55,
        "note": "Controlled continuous tow path; excellent symmetry and hoop control.",
    },
    "hybrid_3d": {
        "name": "3D multi-axial hybrid weave",
        "torsion_factor": 1.22,
        "mass_factor": 1.12,
        "cost_factor": 1.8,
        "note": "Z-axis reinforcement for delamination resistance and off-center hit durability.",
    },
    "automated_tape": {
        "name": "Automated tape winding",
        "torsion_factor": 1.2,
        "mass_factor": 0.92,
        "cost_factor": 1.7,
        "note": "Variable-angle tow/tape placement with local wall-thickness steering.",
    },
}

ZONE_STATIONS_IN = [41, 36, 31, 26, 21, 16, 11]


def default_segments(base_angle: float = 45.0, thickness_m: float = 0.000125) -> list[Segment]:
    layup = [
        Ply(0.0, thickness_m),
        Ply(base_angle, thickness_m),
        Ply(-base_angle, thickness_m),
        Ply(0.0, thickness_m),
    ]
    return [
        Segment("Butt", 0.254, 0.0150, 0.0130, layup.copy()),
        Segment("Upper mid", 0.254, 0.0130, 0.0110, layup.copy()),
        Segment("Lower mid", 0.254, 0.0110, 0.0090, layup.copy()),
        Segment("Tip", 0.254, 0.0090, 0.0070, layup.copy()),
    ]


def area_moment_i(od: float, id_: float) -> float:
    return (pi / 64.0) * (od**4 - id_**4)


def polar_moment_j(od: float, id_: float) -> float:
    return (pi / 32.0) * (od**4 - id_**4)


def transformed_modulus(material: Material, angle_deg: float) -> float:
    angle = radians(angle_deg)
    c = cos(angle)
    s = sin(angle)
    return (
        material.e1_pa * c**4
        + material.e2_pa * s**4
        + (2.0 * material.g12_pa + material.nu12 * material.e1_pa) * s**2 * c**2
    )


def effective_modulus(segment: Segment, material: Material) -> float:
    total = sum(p.thickness_m for p in segment.layup)
    if total <= 0:
        return material.e1_pa
    return sum(transformed_modulus(material, p.angle_deg) * p.thickness_m for p in segment.layup) / total


def segment_ei(segment: Segment, material: Material) -> float:
    return effective_modulus(segment, material) * area_moment_i(
        segment.outer_diameter_m, segment.inner_diameter_m
    )


def total_length(segments: list[Segment]) -> float:
    return sum(s.length_m for s in segments)


def average_ei(segments: list[Segment], material: Material) -> float:
    length = total_length(segments)
    return sum(segment_ei(s, material) * s.length_m for s in segments) / length


def shaft_mass_kg(segments: list[Segment], material: Material) -> float:
    return sum(
        pi * (s.outer_diameter_m**2 - s.inner_diameter_m**2) / 4.0 * s.length_m * material.density_kg_m3
        for s in segments
    )


def overall_cpm(segments: list[Segment], material: Material, head_weight_g: float) -> float:
    length = total_length(segments)
    ei = average_ei(segments, material)
    return 14.7 * sqrt(ei / ((head_weight_g / 1000.0) * length**3))


def zone_profile(segments: list[Segment], material: Material, profile_weight_g: float = 255.0) -> list[dict[str, float]]:
    ei = average_ei(segments, material)
    return [
        {
            "station_in": float(station),
            "cpm": 8.5 * sqrt(ei / ((profile_weight_g / 1000.0) * (station * 0.0254) ** 3)),
        }
        for station in ZONE_STATIONS_IN
    ]


def tip_deflection_mm(segments: list[Segment], material: Material, load_n: float = 100.0) -> float:
    length = total_length(segments)
    return load_n * length**3 / (3.0 * average_ei(segments, material)) * 1000.0


def torsion_deg(segments: list[Segment], material: Material, torque_nm: float = 15.0, factor: float = 1.0) -> float:
    length = total_length(segments)
    avg_j = sum(polar_moment_j(s.outer_diameter_m, s.inner_diameter_m) * s.length_m for s in segments) / length
    return degrees(torque_nm * length / (avg_j * material.g12_pa * factor))


def natural_frequency_hz(segments: list[Segment], material: Material) -> float:
    length = total_length(segments)
    ei = average_ei(segments, material)
    mass_per_length = shaft_mass_kg(segments, material) / length
    return (1.875**2 / (2.0 * pi * length**2)) * sqrt(ei / mass_per_length)


def fatigue_cycles(stress_pa: float = 180e6, fatigue_limit_pa: float = 450e6) -> float:
    return (fatigue_limit_pa / stress_pa) ** 8.5 * 10000.0


def wrapping_angle_sweep(target_cpm: float) -> dict[str, Any]:
    rows = []
    best = None
    for angle in range(15, 66, 5):
        torsion_index = 1.0 + 0.35 * sin(radians(angle * 2.0))
        cpm = target_cpm + (angle - 45.0) * 0.16
        score = torsion_index - abs(cpm - target_cpm) / 25.0
        row = {"angle_deg": angle, "torsion_index": torsion_index, "estimated_cpm": cpm, "score": score}
        rows.append(row)
        if best is None or score > best["score"]:
            best = row
    return {"best": best, "sweep": rows}


def doe_sweep(base_cpm: float, target_cpm: float) -> list[dict[str, float]]:
    rows = []
    for scale in [0.8, 0.9, 1.0, 1.1, 1.2]:
        cpm = base_cpm * sqrt(scale)
        rows.append({"thickness_scale": scale, "estimated_cpm": cpm, "target_error": cpm - target_cpm})
    return rows


def simulate_launch(cpm: float, head_speed_mph: float) -> dict[str, float]:
    stiffness_delta = cpm - 255.0
    ball_speed = head_speed_mph * 1.45 + stiffness_delta * 0.04
    launch_angle = 13.5 - stiffness_delta * 0.018
    spin_rpm = 2650.0 - stiffness_delta * 8.5
    carry_yards = ball_speed * 1.68 + launch_angle * 2.0 - spin_rpm / 180.0
    return {
        "club_speed_mph": head_speed_mph,
        "ball_speed_mph": ball_speed,
        "launch_angle_deg": launch_angle,
        "spin_rpm": spin_rpm,
        "carry_yards": carry_yards,
    }


def generate_mandrel_gcode(
    segments: list[Segment],
    units: str = "mm",
    rapid_feed: float = 600.0,
    cut_feed: float = 180.0,
    spin_feed: float = 300.0,
    spindle_rpm: int = 1200,
    tool_number: int = 1,
    pass_count: int = 1,
) -> str:
    use_inches = units.lower() in {"inch", "in", "inches"}
    linear_scale = 39.3700787402 if use_inches else 1000.0
    radius_scale = 19.6850393701 if use_inches else 500.0
    unit_code = "G20" if use_inches else "G21"
    unit_label = "inches" if use_inches else "millimeters"
    pass_count = max(1, min(int(pass_count), 8))
    tool_number = max(1, int(tool_number))
    spindle_rpm = max(0, int(spindle_rpm))
    rapid_feed = max(1.0, float(rapid_feed))
    cut_feed = max(1.0, float(cut_feed))
    spin_feed = max(1.0, float(spin_feed))

    lines = [
        f"{unit_code} ; units in {unit_label}",
        "G90 ; absolute positioning",
        "G17 ; XY plane selection",
        f"T{tool_number} M06 ; mandrel turning / contour tool",
        f"S{spindle_rpm} M03 ; spindle on clockwise",
        f"G0 X0.000 Z0.000 F{rapid_feed:.1f}",
        "; Golf shaft tapered mandrel envelope",
    ]
    z_pos = 0.0
    for index, segment in enumerate(segments, start=1):
        start_radius = segment.outer_diameter_m * radius_scale
        z_next = z_pos + segment.length_m * linear_scale
        end_radius = segment.outer_diameter_m * radius_scale
        if index < len(segments):
            end_radius = segments[index].outer_diameter_m * radius_scale
        lines.extend([f"; Segment {index}: {segment.name}", f"G0 Z{z_pos:.3f} F{rapid_feed:.1f}"])
        for pass_index in range(1, pass_count + 1):
            stock_allowance = (pass_count - pass_index) * (0.08 if not use_inches else 0.003)
            pass_start_radius = start_radius + stock_allowance
            pass_end_radius = end_radius + stock_allowance
            lines.extend(
                [
                    f"; Pass {pass_index} of {pass_count}",
                    f"G1 X{pass_start_radius:.3f} F{spin_feed:.1f}",
                    f"G1 Z{z_next:.3f} X{pass_end_radius:.3f} F{cut_feed:.1f}",
                ]
            )
        lines.append(f"G2 I-{end_radius:.3f} J0.000 F{spin_feed:.1f} ; verification spin pass")
        z_pos = z_next
    lines.extend(
        [
            "M05 ; spindle stop",
            "G0 X0.000",
            "M30 ; program end",
        ]
    )
    return "\n".join(lines)


def analyze_shaft(
    target_cpm: float = 255.0,
    head_weight_g: float = 205.0,
    material_name: str = "Mitsubishi MR70",
    method_key: str = "roll_wrapped",
    wrap_angle_deg: float = 45.0,
    head_speed_mph: float = 105.0,
    gcode_units: str = "mm",
    gcode_rapid_feed: float = 600.0,
    gcode_cut_feed: float = 180.0,
    gcode_spin_feed: float = 300.0,
    gcode_spindle_rpm: int = 1200,
    gcode_tool_number: int = 1,
    gcode_pass_count: int = 1,
) -> dict[str, Any]:
    material = MATERIALS.get(material_name, MATERIALS["Mitsubishi MR70"])
    method = MANUFACTURING_METHODS.get(method_key, MANUFACTURING_METHODS["roll_wrapped"])
    segments = default_segments(base_angle=wrap_angle_deg)
    cpm = overall_cpm(segments, material, head_weight_g)
    mass = shaft_mass_kg(segments, material) * method["mass_factor"]
    cost = mass * material.cost_per_kg * method["cost_factor"]
    torsion = torsion_deg(segments, material, factor=method["torsion_factor"])
    zones = zone_profile(segments, material)
    fatigue = fatigue_cycles()
    return {
        "inputs": {
            "target_cpm": target_cpm,
            "head_weight_g": head_weight_g,
            "material": material_name,
            "manufacturing_method": method_key,
            "wrap_angle_deg": wrap_angle_deg,
            "head_speed_mph": head_speed_mph,
        },
        "gcode_settings": {
            "units": gcode_units,
            "rapid_feed": gcode_rapid_feed,
            "cut_feed": gcode_cut_feed,
            "spin_feed": gcode_spin_feed,
            "spindle_rpm": gcode_spindle_rpm,
            "tool_number": gcode_tool_number,
            "pass_count": gcode_pass_count,
        },
        "overall_cpm": cpm,
        "cpm_error": cpm - target_cpm,
        "mass_g": mass * 1000.0,
        "material_cost_usd": cost,
        "tip_deflection_mm_100n": tip_deflection_mm(segments, material),
        "torsion_deflection_deg_15nm": torsion,
        "natural_frequency_hz": natural_frequency_hz(segments, material),
        "fatigue_cycles_estimate": fatigue,
        "damage_index": min(0.99, 1.0 / max(log10(fatigue), 1.0)),
        "zone_profile": zones,
        "ei_profile": [
            {
                "segment": s.name,
                "ei_nm2": segment_ei(s, material),
                "effective_modulus_gpa": effective_modulus(s, material) / 1e9,
                "outer_diameter_mm": s.outer_diameter_m * 1000.0,
            }
            for s in segments
        ],
        "taper_ratios": [
            {
                "from": segments[i].name,
                "to": segments[i + 1].name,
                "outer_diameter_ratio": segments[i + 1].outer_diameter_m / segments[i].outer_diameter_m,
            }
            for i in range(len(segments) - 1)
        ],
        "modal": {
            "first_natural_frequency_hz": natural_frequency_hz(segments, material),
            "resonance_margin_hz": natural_frequency_hz(segments, material) - 15.2,
        },
        "launch_simulation": simulate_launch(cpm, head_speed_mph),
        "gcode": generate_mandrel_gcode(
            segments,
            units=gcode_units,
            rapid_feed=gcode_rapid_feed,
            cut_feed=gcode_cut_feed,
            spin_feed=gcode_spin_feed,
            spindle_rpm=gcode_spindle_rpm,
            tool_number=gcode_tool_number,
            pass_count=gcode_pass_count,
        ),
        "doe_sweep": doe_sweep(cpm, target_cpm),
        "wrapping_angle_optimization": wrapping_angle_sweep(target_cpm),
        "manufacturing_method": method,
        "experimental_library": MANUFACTURING_METHODS,
        "materials": {name: asdict(value) for name, value in MATERIALS.items()},
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
    body { margin: 0; font-family: Arial, sans-serif; background: #dfe6e3; color: #17211f; }
    header { background: #17211f; color: white; padding: 14px 18px; border-bottom: 4px solid #17695f; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    header p { margin: 6px 0 0; color: #c8d8d4; }
    main { display: grid; grid-template-columns: 340px 1fr; gap: 0; min-height: calc(100vh - 78px); }
    section { background: #f8fbfa; border-right: 1px solid #b9c8c4; padding: 16px; }
    section.workspace { background: #eef2f0; border-right: 0; padding: 0; }
    .workspace-head { display: flex; justify-content: space-between; align-items: center; background: #ffffff; border-bottom: 1px solid #cdd9d6; padding: 12px 14px; }
    .workspace-title { font-size: 18px; font-weight: 700; }
    .tabs { display: flex; gap: 6px; }
    .tab { width: auto; margin: 0; padding: 8px 12px; background: #d7e2df; color: #17211f; border: 1px solid #b9c8c4; border-radius: 6px; }
    .tab.active { background: #17695f; color: white; }
    .view { padding: 16px; }
    .hidden { display: none; }
    label { display: block; margin-top: 12px; font-size: 13px; font-weight: 700; }
    input, select, button { width: 100%; box-sizing: border-box; padding: 10px; margin-top: 5px; border: 1px solid #b9c8c4; border-radius: 6px; font-size: 15px; }
    button { border: 0; background: #17695f; color: white; font-weight: 700; cursor: pointer; margin-top: 16px; }
    button.secondary { background: #4d5f5b; }
    button.clicked { background: #d9911f; color: #17211f; }
    .mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .panel-title { margin-top: 18px; padding-top: 14px; border-top: 1px solid #dbe4e1; font-size: 16px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; }
    .card { background: #eef5f3; border-radius: 8px; padding: 12px; }
    .card span { display: block; font-size: 12px; color: #50615e; }
    .card strong { display: block; margin-top: 5px; font-size: 22px; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { border-bottom: 1px solid #e3ebe8; padding: 8px; text-align: left; }
    th { color: #50615e; font-size: 13px; }
    canvas { width: 100%; height: 230px; border: 1px solid #cbd8d5; border-radius: 6px; margin-top: 10px; background: white; }
    .drawing-canvas { height: 420px; background: #101918; border-color: #344642; }
    .flag-canvas { height: 520px; background: #101918; border-color: #344642; }
    .cad-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
    .cad-chip { background: #17211f; color: #d7fff6; padding: 10px; border-radius: 6px; font-size: 13px; }
    .cad-chip strong { display: block; color: white; font-size: 18px; margin-top: 4px; }
    .tool-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0; }
    .tool-row button { margin-top: 0; }
    .editable-table input { margin: 0; padding: 6px; font-size: 13px; }
    .editable-table button { margin: 0; padding: 6px; }
    pre { background: #17211f; color: #d7fff6; padding: 12px; border-radius: 8px; max-height: 300px; overflow: auto; }
    @media (max-width: 900px) { main, .grid2 { grid-template-columns: 1fr; } .metrics { grid-template-columns: 1fr 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Golf Shaft Design Studio</h1>
    <p>CPM-first composite shaft design with EI, torsion, fatigue, launch simulation, and experimental weave analysis.</p>
  </header>
  <main>
    <section>
      <h2>Design Inputs</h2>
      <label>Target CPM</label>
      <input id="target" type="number" value="255" step="0.1">
      <label>Head Weight (g)</label>
      <input id="head" type="number" value="205" step="1">
      <label>Club Speed (mph)</label>
      <input id="speed" type="number" value="105" step="1">
      <label>Wrap Angle (degrees)</label>
      <input id="angle" type="number" value="45" step="1">
      <label>Material</label>
      <select id="material">
        <option>Mitsubishi MR70</option>
        <option>Toray T1100G</option>
        <option>Hexcel IM7</option>
      </select>
      <label>Manufacturing Method</label>
      <select id="method">
        <option value="roll_wrapped">Roll-wrapped prepreg</option>
        <option value="tubular_braid">Seamless tubular braid</option>
        <option value="filament_winding">Filament winding</option>
        <option value="hybrid_3d">3D multi-axial hybrid weave</option>
        <option value="automated_tape">Automated tape winding</option>
      </select>
      <h3 class="panel-title">G-Code Settings</h3>
      <label>Units</label>
      <select id="gcodeUnits">
        <option value="mm">Millimeters (G21)</option>
        <option value="inch">Inches (G20)</option>
      </select>
      <div class="mini-grid">
        <div>
          <label>Tool #</label>
          <input id="toolNumber" type="number" value="1" step="1" min="1">
        </div>
        <div>
          <label>Passes</label>
          <input id="passCount" type="number" value="1" step="1" min="1" max="8">
        </div>
      </div>
      <label>Spindle RPM</label>
      <input id="spindleRpm" type="number" value="1200" step="50" min="0">
      <div class="mini-grid">
        <div>
          <label>Rapid Feed</label>
          <input id="rapidFeed" type="number" value="600" step="10" min="1">
        </div>
        <div>
          <label>Cut Feed</label>
          <input id="cutFeed" type="number" value="180" step="10" min="1">
        </div>
      </div>
      <label>Spin Feed</label>
      <input id="spinFeed" type="number" value="300" step="10" min="1">
      <button onclick="run(this)">Analyze Shaft</button>
      <button class="secondary" onclick="downloadJson(this)">Export JSON</button>
      <button class="secondary" onclick="downloadGcode(this)">Export G-Code</button>
      <p><a href="/docs">Developer API tester</a></p>
    </section>
    <section class="workspace">
      <div class="workspace-head">
        <div class="workspace-title">Engineering Workspace</div>
        <div class="tabs">
          <button class="tab active" id="simTab" onclick="showView('simulation')">Simulation</button>
          <button class="tab" id="drawTab" onclick="showView('drawing')">Design / Drawing</button>
          <button class="tab" id="flagTab" onclick="showView('flags')">Flag CAD</button>
        </div>
      </div>
      <div id="simulationView" class="view">
        <div class="metrics">
          <div class="card"><span>Overall CPM</span><strong id="cpm">-</strong></div>
          <div class="card"><span>CPM Error</span><strong id="error">-</strong></div>
          <div class="card"><span>Mass</span><strong id="mass">-</strong></div>
          <div class="card"><span>Torsion</span><strong id="torsion">-</strong></div>
        </div>
        <div class="grid2">
          <div>
            <h3>7-Zone CPM Profile</h3>
            <canvas id="cpmChart" width="640" height="260"></canvas>
            <table><thead><tr><th>Station</th><th>CPM</th></tr></thead><tbody id="zones"></tbody></table>
          </div>
          <div>
            <h3>Trackman-Style Launch Estimate</h3>
            <table><tbody id="launch"></tbody></table>
            <h3>Engineering Analytics</h3>
            <table><tbody id="analytics"></tbody></table>
          </div>
        </div>
        <h3>Experimental / Manufacturing Library</h3>
        <pre id="library"></pre>
        <h3>Mandrel / Taper G-Code</h3>
        <pre id="gcode"></pre>
      </div>
      <div id="drawingView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Length<strong id="drawLength">-</strong></div>
          <div class="cad-chip">Butt OD<strong id="drawButt">-</strong></div>
          <div class="cad-chip">Tip OD<strong id="drawTip">-</strong></div>
          <div class="cad-chip">Selected Tool<strong id="drawTool">-</strong></div>
        </div>
        <h3>Composite Shaft Drawing</h3>
        <canvas class="drawing-canvas" id="designCanvas" width="1100" height="420"></canvas>
        <div class="grid2">
          <div>
            <h3>Drawing Dimensions</h3>
            <table><thead><tr><th>Feature</th><th>Value</th></tr></thead><tbody id="drawingDims"></tbody></table>
          </div>
          <div>
            <h3>Segment Schedule</h3>
            <table><thead><tr><th>Section</th><th>OD</th><th>EI</th></tr></thead><tbody id="segmentSchedule"></tbody></table>
          </div>
        </div>
      </div>
      <div id="flagView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Flags<strong id="flagCount">-</strong></div>
          <div class="cad-chip">Total Area<strong id="flagArea">-</strong></div>
          <div class="cad-chip">Longest Flag<strong id="flagLongest">-</strong></div>
          <div class="cad-chip">Export<strong>SVG</strong></div>
        </div>
        <h3>Prepreg Flag Drawing Board</h3>
        <canvas class="flag-canvas" id="flagCanvas" width="1200" height="520"></canvas>
        <div class="tool-row">
          <button onclick="addFlag(this)">Add Flag</button>
          <button class="secondary" onclick="resetFlags(this)">Reset Flags</button>
          <button class="secondary" onclick="downloadFlagJson(this)">Export Flag JSON</button>
          <button class="secondary" onclick="downloadFlagSvg(this)">Export Flag SVG</button>
        </div>
        <h3>Editable Flag Dimensions</h3>
        <table class="editable-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Length mm</th>
              <th>Root width mm</th>
              <th>Tip width mm</th>
              <th>Fiber angle</th>
              <th>Station</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="flagRows"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    let latest = null;
    let flags = defaultFlags();

    function defaultFlags() {
      return [
        {name: 'Butt 0deg', length: 420, root: 92, tip: 74, angle: 0, station: 'Butt'},
        {name: 'Bias +45', length: 360, root: 78, tip: 58, angle: 45, station: 'Mid'},
        {name: 'Bias -45', length: 360, root: 78, tip: 58, angle: -45, station: 'Mid'},
        {name: 'Tip 0deg', length: 300, root: 55, tip: 36, angle: 0, station: 'Tip'}
      ];
    }

    function showView(viewName) {
      const simulation = document.getElementById('simulationView');
      const drawing = document.getElementById('drawingView');
      const flagView = document.getElementById('flagView');
      const simTab = document.getElementById('simTab');
      const drawTab = document.getElementById('drawTab');
      const flagTab = document.getElementById('flagTab');
      simulation.classList.toggle('hidden', viewName !== 'simulation');
      drawing.classList.toggle('hidden', viewName !== 'drawing');
      flagView.classList.toggle('hidden', viewName !== 'flags');
      simTab.classList.toggle('active', viewName === 'simulation');
      drawTab.classList.toggle('active', viewName === 'drawing');
      flagTab.classList.toggle('active', viewName === 'flags');
      if (viewName === 'drawing' && latest) drawDesign(latest);
      if (viewName === 'flags') renderFlagEditor();
    }

    function flashButton(button, label) {
      if (!button) return;
      const original = button.textContent;
      button.classList.add('clicked');
      if (label) button.textContent = label;
      setTimeout(() => {
        button.classList.remove('clicked');
        button.textContent = original;
      }, 900);
    }

    async function run(button) {
      flashButton(button, 'Analyzing...');
      const params = new URLSearchParams({
        target_cpm: document.getElementById('target').value,
        head_weight_g: document.getElementById('head').value,
        material_name: document.getElementById('material').value,
        method_key: document.getElementById('method').value,
        wrap_angle_deg: document.getElementById('angle').value,
        head_speed_mph: document.getElementById('speed').value,
        gcode_units: document.getElementById('gcodeUnits').value,
        gcode_rapid_feed: document.getElementById('rapidFeed').value,
        gcode_cut_feed: document.getElementById('cutFeed').value,
        gcode_spin_feed: document.getElementById('spinFeed').value,
        gcode_spindle_rpm: document.getElementById('spindleRpm').value,
        gcode_tool_number: document.getElementById('toolNumber').value,
        gcode_pass_count: document.getElementById('passCount').value
      });
      const res = await fetch('/api/analyze?' + params.toString());
      latest = await res.json();

      document.getElementById('cpm').textContent = latest.overall_cpm.toFixed(1);
      document.getElementById('error').textContent = latest.cpm_error.toFixed(1);
      document.getElementById('mass').textContent = latest.mass_g.toFixed(1) + ' g';
      document.getElementById('torsion').textContent = latest.torsion_deflection_deg_15nm.toFixed(1) + ' deg';

      document.getElementById('zones').innerHTML = latest.zone_profile.map(
        z => `<tr><td>${z.station_in}"</td><td>${z.cpm.toFixed(1)}</td></tr>`
      ).join('');

      const launch = latest.launch_simulation;
      document.getElementById('launch').innerHTML = [
        ['Club Speed', launch.club_speed_mph.toFixed(1) + ' mph'],
        ['Ball Speed', launch.ball_speed_mph.toFixed(1) + ' mph'],
        ['Launch Angle', launch.launch_angle_deg.toFixed(1) + ' deg'],
        ['Spin', launch.spin_rpm.toFixed(0) + ' rpm'],
        ['Carry', launch.carry_yards.toFixed(1) + ' yd']
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');

      document.getElementById('analytics').innerHTML = [
        ['Tip Deflection @100N', latest.tip_deflection_mm_100n.toFixed(1) + ' mm'],
        ['Natural Frequency', latest.natural_frequency_hz.toFixed(2) + ' Hz'],
        ['Fatigue Cycles', latest.fatigue_cycles_estimate.toExponential(2)],
        ['Material Cost', '$' + latest.material_cost_usd.toFixed(2)],
        ['Best Wrap Angle', latest.wrapping_angle_optimization.best.angle_deg + ' deg']
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');

      document.getElementById('library').textContent = JSON.stringify({
        selected_method: latest.manufacturing_method,
        taper_ratios: latest.taper_ratios,
        doe_sweep: latest.doe_sweep,
        ei_profile: latest.ei_profile
      }, null, 2);
      document.getElementById('gcode').textContent = latest.gcode;

      drawChart(latest.zone_profile);
      drawDesign(latest);
      renderFlagEditor();
    }

    function drawChart(profile) {
      const canvas = document.getElementById('cpmChart');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const pad = 34;
      const max = Math.max(...profile.map(p => p.cpm));
      const min = Math.min(...profile.map(p => p.cpm));
      ctx.strokeStyle = '#d4e0dd';
      ctx.lineWidth = 1;
      for (let i = 0; i < 5; i++) {
        const y = pad + i * (canvas.height - 2 * pad) / 4;
        ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(canvas.width - pad, y); ctx.stroke();
      }
      ctx.strokeStyle = '#17695f';
      ctx.lineWidth = 3;
      ctx.beginPath();
      profile.forEach((p, i) => {
        const x = pad + i * (canvas.width - 2 * pad) / (profile.length - 1);
        const y = canvas.height - pad - (p.cpm - min) / (max - min || 1) * (canvas.height - 2 * pad);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.fillStyle = '#0f3d38';
      profile.forEach((p, i) => {
        const x = pad + i * (canvas.width - 2 * pad) / (profile.length - 1);
        const y = canvas.height - pad - (p.cpm - min) / (max - min || 1) * (canvas.height - 2 * pad);
        ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
        ctx.fillText(p.station_in + '"', x - 10, canvas.height - 10);
      });
    }

    function drawDesign(data) {
      const canvas = document.getElementById('designCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const ei = data.ei_profile;
      const lengthMm = 1016;
      const left = 76;
      const right = canvas.width - 72;
      const centerY = 205;
      const scaleX = (right - left) / lengthMm;
      const maxOd = Math.max(...ei.map(s => s.outer_diameter_mm));
      const radiusScale = 7.0;

      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#243532';
      ctx.lineWidth = 1;
      for (let x = left; x <= right; x += 63.5 * scaleX) {
        ctx.beginPath(); ctx.moveTo(x, 42); ctx.lineTo(x, 350); ctx.stroke();
      }
      for (let y = 65; y <= 345; y += 40) {
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
      }

      const stations = [0, 254, 508, 762, 1016];
      const ods = [15, 13, 11, 9, 7];
      ctx.beginPath();
      stations.forEach((z, i) => {
        const x = left + z * scaleX;
        const y = centerY - ods[i] * radiusScale;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      for (let i = stations.length - 1; i >= 0; i--) {
        const x = left + stations[i] * scaleX;
        const y = centerY + ods[i] * radiusScale;
        ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = '#d7fff6';
      ctx.globalAlpha = 0.88;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#35c7b2';
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.strokeStyle = '#f2b84b';
      ctx.fillStyle = '#f2b84b';
      ctx.lineWidth = 1.5;
      const ZONES = [41, 36, 31, 26, 21, 16, 11];
      ZONES.forEach(station => {
        const x = left + (41 - station) * 25.4 * scaleX;
        ctx.beginPath(); ctx.moveTo(x, 70); ctx.lineTo(x, 340); ctx.stroke();
        ctx.fillText(station + '" CPM', x - 18, 58);
      });

      ctx.fillStyle = '#ffffff';
      ctx.font = '16px Arial';
      ctx.fillText('Side Profile / Mandrel Envelope', left, 28);
      ctx.font = '13px Arial';
      ctx.fillText('Butt', left - 8, centerY + maxOd * radiusScale + 32);
      ctx.fillText('Tip', right - 10, centerY + maxOd * radiusScale + 32);
      ctx.fillText('Total Length: 1016 mm / 40 in', left, 382);
      ctx.fillText('OD Taper: 15 mm butt to 7 mm tip', left + 260, 382);
      ctx.fillText('CPM profiling stations shown in gold', left + 540, 382);

      document.getElementById('drawLength').textContent = '1016 mm';
      document.getElementById('drawButt').textContent = '15.0 mm';
      document.getElementById('drawTip').textContent = '7.0 mm';
      document.getElementById('drawTool').textContent = 'T' + data.gcode_settings.tool_number;
      document.getElementById('drawingDims').innerHTML = [
        ['Overall Length', '1016 mm / 40 in'],
        ['Butt OD', '15.0 mm'],
        ['Tip OD', '7.0 mm'],
        ['Clamp Reference', '5 in'],
        ['Profile Stations', '41, 36, 31, 26, 21, 16, 11 in'],
        ['G-Code Units', data.gcode_settings.units],
        ['Pass Count', data.gcode_settings.pass_count]
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');
      document.getElementById('segmentSchedule').innerHTML = data.ei_profile.map(
        row => `<tr><td>${row.segment}</td><td>${row.outer_diameter_mm.toFixed(1)} mm</td><td>${row.ei_nm2.toExponential(2)}</td></tr>`
      ).join('');
    }

    function renderFlagEditor() {
      document.getElementById('flagRows').innerHTML = flags.map((flag, index) => `
        <tr>
          <td><input value="${flag.name}" onchange="updateFlag(${index}, 'name', this.value)"></td>
          <td><input type="number" value="${flag.length}" step="1" onchange="updateFlag(${index}, 'length', this.value)"></td>
          <td><input type="number" value="${flag.root}" step="1" onchange="updateFlag(${index}, 'root', this.value)"></td>
          <td><input type="number" value="${flag.tip}" step="1" onchange="updateFlag(${index}, 'tip', this.value)"></td>
          <td><input type="number" value="${flag.angle}" step="1" onchange="updateFlag(${index}, 'angle', this.value)"></td>
          <td><input value="${flag.station}" onchange="updateFlag(${index}, 'station', this.value)"></td>
          <td><button class="secondary" onclick="deleteFlag(${index}, this)">Delete</button></td>
        </tr>
      `).join('');
      drawFlags();
    }

    function updateFlag(index, key, value) {
      if (['length', 'root', 'tip', 'angle'].includes(key)) {
        flags[index][key] = Number(value);
      } else {
        flags[index][key] = value;
      }
      drawFlags();
    }

    function addFlag(button) {
      flashButton(button, 'Added');
      flags.push({name: 'New flag', length: 320, root: 70, tip: 48, angle: 0, station: 'Custom'});
      renderFlagEditor();
    }

    function deleteFlag(index, button) {
      flashButton(button, 'Deleted');
      flags.splice(index, 1);
      renderFlagEditor();
    }

    function resetFlags(button) {
      flashButton(button, 'Reset');
      flags = defaultFlags();
      renderFlagEditor();
    }

    function flagPoints(flag, x, y, scale) {
      const length = flag.length * scale;
      const root = flag.root * scale;
      const tip = flag.tip * scale;
      return [
        [x, y - root / 2],
        [x + length, y - tip / 2],
        [x + length, y + tip / 2],
        [x, y + root / 2]
      ];
    }

    function drawDimension(ctx, x1, y1, x2, y2, label) {
      ctx.strokeStyle = '#f2b84b';
      ctx.fillStyle = '#f2b84b';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x1, y1 - 5); ctx.lineTo(x1, y1 + 5); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x2, y2 - 5); ctx.lineTo(x2, y2 + 5); ctx.stroke();
      ctx.fillText(label, (x1 + x2) / 2 - 22, y1 - 8);
    }

    function drawFlags() {
      const canvas = document.getElementById('flagCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#263b37';
      for (let x = 40; x < canvas.width; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, canvas.height - 35); ctx.stroke();
      }
      for (let y = 40; y < canvas.height; y += 40) {
        ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(canvas.width - 30, y); ctx.stroke();
      }

      const maxLength = Math.max(...flags.map(f => f.length), 1);
      const scale = Math.min(1.8, (canvas.width - 180) / maxLength);
      const rowGap = Math.max(78, (canvas.height - 90) / Math.max(flags.length, 1));
      ctx.font = '13px Arial';
      flags.forEach((flag, index) => {
        const y = 72 + index * rowGap;
        const x = 100;
        const points = flagPoints(flag, x, y, scale);
        ctx.beginPath();
        points.forEach((p, i) => {
          if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
        });
        ctx.closePath();
        ctx.fillStyle = index % 2 === 0 ? '#d7fff6' : '#b8e9ff';
        ctx.globalAlpha = 0.82;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#35c7b2';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.strokeStyle = '#ff6f61';
        ctx.beginPath();
        ctx.moveTo(x + 20, y);
        ctx.lineTo(x + Math.cos(flag.angle * Math.PI / 180) * 78, y + Math.sin(flag.angle * Math.PI / 180) * 78);
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.fillText(`${flag.name} | ${flag.station} | ${flag.angle} deg`, x, y - flag.root * scale / 2 - 16);
        drawDimension(ctx, x, y + flag.root * scale / 2 + 18, x + flag.length * scale, y + flag.root * scale / 2 + 18, `${flag.length} mm`);
        ctx.fillStyle = '#f2b84b';
        ctx.fillText(`Root ${flag.root} mm`, x - 82, y);
        ctx.fillText(`Tip ${flag.tip} mm`, x + flag.length * scale + 14, y);
      });

      const totalArea = flags.reduce((sum, f) => sum + ((f.root + f.tip) / 2) * f.length, 0);
      const longest = Math.max(...flags.map(f => f.length), 0);
      document.getElementById('flagCount').textContent = String(flags.length);
      document.getElementById('flagArea').textContent = Math.round(totalArea).toLocaleString() + ' mm2';
      document.getElementById('flagLongest').textContent = longest + ' mm';
    }

    function flagSvgText() {
      const width = 1200;
      const rowGap = 120;
      const height = Math.max(220, 90 + flags.length * rowGap);
      const scale = 1.5;
      const shapes = flags.map((flag, index) => {
        const x = 80;
        const y = 70 + index * rowGap;
        const pts = flagPoints(flag, x, y, scale).map(p => p.join(',')).join(' ');
        return `<polygon points="${pts}" fill="none" stroke="#111" stroke-width="2"/><text x="${x}" y="${y - flag.root * scale / 2 - 10}" font-size="14">${flag.name} ${flag.length}mm root ${flag.root}mm tip ${flag.tip}mm ${flag.angle}deg</text>`;
      }).join('');
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${shapes}</svg>`;
    }

    function downloadFlagJson(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify({flags}, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-flag-dimensions.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function downloadFlagSvg(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([flagSvgText()], {type: 'image/svg+xml'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-flag-drawing.svg';
      a.click();
      URL.revokeObjectURL(url);
    }

    function downloadJson(button) {
      if (!latest) return;
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify(latest, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-design-analysis.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function downloadGcode(button) {
      if (!latest) return;
      flashButton(button, 'Exported');
      const blob = new Blob([latest.gcode], {type: 'text/plain'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-mandrel-toolpath.nc';
      a.click();
      URL.revokeObjectURL(url);
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
def api_analyze(
    target_cpm: float = 255.0,
    head_weight_g: float = 205.0,
    material_name: str = "Mitsubishi MR70",
    method_key: str = "roll_wrapped",
    wrap_angle_deg: float = 45.0,
    head_speed_mph: float = 105.0,
    gcode_units: str = "mm",
    gcode_rapid_feed: float = 600.0,
    gcode_cut_feed: float = 180.0,
    gcode_spin_feed: float = 300.0,
    gcode_spindle_rpm: int = 1200,
    gcode_tool_number: int = 1,
    gcode_pass_count: int = 1,
) -> dict[str, Any]:
    return analyze_shaft(
        target_cpm=target_cpm,
        head_weight_g=head_weight_g,
        material_name=material_name,
        method_key=method_key,
        wrap_angle_deg=wrap_angle_deg,
        head_speed_mph=head_speed_mph,
        gcode_units=gcode_units,
        gcode_rapid_feed=gcode_rapid_feed,
        gcode_cut_feed=gcode_cut_feed,
        gcode_spin_feed=gcode_spin_feed,
        gcode_spindle_rpm=gcode_spindle_rpm,
        gcode_tool_number=gcode_tool_number,
        gcode_pass_count=gcode_pass_count,
    )


@app.get("/api/gcode")
def api_gcode(
    wrap_angle_deg: float = 45.0,
    gcode_units: str = "mm",
    gcode_rapid_feed: float = 600.0,
    gcode_cut_feed: float = 180.0,
    gcode_spin_feed: float = 300.0,
    gcode_spindle_rpm: int = 1200,
    gcode_tool_number: int = 1,
    gcode_pass_count: int = 1,
) -> dict[str, str]:
    return {
        "gcode": generate_mandrel_gcode(
            default_segments(base_angle=wrap_angle_deg),
            units=gcode_units,
            rapid_feed=gcode_rapid_feed,
            cut_feed=gcode_cut_feed,
            spin_feed=gcode_spin_feed,
            spindle_rpm=gcode_spindle_rpm,
            tool_number=gcode_tool_number,
            pass_count=gcode_pass_count,
        )
    }


@app.get("/api/materials")
def api_materials() -> dict[str, Any]:
    return {name: asdict(material) for name, material in MATERIALS.items()}


@app.get("/api/manufacturing-methods")
def api_methods() -> dict[str, Any]:
    return MANUFACTURING_METHODS
