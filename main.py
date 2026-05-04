from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, degrees, log10, pi, radians, sin, sqrt
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="AE ShaftCAD Studio", version="1.1")


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
    "braid_tape_braid": {
        "name": "Braid-tape-braid hybrid",
        "torsion_factor": 1.26,
        "mass_factor": 1.08,
        "cost_factor": 1.85,
        "note": "Inner braid sleeve, localized UD tape reinforcement, then outer braid consolidation sleeve.",
    },
}

ARCHITECTURE_MODES: dict[str, dict[str, Any]] = {
    "flag_wrap": {
        "name": "Flag wrap",
        "cad_role": "2D prepreg flags wrapped around a tapered mandrel",
        "exports": ["flag_json", "svg", "dxf", "gcode", "step_recipe"],
        "design_objects": ["trapezoid_flag", "triangle_flag", "station_constraint", "fiber_angle"],
    },
    "helical_wrap": {
        "name": "Helical wrap",
        "cad_role": "Continuous tow path with pitch, angle, start station, and end station",
        "exports": ["helix_path_json", "gcode", "step_recipe"],
        "design_objects": ["helix_path", "tow_count", "pitch", "coverage"],
    },
    "tubular_braid": {
        "name": "Tubular braid",
        "cad_role": "Over-under braid sleeve mapped to the shaft taper",
        "exports": ["braid_json", "coverage_report", "step_recipe"],
        "design_objects": ["carrier_count", "braid_angle", "sleeve_zone", "coverage"],
    },
    "hybrid_flag_helix": {
        "name": "Hybrid flag + helix",
        "cad_role": "Conventional flags plus localized spiral reinforcement zones",
        "exports": ["project_json", "dxf", "gcode", "step_recipe"],
        "design_objects": ["flag_stack", "helix_zone", "tip_reinforcement", "butt_reinforcement"],
    },
    "automated_tape": {
        "name": "Automated tape placement",
        "cad_role": "Variable angle tape path with localized wall-thickness control",
        "exports": ["tape_path_json", "gcode", "step_recipe"],
        "design_objects": ["steered_tow", "tape_width", "path_station", "course"],
    },
    "braid_tape_braid": {
        "name": "Braid-tape-braid hybrid",
        "cad_role": "Inner braided sleeve, localized UD tape reinforcement, and outer braided sleeve",
        "exports": ["tape_schedule_json", "braid_stack_report", "gcode", "step_recipe"],
        "design_objects": ["inner_braid", "ud_tape_strip", "bias_tape_strip", "outer_braid", "layer_index"],
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


def generate_cadquery_step_recipe(segments: list[Segment]) -> str:
    rows = [
        {
            "name": segment.name,
            "length_mm": segment.length_m * 1000.0,
            "od_mm": segment.outer_diameter_m * 1000.0,
            "id_mm": segment.inner_diameter_m * 1000.0,
        }
        for segment in segments
    ]
    return f'''"""
ShaftCAD CadQuery STEP recipe.

This script is generated by the ShaftCAD web app. Run it in a Python
environment with cadquery installed to create a STEP mandrel/shaft envelope.

Install locally:
    pip install cadquery

Run:
    python shaftcad_step_recipe.py
"""

import cadquery as cq


SEGMENTS = {rows!r}


def make_shaft_envelope():
    """Create a tapered hollow shaft envelope from section diameters."""
    z = 0.0
    work = cq.Workplane("XY")

    for index, segment in enumerate(SEGMENTS):
        radius = segment["od_mm"] / 2.0
        work = work.workplane(offset=z).circle(radius)
        z += segment["length_mm"]

        if index == len(SEGMENTS) - 1:
            final_radius = segment["od_mm"] / 2.0
            work = work.workplane(offset=z).circle(final_radius)

    solid = work.loft(combine=True)
    return solid


def make_mandrel_core():
    """Create a solid tapered mandrel core using the same OD stations."""
    return make_shaft_envelope()


if __name__ == "__main__":
    shaft = make_shaft_envelope()
    cq.exporters.export(shaft, "shaftcad_shaft_envelope.step")
    cq.exporters.export(make_mandrel_core(), "shaftcad_mandrel_core.step")
    print("Exported shaftcad_shaft_envelope.step and shaftcad_mandrel_core.step")
'''


def analyze_shaft(
    target_cpm: float = 255.0,
    head_weight_g: float = 205.0,
    material_name: str = "Mitsubishi MR70",
    method_key: str = "roll_wrapped",
    wrap_angle_deg: float = 45.0,
    architecture_mode: str = "flag_wrap",
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
    architecture = ARCHITECTURE_MODES.get(architecture_mode, ARCHITECTURE_MODES["flag_wrap"])
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
            "architecture_mode": architecture_mode,
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
        "cadquery_step_recipe": generate_cadquery_step_recipe(segments),
        "doe_sweep": doe_sweep(cpm, target_cpm),
        "wrapping_angle_optimization": wrapping_angle_sweep(target_cpm),
        "manufacturing_method": method,
        "architecture_mode": architecture,
        "architecture_library": ARCHITECTURE_MODES,
        "experimental_library": MANUFACTURING_METHODS,
        "materials": {name: asdict(value) for name, value in MATERIALS.items()},
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
<!doctype html>
<html>
<head>
  <title>AE ShaftCAD Studio</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #dfe6e3; color: #17211f; }
    header { background: #17211f; color: white; padding: 14px 18px; border-bottom: 4px solid #17695f; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    header p { margin: 6px 0 0; color: #c8d8d4; }
    .brand-mark { display: inline-grid; place-items: center; width: 42px; height: 42px; border: 2px solid #d7fff6; border-radius: 6px; font-weight: 900; color: #d7fff6; margin-right: 10px; }
    .brand-row { display: flex; align-items: center; }
    .build-badge { border: 1px solid #4e7f76; color: #d7fff6; padding: 7px 10px; border-radius: 6px; font-size: 12px; white-space: nowrap; }
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
    .flag-canvas { height: 520px; background: #101918; border-color: #344642; cursor: crosshair; }
    .viewer-canvas { height: 520px; background: #f7f8fb; border-color: #cbd8d5; }
    .cad-split { display: grid; grid-template-columns: 280px 1fr 280px; grid-template-rows: 520px 150px; gap: 8px; }
    .viewer-panel { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; }
    .viewer-panel h3 { margin: 6px 0 8px; border-bottom: 1px solid #17211f; padding-bottom: 4px; }
    .viewer-panel label { display: flex; justify-content: space-between; align-items: center; margin: 7px 0; font-weight: 400; }
    .viewer-panel input { width: auto; }
    .link-list button { display: block; width: 100%; text-align: left; background: transparent; color: #005bd1; padding: 3px 0; margin: 0; font-weight: 400; }
    .code-panel textarea { width: 100%; height: 520px; box-sizing: border-box; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; font-family: Consolas, monospace; font-size: 13px; line-height: 1.45; color: #8a005f; background: #fff; }
    .viewport-panel { min-width: 0; }
    .inspector-panel { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 10px; overflow: auto; }
    .inspector-panel h3 { margin: 6px 0 8px; border-bottom: 1px solid #dbe4e1; padding-bottom: 5px; }
    .inspector-panel table { font-size: 12px; }
    .console-panel { grid-column: 1 / 4; background: #151b1a; color: #d7fff6; border-radius: 6px; padding: 10px; overflow: auto; font-family: Consolas, monospace; font-size: 13px; }
    .export-row { display: grid; grid-template-columns: 1fr 90px; gap: 8px; margin-top: 8px; }
    .fit-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .fit-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 12px 0; }
    .cad-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
    .cad-chip { background: #17211f; color: #d7fff6; padding: 10px; border-radius: 6px; font-size: 13px; }
    .cad-chip strong { display: block; color: white; font-size: 18px; margin-top: 4px; }
    .tool-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0; }
    .tool-row button { margin-top: 0; }
    .cad-toolbar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; margin: 10px 0; }
    .cad-tool { background: #243532; color: #d7fff6; border: 1px solid #45615b; padding: 8px; margin: 0; }
    .cad-tool.active { background: #6d2d76; color: white; }
    .sketch-shell { display: grid; grid-template-columns: 72px 1fr 300px; gap: 0; border: 1px solid #344642; background: #050808; }
    .sketch-menu { grid-column: 1 / 4; background: #202020; color: white; padding: 7px 10px; font-family: Georgia, serif; font-weight: 700; }
    .sketch-menu span { margin-right: 18px; }
    .sketch-tools { background: #222; padding: 8px; display: grid; gap: 6px; align-content: start; }
    .sketch-icon { background: #151515; color: #15d61f; border: 1px solid #333; padding: 7px 4px; margin: 0; font-size: 15px; min-height: 32px; }
    .sketch-icon.purple { color: #ff34ff; }
    .sketch-icon.active { outline: 2px solid #d7fff6; }
    .sketch-side { background: #050808; color: #19c8ff; border-left: 1px solid #202020; padding: 12px; font-family: Consolas, monospace; }
    .sketch-side h3 { color: #f2b84b; margin: 8px 0; font-size: 16px; }
    .group-row { display: grid; grid-template-columns: 32px 44px 1fr; gap: 8px; padding: 5px; background: #161616; margin: 4px 0; }
    .ok { color: #00ff41; }
    .sketch-options { display: flex; gap: 14px; align-items: center; margin: 10px 0; font-size: 13px; }
    .sketch-options label { display: flex; gap: 6px; align-items: center; margin: 0; font-weight: 700; }
    .sketch-options input { width: auto; margin: 0; }
    .architecture-panel { display: grid; grid-template-columns: 1.1fr 1fr; gap: 12px; margin: 12px 0; }
    .architecture-card { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; }
    .architecture-card h3 { margin: 0 0 8px; }
    .object-list { display: grid; grid-template-columns: repeat(2, minmax(120px, 1fr)); gap: 6px; }
    .object-token { background: #e7efec; border: 1px solid #c3d1cd; padding: 7px; border-radius: 5px; font-size: 12px; font-weight: 700; }
    .layer-tag { display: inline-block; padding: 2px 7px; border-radius: 999px; color: #101918; font-weight: 700; font-size: 12px; }
    .editable-table input { margin: 0; padding: 6px; font-size: 13px; }
    .editable-table button { margin: 0; padding: 6px; }
    .tape-board { display: grid; grid-template-columns: 1fr 380px; gap: 14px; align-items: start; }
    .tape-canvas { height: 520px; background: #101918; border-color: #344642; }
    .tape-summary { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; }
    .tape-summary h3 { margin-top: 0; }
    .tape-badge { display: inline-block; background: #17211f; color: #d7fff6; padding: 4px 8px; border-radius: 999px; margin: 3px; font-size: 12px; font-weight: 700; }
    .stack-board { display: grid; grid-template-columns: 1fr 420px; gap: 14px; align-items: start; }
    .stack-canvas { height: 520px; background: #101918; border-color: #344642; }
    .stack-layer { display: grid; grid-template-columns: 42px 1fr 76px; gap: 8px; align-items: center; background: #eef5f3; border: 1px solid #cbd8d5; border-radius: 6px; padding: 8px; margin: 7px 0; }
    .stack-layer strong { display: block; }
    .stack-layer span { color: #50615e; font-size: 12px; }
    .stack-layer button { margin: 0; padding: 6px; }
    .stack-summary { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; }
    .stack-summary h3 { margin-top: 0; }
    pre { background: #17211f; color: #d7fff6; padding: 12px; border-radius: 8px; max-height: 300px; overflow: auto; }
    @media (max-width: 900px) { main, .grid2 { grid-template-columns: 1fr; } .metrics { grid-template-columns: 1fr 1fr; } }
  </style>
</head>
<body>
  <header>
    <div class="brand-row">
      <div class="brand-mark">AE</div>
      <div>
        <h1>AE ShaftCAD Studio</h1>
        <p>Physics-driven golf shaft CAD: CPM, EI, fitting, plies, flags, braid paths, mandrels, and manufacturing exports.</p>
      </div>
    </div>
    <div class="build-badge">Prototype CAD kernel: shaft-native</div>
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
        <option value="braid_tape_braid">Braid-tape-braid hybrid</option>
      </select>
      <label>CAD Architecture Mode</label>
      <select id="architectureMode" onchange="updateArchitecturePanel(); drawCad3d();">
        <option value="flag_wrap">Flag wrap</option>
        <option value="helical_wrap">Helical wrap</option>
        <option value="tubular_braid">Tubular braid</option>
        <option value="hybrid_flag_helix">Hybrid flag + helix</option>
        <option value="automated_tape">Automated tape placement</option>
        <option value="braid_tape_braid">Braid-tape-braid hybrid</option>
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
        <div class="workspace-title">AE ShaftCAD Workbench</div>
        <div class="tabs">
          <button class="tab active" id="simTab" onclick="showView('simulation')">Simulation</button>
          <button class="tab" id="fitTab" onclick="showView('fit')">Fit-to-Build</button>
          <button class="tab" id="drawTab" onclick="showView('drawing')">Design / Drawing</button>
          <button class="tab" id="flagTab" onclick="showView('flags')">Flag CAD</button>
          <button class="tab" id="tapeTab" onclick="showView('tape')">TapeCAD</button>
          <button class="tab" id="stackTab" onclick="showView('stack')">StackCAD</button>
          <button class="tab" id="cad3dTab" onclick="showView('cad3d')">3D CAD</button>
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
      <div id="fitView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Workflow<strong>Swing to Shaft</strong></div>
          <div class="cad-chip">Output<strong>Target Profile</strong></div>
          <div class="cad-chip">CAD Link<strong>Apply Build</strong></div>
          <div class="cad-chip">Mode<strong>Prototype</strong></div>
        </div>
        <h3>Fit-to-Build Swing Inputs</h3>
        <div class="fit-grid">
          <div><label>Club Speed (mph)</label><input id="fitSpeed" type="number" value="105" step="1"></div>
          <div><label>Tempo</label><select id="fitTempo"><option>Smooth</option><option selected>Medium</option><option>Aggressive</option></select></div>
          <div><label>Transition</label><select id="fitTransition"><option>Smooth</option><option selected>Medium</option><option>Hard</option></select></div>
          <div><label>Release Timing</label><select id="fitRelease"><option>Early</option><option selected>Mid</option><option>Late</option></select></div>
          <div><label>Current Launch (deg)</label><input id="fitLaunch" type="number" value="13.5" step="0.1"></div>
          <div><label>Current Spin (rpm)</label><input id="fitSpin" type="number" value="2650" step="10"></div>
          <div><label>Miss Pattern</label><select id="fitMiss"><option>Left</option><option selected>Neutral</option><option>Right</option><option>High spin</option><option>Low launch</option></select></div>
          <div><label>Feel Goal</label><select id="fitFeel"><option>Softer load</option><option selected>Stable mid</option><option>Boardy/stout</option></select></div>
          <div><label>Target Weight (g)</label><input id="fitWeight" type="number" value="65" step="1"></div>
        </div>
        <div class="fit-actions">
          <button onclick="runFitToBuild(this)">Generate Shaft Target</button>
          <button class="secondary" onclick="applyFitToCad(this)">Apply to CAD</button>
          <button class="secondary" onclick="downloadFitProfile(this)">Export Fit Profile</button>
        </div>
        <div class="grid2">
          <div>
            <h3>Target Shaft Profile</h3>
            <table><tbody id="fitProfile"></tbody></table>
          </div>
          <div>
            <h3>Build Recommendation</h3>
            <pre id="fitBuild"></pre>
          </div>
        </div>
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
        <h3>Prepreg Flag Constraint Sketcher</h3>
        <div class="sketch-shell">
          <div class="sketch-menu">
            <span>File</span><span>Edit</span><span>View</span><span>New Group</span><span>Sketch</span><span>Constrain</span><span>Analyze</span><span>Help</span>
          </div>
          <div class="sketch-tools">
            <button class="sketch-icon active" onclick="setSketchTool('select', this)">SEL</button>
            <button class="sketch-icon" onclick="setSketchTool('line', this)">LN</button>
            <button class="sketch-icon" onclick="setSketchTool('point', this)">PT</button>
            <button class="sketch-icon purple" onclick="setSketchTool('dimension', this)">DIM</button>
            <button class="sketch-icon purple" onclick="setSketchTool('horizontal', this)">H</button>
            <button class="sketch-icon purple" onclick="setSketchTool('vertical', this)">V</button>
            <button class="sketch-icon purple" onclick="setSketchTool('angle', this)">ANG</button>
            <button class="sketch-icon" onclick="setSketchTool('construction', this)">REF</button>
          </div>
          <canvas class="flag-canvas" id="flagCanvas" width="1020" height="520"
            onmousedown="flagMouseDown(event)" onmousemove="flagMouseMove(event)" onmouseup="flagMouseUp()" onmouseleave="flagMouseUp()"></canvas>
          <div class="sketch-side">
            <div>home &nbsp; in plane: <span class="ok">g002-sketch-in-plane</span></div>
            <h3>active</h3>
            <div class="group-row"><span></span><span>shown</span><span>dof&nbsp;&nbsp;group-name</span></div>
            <div class="group-row"><span>◎</span><span>☑</span><span><span class="ok">ok</span>&nbsp;&nbsp;g001-references</span></div>
            <div class="group-row"><span>⊙</span><span>☑</span><span><span class="ok">ok</span>&nbsp;&nbsp;g002-sketch-in-plane</span></div>
            <h3>constraints</h3>
            <div id="constraintReadout">H: 0 | V: 0 | DIM: 0</div>
            <h3>selection</h3>
            <div id="sideSelection">No flag selected</div>
          </div>
        </div>
        <div class="sketch-options">
          <label><input id="snapGrid" type="checkbox" checked onchange="drawFlags()"> Snap to 5 mm grid</label>
          <label><input id="lockAngle" type="checkbox"> Lock fiber angle while dragging</label>
          <label><input id="lockDimensions" type="checkbox" onchange="drawFlags()"> Lock dimensions</label>
          <span id="selectedFlagLabel">No flag selected</span>
        </div>
        <div class="tool-row">
          <button onclick="addFlag(this)">Add Flag</button>
          <button onclick="addTriangleFlag(this)">Add Triangle</button>
          <button class="secondary" onclick="resetFlags(this)">Reset Flags</button>
          <button class="secondary" onclick="downloadFlagJson(this)">Export Flag JSON</button>
          <button class="secondary" onclick="downloadFlagSvg(this)">Export Flag SVG</button>
          <button class="secondary" onclick="downloadFlagDxf(this)">Export DXF</button>
        </div>
        <div class="tool-row">
          <button class="secondary" onclick="downloadProject(this)">Save Project</button>
          <button class="secondary" onclick="document.getElementById('projectFile').click()">Load Project</button>
          <input id="projectFile" type="file" accept="application/json,.json" style="display:none" onchange="loadProjectFile(event)">
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
              <th>Layer</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="flagRows"></tbody>
        </table>
      </div>
      <div id="tapeView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Module<strong>TapeCAD</strong></div>
          <div class="cad-chip">Tape Count<strong id="tapeCount">-</strong></div>
          <div class="cad-chip">Mass Added<strong id="tapeMass">-</strong></div>
          <div class="cad-chip">CPM Boost<strong id="tapeCpmBoost">-</strong></div>
        </div>
        <h3>Localized Carbon Tape Reinforcement</h3>
        <div class="tape-board">
          <div>
            <canvas class="tape-canvas" id="tapeCanvas" width="1120" height="520"></canvas>
          </div>
          <div class="tape-summary">
            <h3>Braid-Tape-Braid Stack</h3>
            <div id="tapeStackBadges"></div>
            <table><tbody id="tapeSummary"></tbody></table>
            <button onclick="addTape(this)">Add Tape Strip</button>
            <button class="secondary" onclick="addBiasTapePair(this)">Add +/-45 Pair</button>
            <button class="secondary" onclick="resetTapes(this)">Reset TapeCAD</button>
            <button class="secondary" onclick="downloadTapeJson(this)">Export Tape JSON</button>
          </div>
        </div>
        <h3>Editable Tape Schedule</h3>
        <table class="editable-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Start in</th>
              <th>Length mm</th>
              <th>Width mm</th>
              <th>Thickness mm</th>
              <th>Angle</th>
              <th>Layer</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="tapeRows"></tbody>
        </table>
      </div>
      <div id="stackView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Module<strong>StackCAD</strong></div>
          <div class="cad-chip">Layers<strong id="stackLayerCount">-</strong></div>
          <div class="cad-chip">Build Mass<strong id="stackMass">-</strong></div>
          <div class="cad-chip">Process<strong>Braid/Tape/Flag</strong></div>
        </div>
        <h3>Layer Stack / Manufacturing Build Sequence</h3>
        <div class="stack-board">
          <div>
            <canvas class="stack-canvas" id="stackCanvas" width="1120" height="520"></canvas>
          </div>
          <div class="stack-summary">
            <h3>Build Sheet Controls</h3>
            <button onclick="regenerateStack(this)">Regenerate from CAD Objects</button>
            <button class="secondary" onclick="downloadStackJson(this)">Export Stack JSON</button>
            <button class="secondary" onclick="downloadBuildSheet(this)">Export Build Sheet</button>
            <table><tbody id="stackSummary"></tbody></table>
          </div>
        </div>
        <h3>Layer Order</h3>
        <div id="stackRows"></div>
      </div>
      <div id="cad3dView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Model<strong>Composite Shaft</strong></div>
          <div class="cad-chip">Kernel<strong>CadQuery bridge</strong></div>
          <div class="cad-chip">Architecture<strong id="cadArchitectureChip">Flag wrap</strong></div>
          <div class="cad-chip">Export<strong>STEP recipe</strong></div>
        </div>
        <h3>Parametric 3D Shaft / Mandrel Workbench</h3>
        <div class="architecture-panel">
          <div class="architecture-card">
            <h3>Architecture Mode</h3>
            <table><tbody id="architectureReadout"></tbody></table>
          </div>
          <div class="architecture-card">
            <h3>Shaft-Native CAD Objects</h3>
            <div class="object-list" id="architectureObjects"></div>
          </div>
        </div>
        <div class="cad-split">
          <div class="code-panel">
            <textarea id="cadScript" spellcheck="false"></textarea>
          </div>
          <div class="viewport-panel">
            <canvas class="viewer-canvas" id="cad3dCanvas" width="900" height="520"></canvas>
            <div class="export-row">
              <select id="cadExportType">
                <option>JSCAD script</option>
                <option>STEP recipe</option>
                <option>STL recipe</option>
                <option>Mandrel G-code</option>
              </select>
              <button onclick="downloadCadScript(this)">Export</button>
            </div>
          </div>
          <div class="inspector-panel">
            <h3>Options</h3>
            <label>Dark Mode <input id="cadDarkMode" type="checkbox" onchange="drawCad3d()"></label>
            <label>Show Axis <input id="cadShowAxis" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Show Grid <input id="cadShowGrid" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Smooth Render <input id="cadSmooth" type="checkbox" onchange="drawCad3d()"></label>
            <label>Zoom To Fit <input id="cadZoomFit" type="checkbox" onchange="drawCad3d()"></label>
            <h3>Documentation</h3>
            <div class="link-list">
              <button onclick="loadCadExample('shaft')">Shaft Envelope</button>
              <button onclick="loadCadExample('mandrel')">Mandrel Core</button>
              <button onclick="loadCadExample('flags')">Flag Wrap Layout</button>
              <button onclick="loadCadExample('imports')">Import SVG / STL plan</button>
            </div>
            <h3>Examples</h3>
            <div class="link-list">
              <button onclick="loadCadExample('extrusion')">Extrusions</button>
              <button onclick="loadCadExample('hollow')">Hollow Operations</button>
              <button onclick="loadCadExample('parametric')">Parameter Types</button>
            </div>
            <h3>Object Inspector</h3>
            <table><tbody id="cadInspector"></tbody></table>
          </div>
          <div class="console-panel" id="cadConsole">CAD console ready.</div>
        </div>
      </div>
    </section>
  </main>
  <script>
    let latest = null;
    let flags = defaultFlags();
    let tapes = defaultTapes();
    let stackLayers = [];
    let flagGeometry = [];
    let activeDrag = null;
    let selectedFlagIndex = null;
    let sketchTool = 'select';
    let latestFitProfile = null;
    const ARCHITECTURES = {
      flag_wrap: {
        name: 'Flag wrap',
        cadRole: '2D prepreg flags wrapped around a tapered mandrel',
        exports: ['Flag JSON', 'SVG', 'DXF', 'G-code', 'STEP recipe'],
        objects: ['Trapezoid flag', 'Triangle flag', 'Station constraint', 'Fiber angle']
      },
      helical_wrap: {
        name: 'Helical wrap',
        cadRole: 'Continuous tow path with pitch, angle, start station, and end station',
        exports: ['Helix path JSON', 'G-code', 'STEP recipe'],
        objects: ['Helix path', 'Tow count', 'Pitch', 'Coverage']
      },
      tubular_braid: {
        name: 'Tubular braid',
        cadRole: 'Over-under braid sleeve mapped to the shaft taper',
        exports: ['Braid JSON', 'Coverage report', 'STEP recipe'],
        objects: ['Carrier count', 'Braid angle', 'Sleeve zone', 'Coverage']
      },
      hybrid_flag_helix: {
        name: 'Hybrid flag + helix',
        cadRole: 'Conventional flags plus localized spiral reinforcement zones',
        exports: ['Project JSON', 'DXF', 'G-code', 'STEP recipe'],
        objects: ['Flag stack', 'Helix zone', 'Tip reinforcement', 'Butt reinforcement']
      },
      automated_tape: {
        name: 'Automated tape placement',
        cadRole: 'Variable angle tape path with localized wall-thickness control',
        exports: ['Tape path JSON', 'G-code', 'STEP recipe'],
        objects: ['Steered tow', 'Tape width', 'Path station', 'Course']
      },
      braid_tape_braid: {
        name: 'Braid-tape-braid hybrid',
        cadRole: 'Inner braided sleeve, localized UD tape reinforcement, and outer braided sleeve',
        exports: ['Tape schedule JSON', 'Braid stack report', 'G-code', 'STEP recipe'],
        objects: ['Inner braid', 'UD tape strip', 'Bias tape strip', 'Outer braid', 'Layer index']
      }
    };

    window.onerror = function(message, source, line, column) {
      const consolePanel = document.getElementById('cadConsole');
      if (consolePanel) {
        consolePanel.textContent += `\n[APP ERROR] ${message} at ${line}:${column}`;
      }
      return false;
    };

    function defaultFlags() {
      return [
        {name: 'Butt 0deg', length: 420, root: 92, tip: 74, angle: 0, station: 'Butt', layer: 'axial', locked: false},
        {name: 'Bias +45', length: 360, root: 78, tip: 58, angle: 45, station: 'Mid', layer: 'bias', locked: false},
        {name: 'Bias -45', length: 360, root: 78, tip: 58, angle: -45, station: 'Mid', layer: 'bias', locked: false},
        {name: 'Tip 0deg', length: 300, root: 55, tip: 36, angle: 0, station: 'Tip', layer: 'tip', locked: false}
      ];
    }

    function defaultTapes() {
      return [
        {name: 'Butt CPM strip', startIn: 41, length: 260, width: 12, thickness: 0.125, angle: 0, layer: 'between inner braid and outer braid'},
        {name: 'Mid +45 torque tape', startIn: 26, length: 220, width: 10, thickness: 0.125, angle: 45, layer: 'over inner braid'},
        {name: 'Mid -45 torque tape', startIn: 26, length: 220, width: 10, thickness: 0.125, angle: -45, layer: 'over inner braid'},
        {name: 'Tip hoop support', startIn: 16, length: 150, width: 8, thickness: 0.125, angle: 90, layer: 'under outer braid'}
      ];
    }

    function showView(viewName) {
      const simulation = document.getElementById('simulationView');
      const fitView = document.getElementById('fitView');
      const drawing = document.getElementById('drawingView');
      const flagView = document.getElementById('flagView');
      const tapeView = document.getElementById('tapeView');
      const stackView = document.getElementById('stackView');
      const cad3dView = document.getElementById('cad3dView');
      const simTab = document.getElementById('simTab');
      const fitTab = document.getElementById('fitTab');
      const drawTab = document.getElementById('drawTab');
      const flagTab = document.getElementById('flagTab');
      const tapeTab = document.getElementById('tapeTab');
      const stackTab = document.getElementById('stackTab');
      const cad3dTab = document.getElementById('cad3dTab');
      simulation.classList.toggle('hidden', viewName !== 'simulation');
      fitView.classList.toggle('hidden', viewName !== 'fit');
      drawing.classList.toggle('hidden', viewName !== 'drawing');
      flagView.classList.toggle('hidden', viewName !== 'flags');
      tapeView.classList.toggle('hidden', viewName !== 'tape');
      stackView.classList.toggle('hidden', viewName !== 'stack');
      cad3dView.classList.toggle('hidden', viewName !== 'cad3d');
      simTab.classList.toggle('active', viewName === 'simulation');
      fitTab.classList.toggle('active', viewName === 'fit');
      drawTab.classList.toggle('active', viewName === 'drawing');
      flagTab.classList.toggle('active', viewName === 'flags');
      tapeTab.classList.toggle('active', viewName === 'tape');
      stackTab.classList.toggle('active', viewName === 'stack');
      cad3dTab.classList.toggle('active', viewName === 'cad3d');
      if (viewName === 'drawing' && latest) drawDesign(latest);
      if (viewName === 'flags') renderFlagEditor();
      if (viewName === 'tape') renderTapeCad();
      if (viewName === 'stack') renderStackCad();
      if (viewName === 'cad3d') {
        updateArchitecturePanel();
        drawCad3d();
      }
    }

    function setSketchTool(tool, button) {
      sketchTool = tool;
      document.querySelectorAll('.cad-tool, .sketch-icon').forEach(item => item.classList.remove('active'));
      if (button) button.classList.add('active');
      drawFlags();
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
      try {
        flashButton(button, 'Analyzing...');
        const params = new URLSearchParams({
          target_cpm: document.getElementById('target').value,
          head_weight_g: document.getElementById('head').value,
          material_name: document.getElementById('material').value,
          method_key: document.getElementById('method').value,
          wrap_angle_deg: document.getElementById('angle').value,
          architecture_mode: document.getElementById('architectureMode').value,
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
        if (!res.ok) throw new Error(`Analyze API failed: ${res.status}`);
        latest = engineeringWithTape(await res.json());
      } catch (error) {
        writeCadConsole(error.message || String(error));
        return;
      }

      document.getElementById('cpm').textContent = latest.overall_cpm.toFixed(1);
      document.getElementById('error').textContent = latest.cpm_error.toFixed(1);
      document.getElementById('mass').textContent = latest.mass_g.toFixed(1) + ' g';
      document.getElementById('torsion').textContent = latest.torsion_deflection_deg_15nm.toFixed(1) + ' deg';

      document.getElementById('zones').innerHTML = latest.zone_profile.map(
        z => `<tr><td>${z.station_in}"</td><td>${z.cpm.toFixed(1)} <small>+${(z.tape_boost || 0).toFixed(1)}</small></td></tr>`
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
        ['Best Wrap Angle', latest.wrapping_angle_optimization.best.angle_deg + ' deg'],
        ['TapeCAD Mass Added', latest.tape_engineering.estimated_mass_g.toFixed(2) + ' g'],
        ['TapeCAD CPM Boost', '+' + latest.tape_engineering.estimated_cpm_boost.toFixed(1)],
        ['TapeCAD Torque Reduction', '-' + latest.tape_engineering.estimated_torque_reduction_deg.toFixed(2) + ' deg']
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');

      document.getElementById('library').textContent = JSON.stringify({
        selected_method: latest.manufacturing_method,
        selected_architecture: latest.architecture_mode,
        taper_ratios: latest.taper_ratios,
        tape_engineering: latest.tape_engineering,
        doe_sweep: latest.doe_sweep,
        ei_profile: latest.ei_profile
      }, null, 2);
      document.getElementById('gcode').textContent = latest.gcode;

      drawChart(latest.zone_profile);
      drawDesign(latest);
      renderFlagEditor();
      renderTapeCad();
      renderStackCad();
      drawCad3d();
      writeCadConsole('Analysis complete. CadQuery STEP recipe ready for export.');
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

    function fitMultiplier(value, mapping) {
      return mapping[value] || 0;
    }

    function runFitToBuild(button) {
      flashButton(button, 'Generated');
      const speed = Number(document.getElementById('fitSpeed').value);
      const launch = Number(document.getElementById('fitLaunch').value);
      const spin = Number(document.getElementById('fitSpin').value);
      const weight = Number(document.getElementById('fitWeight').value);
      const tempo = document.getElementById('fitTempo').value;
      const transition = document.getElementById('fitTransition').value;
      const release = document.getElementById('fitRelease').value;
      const miss = document.getElementById('fitMiss').value;
      const feel = document.getElementById('fitFeel').value;

      let targetCpm = 235 + speed * 0.22;
      targetCpm += fitMultiplier(tempo, {Smooth: -4, Medium: 0, Aggressive: 5});
      targetCpm += fitMultiplier(transition, {Smooth: -3, Medium: 0, Hard: 6});
      targetCpm += fitMultiplier(release, {Early: -3, Mid: 0, Late: 4});
      targetCpm += fitMultiplier(feel, {'Softer load': -5, 'Stable mid': 0, 'Boardy/stout': 6});
      if (miss === 'Left') targetCpm += 3;
      if (miss === 'Right') targetCpm -= 2;
      if (miss === 'High spin') targetCpm += 4;
      if (miss === 'Low launch') targetCpm -= 4;

      const torqueTarget = Math.max(2.4, 4.2 - (targetCpm - 250) * 0.025 - fitMultiplier(transition, {Hard: 0.35}));
      const launchBias = launch > 15 || spin > 3000 ? 'lower launch / lower spin' : launch < 11 ? 'add launch / smoother tip' : 'neutral launch';
      const wrapAngle = Math.max(28, Math.min(58, 45 + (transition === 'Hard' ? 5 : 0) + (miss === 'Left' ? 4 : 0) - (feel === 'Softer load' ? 5 : 0)));
      const tipBias = launchBias.includes('lower') ? 'stiffen tip section with bias/hoop support' : launchBias.includes('add') ? 'soften tip section and reduce hoop density' : 'balanced tip stiffness';
      const profile = [
        {station: 41, cpm: targetCpm - 18},
        {station: 36, cpm: targetCpm - 10},
        {station: 31, cpm: targetCpm - 3},
        {station: 26, cpm: targetCpm + 2},
        {station: 21, cpm: targetCpm + 8},
        {station: 16, cpm: targetCpm + 15},
        {station: 11, cpm: targetCpm + 24}
      ];

      latestFitProfile = {
        target_cpm: targetCpm,
        target_weight_g: weight,
        torque_target_deg: torqueTarget,
        wrap_angle_deg: wrapAngle,
        launch_bias: launchBias,
        tip_strategy: tipBias,
        zone_profile: profile,
        inputs: {speed, launch, spin, weight, tempo, transition, release, miss, feel}
      };

      document.getElementById('fitProfile').innerHTML = [
        ['Target Overall CPM', targetCpm.toFixed(1)],
        ['Target Weight', weight.toFixed(0) + ' g'],
        ['Torque Target', torqueTarget.toFixed(2) + ' deg'],
        ['Wrap Angle', wrapAngle.toFixed(0) + ' deg'],
        ['Launch Bias', launchBias],
        ['Tip Strategy', tipBias]
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');

      document.getElementById('fitBuild').textContent = JSON.stringify({
        shaft_target: latestFitProfile,
        cad_translation: {
          set_target_cpm: targetCpm,
          set_wrap_angle: wrapAngle,
          flags: [
            '0deg axial butt/mid stability flag',
            `${wrapAngle.toFixed(0)}deg bias flag pair for torque control`,
            tipBias,
            'optional hoop/helix layer if torque target is not met'
          ]
        }
      }, null, 2);
    }

    function applyFitToCad(button) {
      if (!latestFitProfile) runFitToBuild(button);
      flashButton(button, 'Applied');
      document.getElementById('target').value = latestFitProfile.target_cpm.toFixed(1);
      document.getElementById('angle').value = latestFitProfile.wrap_angle_deg.toFixed(0);
      document.getElementById('speed').value = latestFitProfile.inputs.speed;
      flags = [
        {name: 'Fit axial butt', length: 430, root: 94, tip: 78, angle: 0, station: 'Butt', layer: 'axial', locked: false},
        {name: 'Fit bias +', length: 370, root: 80, tip: 52, angle: latestFitProfile.wrap_angle_deg, station: 'Mid', layer: 'bias', locked: false},
        {name: 'Fit bias -', length: 370, root: 80, tip: 52, angle: -latestFitProfile.wrap_angle_deg, station: 'Mid', layer: 'bias', locked: false},
        {name: 'Fit tip tune', length: 300, root: 58, tip: latestFitProfile.launch_bias.includes('lower') ? 42 : 30, angle: 0, station: 'Tip', layer: 'tip', locked: false}
      ];
      renderFlagEditor();
      run();
      writeCadConsole('Applied Fit-to-Build target to CAD model.');
    }

    function downloadFitProfile(button) {
      if (!latestFitProfile) runFitToBuild(button);
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify(latestFitProfile, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-fit-to-build-profile.json';
      a.click();
      URL.revokeObjectURL(url);
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
          <td><input id="flagName${index}" value="${flag.name}" onchange="updateFlag(${index}, 'name', this.value)"></td>
          <td><input id="flagLength${index}" type="number" value="${flag.length}" step="1" onchange="updateFlag(${index}, 'length', this.value)"></td>
          <td><input id="flagRoot${index}" type="number" value="${flag.root}" step="1" onchange="updateFlag(${index}, 'root', this.value)"></td>
          <td><input id="flagTip${index}" type="number" value="${flag.tip}" step="1" onchange="updateFlag(${index}, 'tip', this.value)"></td>
          <td><input id="flagAngle${index}" type="number" value="${flag.angle}" step="1" onchange="updateFlag(${index}, 'angle', this.value)"></td>
          <td><input id="flagStation${index}" value="${flag.station}" onchange="updateFlag(${index}, 'station', this.value)"></td>
          <td><input id="flagLayer${index}" value="${flag.layer || 'ply'}" onchange="updateFlag(${index}, 'layer', this.value)"></td>
          <td><button class="secondary" onclick="deleteFlag(${index}, this)">Delete</button></td>
        </tr>
      `).join('');
      drawFlags();
    }

    function updateFlagTableValues() {
      flags.forEach((flag, index) => {
        const length = document.getElementById(`flagLength${index}`);
        const root = document.getElementById(`flagRoot${index}`);
        const tip = document.getElementById(`flagTip${index}`);
        const angle = document.getElementById(`flagAngle${index}`);
        if (length) length.value = Math.round(flag.length);
        if (root) root.value = Math.round(flag.root);
        if (tip) tip.value = Math.round(flag.tip);
        if (angle) angle.value = Math.round(flag.angle);
      });
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
      flags.push({name: 'New flag', length: 320, root: 70, tip: 48, angle: 0, station: 'Custom', layer: 'custom', locked: false});
      renderFlagEditor();
    }

    function addTriangleFlag(button) {
      flashButton(button, 'Added');
      flags.push({name: 'Triangle bias flag', length: 340, root: 76, tip: 4, angle: 45, station: 'Custom', layer: 'bias', locked: false});
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

    function canvasPoint(event) {
      const canvas = document.getElementById('flagCanvas');
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * canvas.width / rect.width,
        y: (event.clientY - rect.top) * canvas.height / rect.height
      };
    }

    function distance(a, b) {
      return Math.hypot(a.x - b[0], a.y - b[1]);
    }

    function snapValue(value) {
      const snap = document.getElementById('snapGrid');
      return snap && snap.checked ? Math.round(value / 5) * 5 : value;
    }

    function flagMouseDown(event) {
      const point = canvasPoint(event);
      let best = null;
      flagGeometry.forEach((geometry, flagIndex) => {
        geometry.points.forEach((cornerPoint, cornerIndex) => {
          const d = distance(point, cornerPoint);
          if (d < 14 && (!best || d < best.distance)) {
            best = {flagIndex, cornerIndex, distance: d};
          }
        });
      });
      if (best) {
        selectedFlagIndex = best.flagIndex;
        activeDrag = best;
        drawFlags();
        return;
      }
      selectedFlagIndex = null;
      activeDrag = null;
      drawFlags();
    }

    function flagMouseMove(event) {
      if (!activeDrag) return;
      const point = canvasPoint(event);
      const geometry = flagGeometry[activeDrag.flagIndex];
      if (!geometry) return;
      const flag = flags[activeDrag.flagIndex];
      if (document.getElementById('lockDimensions').checked || flag.locked) return;
      const localX = Math.max(40, point.x - geometry.x);
      const localY = Math.abs(point.y - geometry.y);
      if (activeDrag.cornerIndex === 1 || activeDrag.cornerIndex === 2) {
        flag.length = Math.max(60, snapValue(localX / geometry.scale));
        flag.tip = Math.max(8, snapValue((localY * 2) / geometry.scale));
      } else {
        flag.root = Math.max(8, snapValue((localY * 2) / geometry.scale));
      }
      if (!document.getElementById('lockAngle').checked && (activeDrag.cornerIndex === 1 || activeDrag.cornerIndex === 2)) {
        const dy = point.y - geometry.y;
        const dx = Math.max(1, point.x - geometry.x);
        flag.angle = Math.round(Math.atan2(dy, dx) * 180 / Math.PI);
      }
      updateFlagTableValues();
      drawFlags();
    }

    function flagMouseUp() {
      activeDrag = null;
    }

    function drawDimension(ctx, x1, y1, x2, y2, label) {
      ctx.strokeStyle = '#b24ac7';
      ctx.fillStyle = '#b24ac7';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x1, y1 - 5); ctx.lineTo(x1, y1 + 5); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x2, y2 - 5); ctx.lineTo(x2, y2 + 5); ctx.stroke();
      ctx.fillText(label, (x1 + x2) / 2 - 22, y1 - 8);
    }

    function drawConstraintLabel(ctx, text, x, y) {
      ctx.fillStyle = '#b24ac7';
      ctx.font = '700 15px Arial';
      ctx.fillText(text, x, y);
    }

    function layerColor(layer) {
      const colors = {
        axial: '#d7fff6',
        bias: '#b8e9ff',
        tip: '#ffd6a5',
        hoop: '#caffbf',
        custom: '#e0c3fc'
      };
      return colors[(layer || '').toLowerCase()] || '#d7fff6';
    }

    function drawHandle(ctx, x, y, active, selected) {
      ctx.fillStyle = active ? '#ff2d20' : selected ? '#f2b84b' : '#39b76a';
      ctx.strokeStyle = '#10231c';
      ctx.lineWidth = 1.5;
      ctx.fillRect(x - 5, y - 5, 10, 10);
      ctx.strokeRect(x - 5, y - 5, 10, 10);
    }

    function drawFlags() {
      const canvas = document.getElementById('flagCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#163c3a';
      ctx.setLineDash([4, 8]);
      for (let x = 40; x < canvas.width; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, canvas.height - 35); ctx.stroke();
      }
      for (let y = 40; y < canvas.height; y += 40) {
        ctx.beginPath(); ctx.moveTo(30, y); ctx.lineTo(canvas.width - 30, y); ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.strokeStyle = '#2ba7a0';
      ctx.setLineDash([7, 7]);
      ctx.strokeRect(80, 38, canvas.width - 150, canvas.height - 82);
      ctx.beginPath(); ctx.moveTo(60, canvas.height / 2); ctx.lineTo(canvas.width - 50, canvas.height / 2); ctx.stroke();
      ctx.setLineDash([]);

      ctx.strokeStyle = '#8b5a22';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(112, canvas.height - 94);
      ctx.lineTo(canvas.width - 118, canvas.height - 94);
      ctx.lineTo(canvas.width - 118, canvas.height - 64);
      ctx.lineTo(112, canvas.height - 64);
      ctx.closePath();
      ctx.stroke();
      ctx.fillStyle = '#8b5a22';
      ctx.font = '13px Arial';
      ctx.fillText('Mandrel / shaft reference envelope', 116, canvas.height - 104);

      const maxLength = Math.max(...flags.map(f => f.length), 1);
      const scale = Math.min(1.8, (canvas.width - 180) / maxLength);
      const rowGap = Math.max(78, (canvas.height - 90) / Math.max(flags.length, 1));
      flagGeometry = [];
      ctx.font = '13px Arial';
      flags.forEach((flag, index) => {
        const y = 72 + index * rowGap;
        const x = 100;
        const points = flagPoints(flag, x, y, scale);
        flagGeometry.push({x, y, scale, points});
        ctx.setLineDash([7, 7]);
        ctx.strokeStyle = '#2a817c';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + flag.length * scale, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath();
        points.forEach((p, i) => {
          if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
        });
        ctx.closePath();
        ctx.fillStyle = layerColor(flag.layer);
        ctx.globalAlpha = 0.14;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = '#e8efed';
        ctx.lineWidth = 2;
        ctx.stroke();

        if (selectedFlagIndex === index) {
          ctx.strokeStyle = '#b24ac7';
          ctx.lineWidth = 3;
          ctx.stroke();
        }

        points.forEach((p, cornerIndex) => {
          drawHandle(
            ctx,
            p[0],
            p[1],
            activeDrag && activeDrag.flagIndex === index && activeDrag.cornerIndex === cornerIndex,
            selectedFlagIndex === index
          );
        });

        ctx.strokeStyle = '#b24ac7';
        ctx.beginPath();
        ctx.moveTo(x + 20, y);
        ctx.lineTo(x + Math.cos(flag.angle * Math.PI / 180) * 78, y + Math.sin(flag.angle * Math.PI / 180) * 78);
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.fillText(`${flag.name} | ${flag.station} | ${flag.angle} deg`, x, y - flag.root * scale / 2 - 16);
        ctx.fillStyle = layerColor(flag.layer);
        ctx.fillRect(x + flag.length * scale + 14, y - 30, 58, 18);
        ctx.fillStyle = '#101918';
        ctx.fillText(flag.layer || 'ply', x + flag.length * scale + 19, y - 16);
        drawDimension(ctx, x, y + flag.root * scale / 2 + 18, x + flag.length * scale, y + flag.root * scale / 2 + 18, `${flag.length} mm`);
        drawConstraintLabel(ctx, 'H', x + flag.length * scale / 2, y - 8);
        drawConstraintLabel(ctx, 'V', x - 22, y + 5);
        drawConstraintLabel(ctx, 'V', x + flag.length * scale + 10, y + 5);
        ctx.fillStyle = '#b24ac7';
        ctx.fillText(`Root ${flag.root} mm`, x - 82, y);
        ctx.fillText(`Tip ${flag.tip} mm`, x + flag.length * scale + 14, y);
      });

      const totalArea = flags.reduce((sum, f) => sum + ((f.root + f.tip) / 2) * f.length, 0);
      const longest = Math.max(...flags.map(f => f.length), 0);
      document.getElementById('flagCount').textContent = String(flags.length);
      document.getElementById('flagArea').textContent = Math.round(totalArea).toLocaleString() + ' mm2';
      document.getElementById('flagLongest').textContent = longest + ' mm';
      document.getElementById('selectedFlagLabel').textContent =
        selectedFlagIndex === null ? `Tool: ${sketchTool} | No flag selected` : `Tool: ${sketchTool} | Selected: ${flags[selectedFlagIndex].name}`;
      const hCount = flags.length;
      const vCount = flags.length * 2;
      const dimCount = flags.length * 3;
      const constraintReadout = document.getElementById('constraintReadout');
      const sideSelection = document.getElementById('sideSelection');
      if (constraintReadout) constraintReadout.textContent = `H: ${hCount} | V: ${vCount} | DIM: ${dimCount}`;
      if (sideSelection) {
        sideSelection.textContent = selectedFlagIndex === null
          ? `Tool: ${sketchTool}`
          : `${flags[selectedFlagIndex].name} | L ${flags[selectedFlagIndex].length} | root ${flags[selectedFlagIndex].root} | tip ${flags[selectedFlagIndex].tip}`;
      }
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

    function dxfLine(x1, y1, x2, y2, layer) {
      return `0
LINE
8
${layer}
10
${x1.toFixed(3)}
20
${y1.toFixed(3)}
30
0.000
11
${x2.toFixed(3)}
21
${y2.toFixed(3)}
31
0.000`;
    }

    function flagDxfText() {
      const lines = ['0', 'SECTION', '2', 'ENTITIES'];
      flags.forEach((flag, index) => {
        const x = 20;
        const y = 20 + index * 140;
        const pts = [
          [x, y - flag.root / 2],
          [x + flag.length, y - flag.tip / 2],
          [x + flag.length, y + flag.tip / 2],
          [x, y + flag.root / 2]
        ];
        const layer = (flag.layer || 'PLY').toUpperCase();
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i];
          const b = pts[(i + 1) % pts.length];
          lines.push(dxfLine(a[0], a[1], b[0], b[1], layer));
        }
      });
      lines.push('0', 'ENDSEC', '0', 'EOF');
      return lines.join('\n');
    }

    function downloadFlagDxf(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([flagDxfText()], {type: 'application/dxf'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-flag-layout.dxf';
      a.click();
      URL.revokeObjectURL(url);
    }

    function tapeMassGrams() {
      const densityMgMm3 = 0.0016;
      return tapes.reduce((sum, tape) => sum + tape.length * tape.width * tape.thickness * densityMgMm3, 0);
    }

    function tapeCpmBoost() {
      return tapes.reduce((sum, tape) => {
        const angle = Math.abs(Number(tape.angle));
        const directional = angle === 0 ? 1.0 : angle === 90 ? 0.25 : 0.55;
        const stationBias = Number(tape.startIn) >= 31 ? 1.15 : Number(tape.startIn) <= 16 ? 0.8 : 1.0;
        return sum + (tape.length * tape.width * tape.thickness / 1000) * directional * stationBias * 0.42;
      }, 0);
    }

    function tapeTorqueReduction() {
      return tapes.reduce((sum, tape) => {
        const angle = Math.abs(Number(tape.angle));
        const angleFactor = angle === 45 ? 1.0 : angle === 90 ? 0.45 : 0.25;
        return sum + (tape.length * tape.width * tape.thickness / 1000) * angleFactor * 0.08;
      }, 0);
    }

    function tapeStiffnessIndexAtStation(stationIn) {
      return tapes.reduce((sum, tape) => {
        const tapeStart = Number(tape.startIn);
        const tapeEnd = tapeStart - Number(tape.length) / 25.4;
        const inZone = stationIn <= tapeStart && stationIn >= tapeEnd;
        if (!inZone) return sum;
        const angle = Math.abs(Number(tape.angle));
        const directional = angle === 0 ? 1.0 : angle === 90 ? 0.2 : 0.55;
        return sum + (Number(tape.width) * Number(tape.thickness) / 10) * directional;
      }, 0);
    }

    function tapeAdjustedZoneProfile(baseProfile) {
      return baseProfile.map(zone => {
        const localBoost = tapeStiffnessIndexAtStation(Number(zone.station_in));
        return {
          ...zone,
          base_cpm: zone.cpm,
          tape_boost: localBoost,
          cpm: zone.cpm + localBoost
        };
      });
    }

    function engineeringWithTape(base) {
      if (!base) return null;
      const massAdded = tapeMassGrams();
      const cpmBoost = tapeCpmBoost();
      const torqueReduction = tapeTorqueReduction();
      const zones = tapeAdjustedZoneProfile(base.zone_profile);
      const adjustedCpm = base.overall_cpm + cpmBoost;
      const adjustedTorsion = Math.max(0.2, base.torsion_deflection_deg_15nm - torqueReduction);
      const stiffnessRatio = Math.max(0.1, adjustedCpm / Math.max(base.overall_cpm, 1));
      const headSpeed = Number(document.getElementById('speed').value);
      const stiffnessDelta = adjustedCpm - 255;
      const adjustedBallSpeed = headSpeed * 1.45 + stiffnessDelta * 0.04;
      const adjustedLaunch = 13.5 - stiffnessDelta * 0.018;
      const adjustedSpin = 2650 - stiffnessDelta * 8.5;
      const adjustedCarry = adjustedBallSpeed * 1.68 + adjustedLaunch * 2.0 - adjustedSpin / 180.0;
      return {
        ...base,
        base_overall_cpm: base.overall_cpm,
        base_mass_g: base.mass_g,
        base_torsion_deflection_deg_15nm: base.torsion_deflection_deg_15nm,
        base_zone_profile: base.zone_profile,
        overall_cpm: adjustedCpm,
        cpm_error: adjustedCpm - Number(document.getElementById('target').value),
        mass_g: base.mass_g + massAdded,
        torsion_deflection_deg_15nm: adjustedTorsion,
        tip_deflection_mm_100n: base.tip_deflection_mm_100n / stiffnessRatio,
        natural_frequency_hz: base.natural_frequency_hz * Math.sqrt(stiffnessRatio),
        launch_simulation: {
          club_speed_mph: headSpeed,
          ball_speed_mph: adjustedBallSpeed,
          launch_angle_deg: adjustedLaunch,
          spin_rpm: adjustedSpin,
          carry_yards: adjustedCarry
        },
        zone_profile: zones,
        tape_engineering: {
          tape_count: tapes.length,
          estimated_mass_g: massAdded,
          estimated_cpm_boost: cpmBoost,
          estimated_torque_reduction_deg: torqueReduction,
          zone_boosts: zones.map(z => ({station_in: z.station_in, tape_boost: z.tape_boost})),
          tapes
        }
      };
    }

    function refreshTapeEngineering() {
      if (!latest) return;
      latest = engineeringWithTape({
        ...latest,
        overall_cpm: latest.base_overall_cpm || latest.overall_cpm,
        mass_g: latest.base_mass_g || latest.mass_g,
        torsion_deflection_deg_15nm: latest.base_torsion_deflection_deg_15nm || latest.torsion_deflection_deg_15nm,
        zone_profile: latest.base_zone_profile || latest.zone_profile
      });
      updateSimulationFromLatest();
    }

    function updateSimulationFromLatest() {
      if (!latest) return;
      document.getElementById('cpm').textContent = latest.overall_cpm.toFixed(1);
      document.getElementById('error').textContent = latest.cpm_error.toFixed(1);
      document.getElementById('mass').textContent = latest.mass_g.toFixed(1) + ' g';
      document.getElementById('torsion').textContent = latest.torsion_deflection_deg_15nm.toFixed(1) + ' deg';

      document.getElementById('zones').innerHTML = latest.zone_profile.map(
        z => `<tr><td>${z.station_in}"</td><td>${z.cpm.toFixed(1)} <small>+${(z.tape_boost || 0).toFixed(1)}</small></td></tr>`
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
        ['Best Wrap Angle', latest.wrapping_angle_optimization.best.angle_deg + ' deg'],
        ['TapeCAD Mass Added', latest.tape_engineering.estimated_mass_g.toFixed(2) + ' g'],
        ['TapeCAD CPM Boost', '+' + latest.tape_engineering.estimated_cpm_boost.toFixed(1)],
        ['TapeCAD Torque Reduction', '-' + latest.tape_engineering.estimated_torque_reduction_deg.toFixed(2) + ' deg']
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');

      document.getElementById('library').textContent = JSON.stringify({
        selected_method: latest.manufacturing_method,
        selected_architecture: latest.architecture_mode,
        taper_ratios: latest.taper_ratios,
        tape_engineering: latest.tape_engineering,
        doe_sweep: latest.doe_sweep,
        ei_profile: latest.ei_profile
      }, null, 2);
      document.getElementById('gcode').textContent = latest.gcode;

      drawChart(latest.zone_profile);
      drawDesign(latest);
      renderTapeCad();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function renderTapeCad() {
      renderTapeTable();
      drawTapeCad();
    }

    function renderTapeTable() {
      const rows = tapes.map((tape, index) => `
        <tr>
          <td><input id="tapeName${index}" value="${tape.name}" onchange="updateTape(${index})"></td>
          <td><input id="tapeStart${index}" type="number" value="${tape.startIn}" step="1" onchange="updateTape(${index})"></td>
          <td><input id="tapeLength${index}" type="number" value="${tape.length}" step="5" onchange="updateTape(${index})"></td>
          <td><input id="tapeWidth${index}" type="number" value="${tape.width}" step="1" onchange="updateTape(${index})"></td>
          <td><input id="tapeThickness${index}" type="number" value="${tape.thickness}" step="0.025" onchange="updateTape(${index})"></td>
          <td><input id="tapeAngle${index}" type="number" value="${tape.angle}" step="1" onchange="updateTape(${index})"></td>
          <td><input id="tapeLayer${index}" value="${tape.layer}" onchange="updateTape(${index})"></td>
          <td><button class="secondary" onclick="deleteTape(${index}, this)">Delete</button></td>
        </tr>
      `).join('');
      const table = document.getElementById('tapeRows');
      if (table) table.innerHTML = rows;
    }

    function updateTape(index) {
      tapes[index] = {
        name: document.getElementById(`tapeName${index}`).value,
        startIn: Number(document.getElementById(`tapeStart${index}`).value),
        length: Number(document.getElementById(`tapeLength${index}`).value),
        width: Number(document.getElementById(`tapeWidth${index}`).value),
        thickness: Number(document.getElementById(`tapeThickness${index}`).value),
        angle: Number(document.getElementById(`tapeAngle${index}`).value),
        layer: document.getElementById(`tapeLayer${index}`).value
      };
      drawTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function addTape(button) {
      flashButton(button, 'Added');
      tapes.push({name: 'New UD tape strip', startIn: 31, length: 200, width: 10, thickness: 0.125, angle: 0, layer: 'between braid layers'});
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function addBiasTapePair(button) {
      flashButton(button, 'Added');
      tapes.push({name: 'Bias +45 tape', startIn: 21, length: 190, width: 10, thickness: 0.125, angle: 45, layer: 'torque pair'});
      tapes.push({name: 'Bias -45 tape', startIn: 21, length: 190, width: 10, thickness: 0.125, angle: -45, layer: 'torque pair'});
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function deleteTape(index, button) {
      flashButton(button, 'Deleted');
      tapes.splice(index, 1);
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function resetTapes(button) {
      flashButton(button, 'Reset');
      tapes = defaultTapes();
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
    }

    function tapeColor(angle) {
      const abs = Math.abs(Number(angle));
      if (abs === 0) return '#f2b84b';
      if (abs === 45) return '#ff7de9';
      if (abs === 90) return '#86fff2';
      return '#d7fff6';
    }

    function drawTapeCad() {
      const canvas = document.getElementById('tapeCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#163c3a';
      ctx.setLineDash([4, 8]);
      for (let x = 50; x < canvas.width; x += 50) {
        ctx.beginPath(); ctx.moveTo(x, 40); ctx.lineTo(x, canvas.height - 40); ctx.stroke();
      }
      for (let y = 50; y < canvas.height; y += 50) {
        ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(canvas.width - 40, y); ctx.stroke();
      }
      ctx.setLineDash([]);

      const startX = 90;
      const endX = canvas.width - 90;
      const centerY = 250;
      const lengthPx = endX - startX;
      ctx.strokeStyle = '#8b5a22';
      ctx.lineWidth = 5;
      ctx.beginPath(); ctx.moveTo(startX, centerY); ctx.lineTo(endX, centerY); ctx.stroke();
      ctx.fillStyle = '#d7fff6';
      ctx.font = '14px Arial';
      ctx.fillText('Unwrapped shaft tape schedule: butt 41 in -> tip 11 in', startX, 44);

      const stations = [41, 36, 31, 26, 21, 16, 11];
      stations.forEach(station => {
        const t = (41 - station) / 30;
        const x = startX + t * lengthPx;
        ctx.strokeStyle = '#2ba7a0';
        ctx.beginPath(); ctx.moveTo(x, centerY - 92); ctx.lineTo(x, centerY + 92); ctx.stroke();
        ctx.fillStyle = '#d7fff6';
        ctx.fillText(`${station}"`, x - 12, centerY + 118);
      });

      tapes.forEach((tape, index) => {
        const t = Math.max(0, Math.min(1, (41 - tape.startIn) / 30));
        const x = startX + t * lengthPx;
        const w = Math.max(40, tape.length * 0.72);
        const h = Math.max(6, tape.width * 1.6);
        const y = 92 + index * 72;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(Number(tape.angle) * Math.PI / 180 * 0.18);
        ctx.fillStyle = tapeColor(tape.angle);
        ctx.globalAlpha = 0.25;
        ctx.fillRect(0, -h / 2, w, h);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = tapeColor(tape.angle);
        ctx.lineWidth = 2;
        ctx.strokeRect(0, -h / 2, w, h);
        ctx.restore();
        ctx.fillStyle = '#ffffff';
        ctx.fillText(`${tape.name} | ${tape.angle} deg | ${tape.width}mm x ${tape.length}mm`, x, y - h - 10);
      });

      const mass = tapeMassGrams();
      const cpm = tapeCpmBoost();
      const torque = tapeTorqueReduction();
      document.getElementById('tapeCount').textContent = String(tapes.length);
      document.getElementById('tapeMass').textContent = mass.toFixed(2) + ' g';
      document.getElementById('tapeCpmBoost').textContent = '+' + cpm.toFixed(1);
      document.getElementById('tapeStackBadges').innerHTML = [
        'Mandrel',
        'Inner braid',
        'UD tape',
        '+/-45 tape',
        'Outer braid',
        'Cure wrap'
      ].map(item => `<span class="tape-badge">${item}</span>`).join('');
      document.getElementById('tapeSummary').innerHTML = [
        ['Estimated tape mass', mass.toFixed(2) + ' g'],
        ['Estimated CPM boost', '+' + cpm.toFixed(1) + ' CPM'],
        ['Estimated torque reduction', '-' + torque.toFixed(2) + ' deg'],
        ['Recommended architecture', 'Braid-tape-braid hybrid'],
        ['Build role', 'Localized rigidity between braid layers']
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
    }

    function downloadTapeJson(button) {
      flashButton(button, 'Exported');
      const payload = {
        module: 'TapeCAD',
        architecture: 'braid_tape_braid',
        estimated_mass_g: tapeMassGrams(),
        estimated_cpm_boost: tapeCpmBoost(),
        estimated_torque_reduction_deg: tapeTorqueReduction(),
        stack: ['mandrel', 'inner_braid', 'localized_tape', 'outer_braid', 'cure_wrap'],
        tapes
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-tapecad-schedule.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function flagMassEstimate(flag) {
      const area = ((Number(flag.root) + Number(flag.tip)) / 2) * Number(flag.length);
      return area * 0.000125 * 0.0016;
    }

    function layerColorByType(type) {
      const colors = {
        mandrel: '#8b5a22',
        braid: '#86fff2',
        tape: '#f2b84b',
        flag: '#d7fff6',
        hoop: '#caffbf',
        cure: '#ff7de9'
      };
      return colors[type] || '#e0c3fc';
    }

    function generatedStackLayers() {
      const layers = [
        {type: 'mandrel', name: 'Mandrel prep / release system', station: 'full length', angle: '-', mass_g: 0, stiffness: 0, instruction: 'Clean mandrel, apply release system, verify taper and surface finish.'},
        {type: 'braid', name: 'Inner braided sleeve', station: 'full length', angle: '+/-45', mass_g: 7.5, stiffness: 0.9, instruction: 'Install inner braid sleeve over mandrel and align braid angle before compaction.'}
      ];

      tapes.forEach(tape => {
        layers.push({
          type: Math.abs(Number(tape.angle)) === 90 ? 'hoop' : 'tape',
          name: tape.name,
          station: `${tape.startIn}" start, ${tape.length} mm`,
          angle: `${tape.angle} deg`,
          mass_g: Number(tape.length) * Number(tape.width) * Number(tape.thickness) * 0.0016,
          stiffness: tapeStiffnessIndexAtStation(Number(tape.startIn)),
          instruction: `Apply ${tape.width} mm tape at ${tape.angle} degrees, ${tape.layer}.`
        });
      });

      flags.forEach(flag => {
        layers.push({
          type: 'flag',
          name: flag.name,
          station: flag.station,
          angle: `${flag.angle} deg`,
          mass_g: flagMassEstimate(flag),
          stiffness: Math.abs(Number(flag.angle)) === 0 ? 0.8 : 0.45,
          instruction: `Wrap ${flag.name} flag at ${flag.angle} degrees in ${flag.station} section.`
        });
      });

      layers.push(
        {type: 'braid', name: 'Outer braided sleeve', station: 'full length', angle: '+/-45', mass_g: 8.2, stiffness: 1.05, instruction: 'Install outer braid sleeve and consolidate tape/flag stack.'},
        {type: 'cure', name: 'Shrink tape / cure wrap', station: 'full length', angle: 'spiral', mass_g: 0, stiffness: 0, instruction: 'Apply shrink tape, cure per material schedule, cool, extract mandrel, trim, and inspect.'}
      );

      return layers.map((layer, index) => ({...layer, order: index + 1}));
    }

    function ensureStackLayers() {
      if (!stackLayers.length) stackLayers = generatedStackLayers();
      return stackLayers;
    }

    function regenerateStack(button) {
      flashButton(button, 'Generated');
      stackLayers = generatedStackLayers();
      renderStackCad();
    }

    function moveStackLayer(index, direction) {
      const next = index + direction;
      if (next < 0 || next >= stackLayers.length) return;
      const temp = stackLayers[index];
      stackLayers[index] = stackLayers[next];
      stackLayers[next] = temp;
      stackLayers = stackLayers.map((layer, orderIndex) => ({...layer, order: orderIndex + 1}));
      renderStackCad();
    }

    function stackMassGrams() {
      return ensureStackLayers().reduce((sum, layer) => sum + Number(layer.mass_g || 0), 0);
    }

    function stackStiffnessIndex() {
      return ensureStackLayers().reduce((sum, layer) => sum + Number(layer.stiffness || 0), 0);
    }

    function renderStackCad() {
      ensureStackLayers();
      renderStackRows();
      drawStackCad();
    }

    function renderStackRows() {
      const rows = ensureStackLayers().map((layer, index) => `
        <div class="stack-layer">
          <div style="color:${layerColorByType(layer.type)}; font-weight:900;">${layer.order}</div>
          <div>
            <strong>${layer.name}</strong>
            <span>${layer.type} | ${layer.station} | ${layer.angle} | ${Number(layer.mass_g).toFixed(2)} g</span>
          </div>
          <div>
            <button class="secondary" onclick="moveStackLayer(${index}, -1)">Up</button>
            <button class="secondary" onclick="moveStackLayer(${index}, 1)">Down</button>
          </div>
        </div>
      `).join('');
      const container = document.getElementById('stackRows');
      if (container) container.innerHTML = rows;
    }

    function drawStackCad() {
      const canvas = document.getElementById('stackCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const layers = ensureStackLayers();
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#163c3a';
      ctx.setLineDash([4, 8]);
      for (let x = 50; x < canvas.width; x += 50) {
        ctx.beginPath(); ctx.moveTo(x, 40); ctx.lineTo(x, canvas.height - 40); ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.fillStyle = '#d7fff6';
      ctx.font = '14px Arial';
      ctx.fillText('Mandrel outward build sequence', 70, 38);

      const startX = 90;
      const width = canvas.width - 180;
      const layerHeight = Math.min(34, (canvas.height - 100) / Math.max(layers.length, 1));
      layers.forEach((layer, index) => {
        const y = 72 + index * (layerHeight + 7);
        ctx.fillStyle = layerColorByType(layer.type);
        ctx.globalAlpha = 0.2;
        ctx.fillRect(startX, y, width, layerHeight);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = layerColorByType(layer.type);
        ctx.lineWidth = 2;
        ctx.strokeRect(startX, y, width, layerHeight);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(`${layer.order}. ${layer.name}`, startX + 12, y + 21);
        ctx.fillStyle = '#d7fff6';
        ctx.fillText(`${layer.angle} | ${Number(layer.mass_g).toFixed(2)} g`, startX + width - 190, y + 21);
      });

      document.getElementById('stackLayerCount').textContent = String(layers.length);
      document.getElementById('stackMass').textContent = stackMassGrams().toFixed(1) + ' g';
      document.getElementById('stackSummary').innerHTML = [
        ['Total layer count', layers.length],
        ['Estimated layer mass', stackMassGrams().toFixed(2) + ' g'],
        ['Stack stiffness index', stackStiffnessIndex().toFixed(2)],
        ['Tape schedule linked', `${tapes.length} tape strips`],
        ['Flag schedule linked', `${flags.length} flags`]
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
    }

    function stackPayload() {
      return {
        module: 'StackCAD',
        architecture: document.getElementById('architectureMode').value,
        generated_from: ['FlagCAD', 'TapeCAD', 'Braid architecture'],
        estimated_layer_mass_g: stackMassGrams(),
        stiffness_index: stackStiffnessIndex(),
        layers: ensureStackLayers()
      };
    }

    function downloadStackJson(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify(stackPayload(), null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-stackcad-build.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function buildSheetText() {
      const payload = stackPayload();
      const lines = [
        'AE ShaftCAD Studio - Build Sheet',
        `Architecture: ${payload.architecture}`,
        `Estimated layer mass: ${payload.estimated_layer_mass_g.toFixed(2)} g`,
        `Stiffness index: ${payload.stiffness_index.toFixed(2)}`,
        '',
        'Layer sequence:'
      ];
      payload.layers.forEach(layer => {
        lines.push(`${layer.order}. ${layer.name}`);
        lines.push(`   Type: ${layer.type} | Station: ${layer.station} | Angle: ${layer.angle} | Mass: ${Number(layer.mass_g).toFixed(2)} g`);
        lines.push(`   Instruction: ${layer.instruction}`);
      });
      return lines.join('\n');
    }

    function downloadBuildSheet(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([buildSheetText()], {type: 'text/plain'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ae-shaftcad-build-sheet.txt';
      a.click();
      URL.revokeObjectURL(url);
    }

    function currentProject() {
      return {
        version: 1,
        name: 'ShaftCAD project',
        inputs: {
          target_cpm: document.getElementById('target').value,
          head_weight_g: document.getElementById('head').value,
          club_speed_mph: document.getElementById('speed').value,
          wrap_angle_deg: document.getElementById('angle').value,
          architecture_mode: document.getElementById('architectureMode').value,
          material: document.getElementById('material').value,
          manufacturing_method: document.getElementById('method').value
        },
        gcode: latest ? latest.gcode_settings : {},
        flags,
        tapes,
        stack_layers: ensureStackLayers()
      };
    }

    function downloadProject(button) {
      flashButton(button, 'Saved');
      const blob = new Blob([JSON.stringify(currentProject(), null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaftcad-project.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function loadProjectFile(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const project = JSON.parse(reader.result);
        if (project.inputs) {
          document.getElementById('target').value = project.inputs.target_cpm || 255;
          document.getElementById('head').value = project.inputs.head_weight_g || 205;
          document.getElementById('speed').value = project.inputs.club_speed_mph || 105;
          document.getElementById('angle').value = project.inputs.wrap_angle_deg || 45;
          if (project.inputs.architecture_mode) document.getElementById('architectureMode').value = project.inputs.architecture_mode;
          document.getElementById('material').value = project.inputs.material || 'Mitsubishi MR70';
          document.getElementById('method').value = project.inputs.manufacturing_method || 'roll_wrapped';
        }
        if (Array.isArray(project.flags)) {
          flags = project.flags;
          renderFlagEditor();
        }
        if (Array.isArray(project.tapes)) {
          tapes = project.tapes;
          renderTapeCad();
        }
        if (Array.isArray(project.stack_layers)) {
          stackLayers = project.stack_layers;
          renderStackCad();
        }
        run();
      };
      reader.readAsText(file);
      event.target.value = '';
    }

    function shaftCadScript() {
      const angle = document.getElementById('angle').value;
      const units = latest ? latest.gcode_settings.units : 'mm';
      const architecture = selectedArchitecture();
      return `"use strict"
const jscad = require('@jscad/modeling')
const { cylinder } = jscad.primitives
const { colorize } = jscad.colors

// AE ShaftCAD parametric mandrel envelope
// Units: ${units}
// Wrap angle: ${angle} degrees
// Architecture mode: ${architecture.name}
// CAD role: ${architecture.cadRole}
const segments = [
  { name: 'Butt', length: 254, od: 15, id: 13 },
  { name: 'Upper mid', length: 254, od: 13, id: 11 },
  { name: 'Lower mid', length: 254, od: 11, id: 9 },
  { name: 'Tip', length: 254, od: 9, id: 7 }
]

function main() {
  // Render service preview uses drawing math.
  // STEP recipe export uses CadQuery/OpenCASCADE for manufacturing geometry.
  // Shaft-native objects: ${architecture.objects.join(', ')}
  return colorize([0.2, 0.75, 0.66], cylinder({ radius: 7.5, height: 1016 }))
}

module.exports = { main }`;
    }

    function cadQueryStepRecipe() {
      if (latest && latest.cadquery_step_recipe) return latest.cadquery_step_recipe;
      return `'''
ShaftCAD CadQuery STEP recipe.
Run this in a Python environment with cadquery installed.
'''

import cadquery as cq

SEGMENTS = [
    {"name": "Butt", "length_mm": 254, "od_mm": 15, "id_mm": 13},
    {"name": "Upper mid", "length_mm": 254, "od_mm": 13, "id_mm": 11},
    {"name": "Lower mid", "length_mm": 254, "od_mm": 11, "id_mm": 9},
    {"name": "Tip", "length_mm": 254, "od_mm": 9, "id_mm": 7},
]

def make_shaft_envelope():
    z = 0
    work = cq.Workplane("XY")
    for index, segment in enumerate(SEGMENTS):
        work = work.workplane(offset=z).circle(segment["od_mm"] / 2)
        z += segment["length_mm"]
        if index == len(SEGMENTS) - 1:
            work = work.workplane(offset=z).circle(segment["od_mm"] / 2)
    return work.loft(combine=True)

if __name__ == "__main__":
    cq.exporters.export(make_shaft_envelope(), "shaftcad_shaft_envelope.step")
`;
    }

    function loadCadExample(kind) {
      const examples = {
        shaft: shaftCadScript(),
        mandrel: `"use strict"
// Mandrel core recipe
// 1. Build tapered cone segments from butt to tip.
// 2. Join sections into a continuous tool body.
// 3. Export STEP for machining or STL for checking.
const mandrel = [
  { z: 0, od: 15 },
  { z: 254, od: 13 },
  { z: 508, od: 11 },
  { z: 762, od: 9 },
  { z: 1016, od: 7 }
]`,
        flags: JSON.stringify({ flags }, null, 2),
        imports: `// Import plan
// SVG: flat prepreg flag drawings
// STL: visual checking and fixture mockup
// STEP: manufacturing-grade mandrel and shaft envelope
// DXF: next target for cutter-ready flag outlines`,
        extrusion: `// Extrusion example
// Convert a 2D flag outline into a thin ply sheet.
// thickness = 0.125 mm prepreg ply`,
        hollow: `// Hollow operation example
// outer shaft envelope - inner bore envelope = tube wall`,
        parametric: `// Parameters
targetCPM = ${document.getElementById('target').value}
wrapAngle = ${document.getElementById('angle').value}
material = "${document.getElementById('material').value}"
method = "${document.getElementById('method').value}"`
      };
      document.getElementById('cadScript').value = examples[kind] || shaftCadScript();
      writeCadConsole(`Loaded CAD example: ${kind}`);
    }

    function writeCadConsole(message) {
      const consolePanel = document.getElementById('cadConsole');
      if (!consolePanel) return;
      const stamp = new Date().toLocaleTimeString();
      consolePanel.textContent += `\n[${stamp}] ${message}`;
      consolePanel.scrollTop = consolePanel.scrollHeight;
    }

    function selectedArchitecture() {
      const key = document.getElementById('architectureMode')?.value || 'flag_wrap';
      return { key, ...(ARCHITECTURES[key] || ARCHITECTURES.flag_wrap) };
    }

    function updateArchitecturePanel() {
      const architecture = selectedArchitecture();
      const chip = document.getElementById('cadArchitectureChip');
      const readout = document.getElementById('architectureReadout');
      const objects = document.getElementById('architectureObjects');
      if (chip) chip.textContent = architecture.name;
      if (readout) {
        readout.innerHTML = [
          ['Mode', architecture.name],
          ['CAD role', architecture.cadRole],
          ['Exports', architecture.exports.join(', ')],
          ['Current angle', `${document.getElementById('angle').value} deg`],
          ['Material', document.getElementById('material').value]
        ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
      }
      if (objects) {
        objects.innerHTML = architecture.objects.map(item => `<div class="object-token">${item}</div>`).join('');
      }
    }

    function updateCadInspector() {
      const inspector = document.getElementById('cadInspector');
      if (!inspector) return;
      const material = document.getElementById('material').value;
      const method = document.getElementById('method').value;
      const angle = document.getElementById('angle').value;
      const architecture = selectedArchitecture();
      const cpm = latest ? latest.overall_cpm.toFixed(1) : '-';
      const rows = [
        ['Model', 'AE ShaftCAD envelope'],
        ['Architecture', architecture.name],
        ['Material', material],
        ['Method', method],
        ['Wrap angle', `${angle} deg`],
        ['Overall CPM', cpm],
        ['Segments', '4'],
        ['Total length', '1016 mm'],
        ['Butt OD', '15 mm'],
        ['Tip OD', '7 mm'],
        ['Flags', flags.length]
      ];
      inspector.innerHTML = rows.map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
    }

    function shaftRadiusAt(t, butt, tip) {
      return butt / 2 + (tip / 2 - butt / 2) * t;
    }

    function drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, phase, color, dash) {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash(dash || []);
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const t = i / 120;
        const x = shaftX + t * length + 23 * t;
        const radius = shaftRadiusAt(t, butt, tip);
        const wave = Math.sin(t * Math.PI * 10 + phase) * radius * 0.48;
        const y = shaftY + wave + 7 * t;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();
    }

    function drawArchitectureOverlay(ctx, key, shaftX, shaftY, length, butt, tip, dark) {
      const primary = dark ? '#f2b84b' : '#a85f00';
      const secondary = dark ? '#ff7de9' : '#7b2c7e';
      const cyan = dark ? '#86fff2' : '#087c75';
      if (key === 'flag_wrap' || key === 'hybrid_flag_helix' || key === 'braid_tape_braid') {
        flags.slice(0, 5).forEach((flag, index) => {
          const t = Math.min(0.92, 0.08 + index * 0.18);
          const x = shaftX + t * length;
          const y = shaftY - shaftRadiusAt(t, butt, tip) - 18 - (index % 2) * 18;
          ctx.save();
          ctx.translate(x, y);
          ctx.rotate((flag.angle || 0) * Math.PI / 180 * 0.2);
          ctx.strokeStyle = primary;
          ctx.fillStyle = 'rgba(242,184,75,0.18)';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(0, -8);
          ctx.lineTo(70, -5);
          ctx.lineTo(70, 5);
          ctx.lineTo(0, 8);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          ctx.restore();
        });
      }
      if (key === 'helical_wrap' || key === 'hybrid_flag_helix' || key === 'automated_tape') {
        drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, 0, secondary, []);
        drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, Math.PI, secondary, key === 'automated_tape' ? [8, 6] : []);
      }
      if (key === 'tubular_braid') {
        for (let phase = 0; phase < Math.PI * 2; phase += Math.PI / 3) {
          drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, phase, cyan, []);
          drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, -phase, primary, [7, 5]);
        }
      }
      if (key === 'braid_tape_braid') {
        for (let phase = 0; phase < Math.PI * 2; phase += Math.PI / 2) {
          drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, phase, cyan, [6, 5]);
          drawHelixLine(ctx, shaftX, shaftY, length, butt, tip, -phase, primary, [8, 6]);
        }
        tapes.forEach((tape, index) => {
          const t = Math.max(0, Math.min(1, (41 - tape.startIn) / 30));
          const x = shaftX + t * length;
          const y = shaftY - 36 - index * 10;
          ctx.save();
          ctx.translate(x, y);
          ctx.rotate(Number(tape.angle) * Math.PI / 180 * 0.18);
          ctx.fillStyle = tapeColor(tape.angle);
          ctx.globalAlpha = 0.72;
          ctx.fillRect(0, -3, Math.max(28, tape.length * 0.28), 6);
          ctx.globalAlpha = 1;
          ctx.restore();
        });
      }
      ctx.fillStyle = dark ? '#d7fff6' : '#17211f';
      ctx.font = '12px Arial';
      ctx.fillText(`${selectedArchitecture().name} design objects`, shaftX, shaftY + 88);
    }

    function drawCad3d() {
      const canvas = document.getElementById('cad3dCanvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const architecture = selectedArchitecture();
      const dark = document.getElementById('cadDarkMode')?.checked;
      const showAxis = document.getElementById('cadShowAxis')?.checked;
      const showGrid = document.getElementById('cadShowGrid')?.checked;
      const smooth = document.getElementById('cadSmooth')?.checked;
      const zoomFit = document.getElementById('cadZoomFit')?.checked;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = dark ? '#101918' : '#f7f8fb';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const originX = canvas.width / 2;
      const originY = canvas.height / 2 + 70;
      const gridSpan = zoomFit ? 13 : 18;
      ctx.strokeStyle = dark ? '#263b37' : '#cfd3ff';
      ctx.lineWidth = 1;
      if (showGrid) {
        for (let i = -gridSpan; i <= gridSpan; i++) {
          ctx.beginPath();
          ctx.moveTo(originX + i * 22 - 330, originY + i * 11 + 165);
          ctx.lineTo(originX + i * 22 + 330, originY + i * 11 - 165);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(originX + i * 22 - 330, originY - i * 11 - 165);
          ctx.lineTo(originX + i * 22 + 330, originY - i * 11 + 165);
          ctx.stroke();
        }
      }

      if (showAxis) {
        ctx.lineWidth = 3;
        ctx.strokeStyle = '#d92929';
        ctx.beginPath(); ctx.moveTo(originX, originY); ctx.lineTo(originX + 140, originY + 70); ctx.stroke();
        ctx.strokeStyle = '#16a34a';
        ctx.beginPath(); ctx.moveTo(originX, originY); ctx.lineTo(originX + 110, originY - 84); ctx.stroke();
        ctx.strokeStyle = '#304ffe';
        ctx.beginPath(); ctx.moveTo(originX, originY); ctx.lineTo(originX, originY - 150); ctx.stroke();
      }

      const shaftX = originX - 230;
      const shaftY = originY - 20;
      const length = 460;
      const butt = 48;
      const tip = 22;
      ctx.beginPath();
      ctx.moveTo(shaftX, shaftY - butt / 2);
      ctx.lineTo(shaftX + length, shaftY - tip / 2);
      ctx.lineTo(shaftX + length + 46, shaftY + 13);
      ctx.lineTo(shaftX + 46, shaftY + butt / 2 + 13);
      ctx.closePath();
      ctx.fillStyle = '#35c7b2';
      ctx.globalAlpha = smooth ? 0.9 : 0.72;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = dark ? '#d7fff6' : '#12665d';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = dark ? '#ffffff' : '#17211f';
      ctx.font = '14px Arial';
      ctx.fillText(`Tapered shaft / mandrel preview - ${architecture.name}`, shaftX, shaftY - 52);
      ctx.fillText('Butt OD 15 mm', shaftX - 12, shaftY + 62);
      ctx.fillText('Tip OD 7 mm', shaftX + length - 8, shaftY + 48);

      drawArchitectureOverlay(ctx, architecture.key, shaftX, shaftY, length, butt, tip, dark);

      ctx.fillStyle = '#d7d7d7';
      ctx.strokeStyle = '#a9a9a9';
      ctx.lineWidth = 1;
      const cubeX = canvas.width - 128;
      const cubeY = 48;
      ctx.beginPath();
      ctx.moveTo(cubeX, cubeY);
      ctx.lineTo(cubeX + 54, cubeY + 26);
      ctx.lineTo(cubeX + 54, cubeY + 84);
      ctx.lineTo(cubeX, cubeY + 58);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#ededed';
      ctx.beginPath();
      ctx.moveTo(cubeX, cubeY);
      ctx.lineTo(cubeX + 48, cubeY - 26);
      ctx.lineTo(cubeX + 102, cubeY);
      ctx.lineTo(cubeX + 54, cubeY + 26);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#cfcfcf';
      ctx.beginPath();
      ctx.moveTo(cubeX + 54, cubeY + 26);
      ctx.lineTo(cubeX + 102, cubeY);
      ctx.lineTo(cubeX + 102, cubeY + 58);
      ctx.lineTo(cubeX + 54, cubeY + 84);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#555';
      ctx.fillText('TOP', cubeX + 43, cubeY - 2);
      ctx.fillText('FRONT', cubeX + 8, cubeY + 48);
      ctx.fillText('RIGHT', cubeX + 62, cubeY + 48);

      const script = document.getElementById('cadScript');
      if (script) script.value = shaftCadScript();
      updateArchitecturePanel();
      updateCadInspector();
    }

    function downloadCadScript(button) {
      flashButton(button, 'Exported');
      const exportType = document.getElementById('cadExportType').value;
      let content = shaftCadScript();
      let filename = 'shaft-parametric-model.jscad';
      if (exportType === 'STEP recipe') {
        content = cadQueryStepRecipe();
        filename = 'shaft-step-recipe.py';
      } else if (exportType === 'STL recipe') {
        content = '# STL preview recipe\n# Lower fidelity visual check export for shaft envelope.\n\n' + shaftCadScript();
        filename = 'shaft-stl-recipe.py';
      } else if (exportType === 'Mandrel G-code') {
        content = latest ? latest.gcode : document.getElementById('gcode').textContent;
        filename = 'shaft-mandrel-toolpath.nc';
      }
      writeCadConsole(`Exported ${exportType}: ${filename}`);
      const blob = new Blob([content], {type: 'text/plain'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
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

    function safeInvoke(name, callback) {
      try {
        callback();
      } catch (error) {
        writeCadConsole(`${name} failed: ${error.message || String(error)}`);
      }
    }

    function bindClickById(id, callback) {
      const element = document.getElementById(id);
      if (!element) return;
      element.onclick = null;
      element.addEventListener('click', event => {
        event.preventDefault();
        safeInvoke(id, () => callback(element));
      });
    }

    function bootstrapButtons() {
      bindClickById('simTab', () => showView('simulation'));
      bindClickById('fitTab', () => showView('fit'));
      bindClickById('drawTab', () => showView('drawing'));
      bindClickById('flagTab', () => showView('flags'));
      bindClickById('tapeTab', () => showView('tape'));
      bindClickById('stackTab', () => showView('stack'));
      bindClickById('cad3dTab', () => showView('cad3d'));

      document.querySelectorAll('button').forEach(button => {
        const label = button.textContent.trim();
        if (button.dataset.bound === '1') return;
        const actions = {
          'Analyze Shaft': () => run(button),
          'Export JSON': () => downloadJson(button),
          'Export G-Code': () => downloadGcode(button),
          'Generate Shaft Target': () => runFitToBuild(button),
          'Apply to CAD': () => applyFitToCad(button),
          'Export Fit Profile': () => downloadFitProfile(button),
          'Add Flag': () => addFlag(button),
          'Add Triangle': () => addTriangleFlag(button),
          'Reset Flags': () => resetFlags(button),
          'Export Flag JSON': () => downloadFlagJson(button),
          'Export Flag SVG': () => downloadFlagSvg(button),
          'Export DXF': () => downloadFlagDxf(button),
          'Save Project': () => downloadProject(button),
          'Add Tape Strip': () => addTape(button),
          'Add +/-45 Pair': () => addBiasTapePair(button),
          'Reset TapeCAD': () => resetTapes(button),
          'Export Tape JSON': () => downloadTapeJson(button),
          'Regenerate from CAD Objects': () => regenerateStack(button),
          'Export Stack JSON': () => downloadStackJson(button),
          'Export Build Sheet': () => downloadBuildSheet(button),
          'Export': () => downloadCadScript(button)
        };
        if (!actions[label]) return;
        button.dataset.bound = '1';
        button.onclick = null;
        button.addEventListener('click', event => {
          event.preventDefault();
          safeInvoke(label, actions[label]);
        });
      });
      writeCadConsole('Button safety bootstrap active.');
    }

    window.showView = showView;
    window.setSketchTool = setSketchTool;
    window.run = run;
    window.runFitToBuild = runFitToBuild;
    window.applyFitToCad = applyFitToCad;
    window.downloadFitProfile = downloadFitProfile;
    window.renderFlagEditor = renderFlagEditor;
    window.addFlag = addFlag;
    window.addTriangleFlag = addTriangleFlag;
    window.deleteFlag = deleteFlag;
    window.resetFlags = resetFlags;
    window.flagMouseDown = flagMouseDown;
    window.flagMouseMove = flagMouseMove;
    window.flagMouseUp = flagMouseUp;
    window.updateFlag = updateFlag;
    window.downloadFlagJson = downloadFlagJson;
    window.downloadFlagSvg = downloadFlagSvg;
    window.downloadFlagDxf = downloadFlagDxf;
    window.downloadProject = downloadProject;
    window.loadProjectFile = loadProjectFile;
    window.renderTapeCad = renderTapeCad;
    window.addTape = addTape;
    window.addBiasTapePair = addBiasTapePair;
    window.updateTape = updateTape;
    window.deleteTape = deleteTape;
    window.resetTapes = resetTapes;
    window.downloadTapeJson = downloadTapeJson;
    window.renderStackCad = renderStackCad;
    window.regenerateStack = regenerateStack;
    window.moveStackLayer = moveStackLayer;
    window.downloadStackJson = downloadStackJson;
    window.downloadBuildSheet = downloadBuildSheet;
    window.loadCadExample = loadCadExample;
    window.updateArchitecturePanel = updateArchitecturePanel;
    window.drawCad3d = drawCad3d;
    window.downloadCadScript = downloadCadScript;
    window.downloadJson = downloadJson;
    window.downloadGcode = downloadGcode;
    window.bootstrapButtons = bootstrapButtons;

    bootstrapButtons();
    run().catch(error => writeCadConsole(error.message || String(error)));
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
    architecture_mode: str = "flag_wrap",
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
        architecture_mode=architecture_mode,
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


@app.get("/api/cadquery-step-recipe")
def api_cadquery_step_recipe(
    wrap_angle_deg: float = 45.0,
) -> dict[str, str]:
    return {
        "filename": "shaftcad_step_recipe.py",
        "recipe": generate_cadquery_step_recipe(default_segments(base_angle=wrap_angle_deg)),
    }


@app.get("/api/materials")
def api_materials() -> dict[str, Any]:
    return {name: asdict(material) for name, material in MATERIALS.items()}


@app.get("/api/manufacturing-methods")
def api_methods() -> dict[str, Any]:
    return MANUFACTURING_METHODS


@app.get("/api/architecture-modes")
def api_architecture_modes() -> dict[str, Any]:
    return ARCHITECTURE_MODES
