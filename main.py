from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import cos, degrees, log10, pi, radians, sin, sqrt
from typing import Any

from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import HTMLResponse

app = FastAPI(title="AE ShaftCAD Studio", version="1.1")
APP_VERSION = "1.2"
APP_BUILD_TIME = datetime.now(timezone.utc).isoformat()
APP_BUILD_COMMIT = os.getenv("RENDER_GIT_COMMIT", "local-dev")


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


@dataclass
class CpmCalibration:
    clamp_length_in: float = 5.0
    overall_weight_g: float = 205.0
    profile_weight_g: float = 255.0
    overall_k: float = 14.7
    zone_k: float = 8.5


DEFAULT_CPM_CAL = CpmCalibration()


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


def cpm_effective_length_m(total_length_m: float, clamp_length_in: float) -> float:
    return max(0.08, total_length_m - clamp_length_in * 0.0254)


def overall_cpm(segments: list[Segment], material: Material, calibration: CpmCalibration) -> float:
    length = total_length(segments)
    effective_length = cpm_effective_length_m(length, calibration.clamp_length_in)
    ei = average_ei(segments, material)
    return calibration.overall_k * sqrt(ei / ((calibration.overall_weight_g / 1000.0) * effective_length**3))


def zone_profile(segments: list[Segment], material: Material, calibration: CpmCalibration) -> list[dict[str, float]]:
    ei = average_ei(segments, material)
    clamp = calibration.clamp_length_in
    return [
        {
            "station_in": float(station),
            "effective_span_in": max(1.0, station - clamp),
            "cpm": calibration.zone_k
            * sqrt(ei / ((calibration.profile_weight_g / 1000.0) * (max(1.0, station - clamp) * 0.0254) ** 3)),
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


def fit_target_from_swing(
    speed_mph: float = 105.0,
    launch_deg: float = 13.5,
    spin_rpm: float = 2650.0,
    weight_g: float = 65.0,
    tempo: str = "Medium",
    transition: str = "Medium",
    release: str = "Mid",
    miss: str = "Neutral",
    feel: str = "Stable mid",
) -> dict[str, Any]:
    tempo_map = {"Smooth": -4.0, "Medium": 0.0, "Aggressive": 5.0}
    transition_map = {"Smooth": -3.0, "Medium": 0.0, "Hard": 6.0}
    release_map = {"Early": -3.0, "Mid": 0.0, "Late": 4.0}
    feel_map = {"Softer load": -5.0, "Stable mid": 0.0, "Boardy/stout": 6.0}

    target_cpm = 235.0 + speed_mph * 0.22
    target_cpm += tempo_map.get(tempo, 0.0)
    target_cpm += transition_map.get(transition, 0.0)
    target_cpm += release_map.get(release, 0.0)
    target_cpm += feel_map.get(feel, 0.0)
    if miss == "Left":
        target_cpm += 3.0
    if miss == "Right":
        target_cpm -= 2.0
    if miss == "High spin":
        target_cpm += 4.0
    if miss == "Low launch":
        target_cpm -= 4.0

    torque_target = max(2.4, 4.2 - (target_cpm - 250.0) * 0.025 - (0.35 if transition == "Hard" else 0.0))
    launch_bias = (
        "lower launch / lower spin"
        if launch_deg > 15.0 or spin_rpm > 3000.0
        else "add launch / smoother tip"
        if launch_deg < 11.0
        else "neutral launch"
    )
    wrap_angle = max(28.0, min(58.0, 45.0 + (5.0 if transition == "Hard" else 0.0) + (4.0 if miss == "Left" else 0.0) - (5.0 if feel == "Softer load" else 0.0)))
    tip_strategy = (
        "stiffen tip section with bias/hoop support"
        if "lower" in launch_bias
        else "soften tip section and reduce hoop density"
        if "add" in launch_bias
        else "balanced tip stiffness"
    )
    profile = [
        {"station": 41, "cpm": target_cpm - 18.0},
        {"station": 36, "cpm": target_cpm - 10.0},
        {"station": 31, "cpm": target_cpm - 3.0},
        {"station": 26, "cpm": target_cpm + 2.0},
        {"station": 21, "cpm": target_cpm + 8.0},
        {"station": 16, "cpm": target_cpm + 15.0},
        {"station": 11, "cpm": target_cpm + 24.0},
    ]
    return {
        "target_cpm": target_cpm,
        "target_weight_g": weight_g,
        "torque_target_deg": torque_target,
        "wrap_angle_deg": wrap_angle,
        "launch_bias": launch_bias,
        "tip_strategy": tip_strategy,
        "zone_profile": profile,
        "inputs": {
            "speed": speed_mph,
            "launch": launch_deg,
            "spin": spin_rpm,
            "weight": weight_g,
            "tempo": tempo,
            "transition": transition,
            "release": release,
            "miss": miss,
            "feel": feel,
        },
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
    cpm_clamp_length_in: float = 5.0,
    cpm_overall_weight_g: float = 205.0,
    cpm_profile_weight_g: float = 255.0,
    cpm_overall_k: float = 14.7,
    cpm_zone_k: float = 8.5,
) -> dict[str, Any]:
    material = MATERIALS.get(material_name, MATERIALS["Mitsubishi MR70"])
    method = MANUFACTURING_METHODS.get(method_key, MANUFACTURING_METHODS["roll_wrapped"])
    architecture = ARCHITECTURE_MODES.get(architecture_mode, ARCHITECTURE_MODES["flag_wrap"])
    segments = default_segments(base_angle=wrap_angle_deg)
    calibration = CpmCalibration(
        clamp_length_in=max(0.0, cpm_clamp_length_in),
        overall_weight_g=max(1.0, cpm_overall_weight_g),
        profile_weight_g=max(1.0, cpm_profile_weight_g),
        overall_k=max(0.1, cpm_overall_k),
        zone_k=max(0.1, cpm_zone_k),
    )
    cpm = overall_cpm(segments, material, calibration)
    mass = shaft_mass_kg(segments, material) * method["mass_factor"]
    cost = mass * material.cost_per_kg * method["cost_factor"]
    torsion = torsion_deg(segments, material, factor=method["torsion_factor"])
    zones = zone_profile(segments, material, calibration)
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
        "cpm_calibration": asdict(calibration),
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
    .app-status { background: #d7fff6; color: #17211f; border-bottom: 1px solid #9fc8c0; padding: 8px 18px; font-size: 13px; font-weight: 800; }
    .app-status.bad { background: #ffe1df; color: #8a1f16; border-color: #df9b95; }
    .build-fingerprint { background: #ffffff; border-bottom: 1px solid #d6e2df; padding: 8px 18px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 12px; }
    .build-fingerprint code { background: #eef5f3; padding: 2px 6px; border-radius: 4px; }
    .build-fingerprint .fp-ok { color: #0f7a4f; font-weight: 700; }
    .build-fingerprint .fp-bad { color: #a5261e; font-weight: 700; }
    .build-fingerprint button { width: auto; margin: 0; padding: 5px 9px; font-size: 12px; }
    .viewer-note { color: #8a4d00; font-weight: 700; margin-left: 8px; }
    main { display: grid; grid-template-columns: 340px 1fr; gap: 0; min-height: calc(100vh - 111px); }
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
    button.danger { background: #b3261e; color: #ffffff; }
    button.clicked { background: #d9911f; color: #17211f; }
    .mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .panel-title { margin-top: 18px; padding-top: 14px; border-top: 1px solid #dbe4e1; font-size: 16px; }
    .debug-panel { margin-top: 14px; border: 1px solid #cbd8d5; border-radius: 6px; background: #ffffff; padding: 10px; }
    .debug-panel h3 { margin: 0 0 8px; font-size: 14px; }
    .debug-panel table { font-size: 12px; margin-top: 0; }
    .history-panel { margin-top: 14px; border: 1px solid #cbd8d5; border-radius: 6px; background: #ffffff; padding: 10px; }
    .history-panel h3 { margin: 0 0 8px; font-size: 14px; }
    .history-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }
    .history-table td { font-size: 12px; padding: 5px; }
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
    .sketch-menu { grid-column: 1 / 4; background: #202020; color: white; padding: 7px 10px; font-family: Georgia, serif; font-weight: 700; display: flex; gap: 8px; flex-wrap: wrap; }
    .sketch-menu .menu-btn { width: auto; margin: 0; padding: 4px 8px; background: transparent; border: 1px solid transparent; color: #ffffff; border-radius: 4px; font-weight: 700; }
    .sketch-menu .menu-btn:hover { border-color: #4a5d58; background: #293230; }
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
    .viewer-mode input,
    .viewer-mode select,
    .viewer-mode textarea,
    .viewer-mode button.viewer-locked {
      opacity: 0.65;
      cursor: not-allowed;
    }
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
  <div id="appStatus" class="app-status">AE boot check: HTML loaded. JavaScript has not confirmed yet.</div>
  <div class="build-fingerprint">
    <span>Version <code id="fpVersion">-</code></span>
    <span>Commit <code id="fpCommit">-</code></span>
    <span>Built <code id="fpBuilt">-</code></span>
    <span>Smoke <strong id="fpSmoke" class="fp-ok">Pending</strong></span>
    <button id="fpSmokeBtn" class="secondary">Run Smoke Test</button>
  </div>
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
      <button id="analyzeBtn" onclick="run(this)">Analyze Shaft</button>
      <button id="exportJsonBtn" class="secondary" onclick="downloadJson(this)">Export JSON</button>
      <button id="exportGcodeBtn" class="secondary" onclick="downloadGcode(this)">Export G-Code</button>
      <div class="debug-panel">
        <h3>Debug / Health</h3>
        <table><tbody id="debugHealth"></tbody></table>
        <label><input id="strictModeToggle" type="checkbox" onchange="setStrictMode(this.checked)"> Strict button mode</label>
        <button id="debugAuditBtn" class="secondary" onclick="runButtonAudit(this)">Run Button Audit</button>
      </div>
      <div class="history-panel">
        <h3>Design History</h3>
        <div class="history-actions">
          <button id="historyUndoBtn" class="secondary">Undo Design</button>
          <button id="historyRedoBtn" class="secondary">Redo Design</button>
        </div>
        <table class="history-table"><tbody id="historyRows"></tbody></table>
      </div>
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
            <h3>Export Validation</h3>
            <table><tbody id="validationReadout"></tbody></table>
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
          <div class="cad-chip">Sync State<strong id="fitSyncState">Not synced</strong></div>
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
          <button id="fitGenerateBtn" onclick="runFitToBuild(this)">Generate Shaft Target</button>
          <button id="fitApplyBtn" class="secondary" onclick="applyFitToCad(this)">Apply to CAD</button>
          <button id="fitExportBtn" class="secondary" onclick="downloadFitProfile(this)">Export Fit Profile</button>
        </div>
        <div class="fit-actions">
          <button id="fitSyncPacketBtn" class="secondary" onclick="downloadFitCadPacket(this)">Export Fit-CAD Packet</button>
          <button id="fitPullCadBtn" class="secondary" onclick="pullCadIntoFit(this)">Pull CAD -> Fit Inputs</button>
        </div>
        <h3>CPM Calibration (Clamp / Weight Rig)</h3>
        <div class="fit-grid">
          <div><label>Clamp Length (in)</label><input id="cpmClampIn" type="number" value="5.0" step="0.1"></div>
          <div><label>Overall Weight (g)</label><input id="cpmOverallWeight" type="number" value="205" step="1"></div>
          <div><label>Profile Weight (g)</label><input id="cpmProfileWeight" type="number" value="255" step="1"></div>
          <div><label>Overall K</label><input id="cpmOverallK" type="number" value="14.7" step="0.1"></div>
          <div><label>Zone K</label><input id="cpmZoneK" type="number" value="8.5" step="0.1"></div>
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
        <div class="grid2">
          <div>
            <h3>Fit/CAD Bridge</h3>
            <table><tbody id="fitBridge"></tbody></table>
          </div>
          <div>
            <h3>Fit Scoring</h3>
            <table><tbody id="fitScore"></tbody></table>
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
        <div class="cad-toolbar">
          <button id="drawToolSelectBtn" class="cad-tool active">Select</button>
          <button id="drawToolMoveBtn" class="cad-tool">Move</button>
          <button id="drawToolAddBtn" class="cad-tool">Add Point</button>
          <button id="drawToolDimBtn" class="cad-tool">Dimension</button>
          <button id="drawToolDeleteBtn" class="cad-tool">Delete Point</button>
        </div>
        <div class="sketch-options">
          <label><input id="drawSnapGrid" type="checkbox" checked> Snap to 5 mm</label>
          <label><input id="drawOrthoLock" type="checkbox"> Ortho Lock (OD only)</label>
          <span id="drawSelectionLabel">No station selected</span>
        </div>
        <div class="tool-row">
          <button id="drawAddStationBtn">Add Station</button>
          <button id="drawDeleteStationBtn" class="danger">Delete Selected Station</button>
          <button id="drawResetProfileBtn" class="secondary">Reset Drawing Profile</button>
        </div>
        <canvas class="drawing-canvas" id="designCanvas" width="1100" height="420"
          onmousedown="drawingMouseDown(event)" onmousemove="drawingMouseMove(event)" onmouseup="drawingMouseUp()" onmouseleave="drawingMouseUp()"></canvas>
        <div class="grid2">
          <div>
            <h3>Drawing Dimensions</h3>
            <table><thead><tr><th>Feature</th><th>Value</th></tr></thead><tbody id="drawingDims"></tbody></table>
            <h3>Station Editor</h3>
            <table class="editable-table">
              <thead><tr><th>#</th><th>Station mm</th><th>OD mm</th></tr></thead>
              <tbody id="drawingStationsRows"></tbody>
            </table>
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
            <button id="sketchMenuFileBtn" class="menu-btn" onclick="handleSketchMenu('file', this)">File</button>
            <button id="sketchMenuEditBtn" class="menu-btn" onclick="handleSketchMenu('edit', this)">Edit</button>
            <button id="sketchMenuViewBtn" class="menu-btn" onclick="handleSketchMenu('view', this)">View</button>
            <button id="sketchMenuNewGroupBtn" class="menu-btn" onclick="handleSketchMenu('new-group', this)">New Group</button>
            <button id="sketchMenuSketchBtn" class="menu-btn" onclick="handleSketchMenu('sketch', this)">Sketch</button>
            <button id="sketchMenuConstrainBtn" class="menu-btn" onclick="handleSketchMenu('constrain', this)">Constrain</button>
            <button id="sketchMenuAnalyzeBtn" class="menu-btn" onclick="handleSketchMenu('analyze', this)">Analyze</button>
            <button id="sketchMenuHelpBtn" class="menu-btn" onclick="handleSketchMenu('help', this)">Help</button>
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
          <button id="constraintSelHorizontalBtn" class="secondary" onclick="applySelectedConstraint('horizontal', this)">Horizontal</button>
          <button id="constraintSelVerticalBtn" class="secondary" onclick="applySelectedConstraint('vertical', this)">Vertical</button>
          <button id="constraintSelLengthBtn" class="secondary" onclick="applySelectedConstraint('length', this)">Set Length</button>
          <button id="constraintSelAngleBtn" class="secondary" onclick="applySelectedConstraint('angle', this)">Set Angle</button>
          <input id="constraintValueInput" type="number" step="0.1" value="0" title="Constraint value (length mm or angle deg)">
        </div>
        <div class="tool-row">
          <button id="flagPrevBtn" class="secondary" onclick="selectAdjacentFlag(-1, this)">Prev Flag</button>
          <button id="flagNextBtn" class="secondary" onclick="selectAdjacentFlag(1, this)">Next Flag</button>
          <button id="flagDuplicateBtn" class="secondary" onclick="duplicateSelectedFlag(this)">Duplicate</button>
          <button id="flagDeleteSelectedBtn" class="secondary" onclick="deleteSelectedFlag(this)">Delete Selected</button>
          <button id="flagMirrorAngleBtn" class="secondary" onclick="mirrorSelectedFlagAngle(this)">Mirror Angle</button>
        </div>
        <div class="tool-row">
          <button id="constraintApplyBtn" class="secondary" onclick="applyFlagConstraints(this)">Apply Constraints</button>
          <button id="constraintResetBtn" class="secondary" onclick="resetFlagConstraints(this)">Reset Constraints</button>
        </div>
        <h3>Dimension Presets</h3>
        <div class="mini-grid">
          <div>
            <label>Length mm</label>
            <input id="dimLengthInput" type="number" value="360" step="1" min="1">
          </div>
          <div>
            <label>Root mm</label>
            <input id="dimRootInput" type="number" value="76" step="1" min="1">
          </div>
        </div>
        <div class="mini-grid">
          <div>
            <label>Tip mm</label>
            <input id="dimTipInput" type="number" value="58" step="1" min="1">
          </div>
          <div>
            <label>Angle rule</label>
            <select id="dimAngleRule">
              <option value="keep">Keep current angle</option>
              <option value="zero">Set angle to 0</option>
              <option value="bias_pair">Set to +/-45 bias pair</option>
            </select>
          </div>
        </div>
        <div class="tool-row">
          <button id="dimApplySelectedBtn" class="secondary" onclick="applyDimensionPreset('selected', this)">Apply to Selected</button>
          <button id="dimApplyAllBtn" class="secondary" onclick="applyDimensionPreset('all', this)">Apply to All Flags</button>
          <button id="dimProgressiveBtn" class="secondary" onclick="applyDimensionPreset('progressive', this)">Progressive Taper Set</button>
        </div>
        <h3>Constraint Set</h3>
        <table class="editable-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Scope</th>
              <th>Value</th>
              <th>Enabled</th>
            </tr>
          </thead>
          <tbody id="constraintRows"></tbody>
        </table>
        <h3>Constraint Failure Diagnostics</h3>
        <table class="editable-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody id="constraintFailureRows"></tbody>
        </table>
        <div class="tool-row">
          <button id="flagAddBtn" onclick="addFlag(this)">Add Flag</button>
          <button id="flagTriangleBtn" onclick="addTriangleFlag(this)">Add Triangle</button>
          <button id="flagResetBtn" class="secondary" onclick="resetFlags(this)">Reset Flags</button>
          <button id="flagJsonBtn" class="secondary" onclick="downloadFlagJson(this)">Export Flag JSON</button>
          <button id="flagSvgBtn" class="secondary" onclick="downloadFlagSvg(this)">Export Flag SVG</button>
          <button id="flagDxfBtn" class="secondary" onclick="downloadFlagDxf(this)">Export DXF</button>
        </div>
        <div class="tool-row">
          <button id="projectSaveBtn" class="secondary" onclick="downloadProject(this)">Save Project</button>
          <button id="projectLoadBtn" class="secondary" onclick="document.getElementById('projectFile').click()">Load Project</button>
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
            <button id="tapeAddBtn" onclick="addTape(this)">Add Tape Strip</button>
            <button id="tapeBiasBtn" class="secondary" onclick="addBiasTapePair(this)">Add +/-45 Pair</button>
            <button id="tapeResetBtn" class="secondary" onclick="resetTapes(this)">Reset TapeCAD</button>
            <button id="tapeJsonBtn" class="secondary" onclick="downloadTapeJson(this)">Export Tape JSON</button>
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
            <button id="stackGenerateBtn" onclick="regenerateStack(this)">Regenerate from CAD Objects</button>
            <button id="stackJsonBtn" class="secondary" onclick="downloadStackJson(this)">Export Stack JSON</button>
            <button id="stackSheetBtn" class="secondary" onclick="downloadBuildSheet(this)">Export Build Sheet</button>
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
            <canvas class="viewer-canvas" id="cad3dCanvas" width="900" height="520"
              onmousedown="cad3dMouseDown(event)" onmousemove="cad3dMouseMove(event)"
              onmouseup="cad3dMouseUp()" onmouseleave="cad3dMouseUp()"></canvas>
            <div class="export-row">
              <select id="cadExportType">
                <option>JSCAD script</option>
                <option>STEP recipe</option>
                <option>STL recipe</option>
                <option>Mandrel G-code</option>
              </select>
              <button id="cadExportBtn" onclick="downloadCadScript(this)">Export</button>
            </div>
          </div>
          <div class="inspector-panel">
            <h3>Options</h3>
            <label>Dark Mode <input id="cadDarkMode" type="checkbox" onchange="drawCad3d()"></label>
            <label>Show Axis <input id="cadShowAxis" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Show Grid <input id="cadShowGrid" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Smooth Render <input id="cadSmooth" type="checkbox" onchange="drawCad3d()"></label>
            <label>Zoom To Fit <input id="cadZoomFit" type="checkbox" onchange="drawCad3d()"></label>
            <h3>Draft Sketch</h3>
            <div class="cad-toolbar">
              <button id="cadDraftSelectBtn" class="cad-tool active">Select</button>
              <button id="cadDraftLineBtn" class="cad-tool">Line</button>
              <button id="cadDraftRectBtn" class="cad-tool">Rect</button>
              <button id="cadDraftCircleBtn" class="cad-tool">Circle</button>
              <button id="cadDraftTriangleBtn" class="cad-tool">Triangle</button>
            </div>
            <div class="tool-row">
              <button id="cadDraftUndoBtn" class="secondary">Undo</button>
              <button id="cadDraftRedoBtn" class="secondary">Redo</button>
              <button id="cadDraftDeleteBtn" class="secondary">Delete Selected</button>
              <button id="cadDraftClearBtn" class="secondary">Clear Sketch</button>
            </div>
            <p id="cadDraftStatus">Tool: select</p>
            <h3>Sketch Diagnostics</h3>
            <table><tbody id="cadDraftDiagnostics"></tbody></table>
            <div class="tool-row">
              <button id="cadRefreshBtn" class="secondary" onclick="drawCad3d()">Refresh View</button>
              <button id="cadPresetDarkBtn" class="secondary" onclick="setCadPreset('dark', this)">Dark Preset</button>
              <button id="cadPresetLightBtn" class="secondary" onclick="setCadPreset('light', this)">Light Preset</button>
              <button id="cadPresetInspectBtn" class="secondary" onclick="setCadPreset('inspect', this)">Inspect Preset</button>
              <button id="cadSyncScriptBtn" class="secondary" onclick="syncCadScript(this)">Sync Script</button>
            </div>
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
    let dimensionHandles = [];
    let drawingStations = [];
    let selectedDrawingStationIndex = null;
    let drawingDragActive = false;
    let drawingTool = 'select';
    let cadDraftEntities = [];
    let cadDraftTool = 'select';
    let cadDraftSelectedIndex = null;
    let cadDraftDrag = null;
    let cadDraftStart = null;
    let cadDraftPreview = null;
    let cadDraftHistory = [[]];
    let cadDraftFuture = [];
    let cadDraftMoveStartSnapshot = null;
    let designHistory = [];
    let designFuture = [];
    let activeDrag = null;
    let selectedFlagIndex = null;
    let sketchTool = 'select';
    let latestFitProfile = null;
    let fitCadBridge = null;
    let flagConstraints = defaultFlagConstraints(defaultFlags().length);
    const debugState = {
      bootTime: new Date().toISOString(),
      mode: 'edit',
      lastStatus: 'Booting',
      statusKind: 'ok',
      lastAction: '-',
      lastError: '-',
      errors: 0,
      buttonAudit: 'Not run',
      strictMode: true
    };
    const APP_MODE = new URLSearchParams(window.location.search).get('mode') === 'viewer' ? 'viewer' : 'edit';
    const VIEWER_ALLOWED_BUTTON_IDS = new Set(['simTab', 'fitTab', 'drawTab', 'flagTab', 'tapeTab', 'stackTab', 'cad3dTab']);
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

    function deepClone(obj) {
      return JSON.parse(JSON.stringify(obj));
    }

    function designInputSnapshot() {
      const read = id => document.getElementById(id)?.value ?? null;
      return {
        target: read('target'),
        head: read('head'),
        speed: read('speed'),
        angle: read('angle'),
        material: read('material'),
        method: read('method'),
        architectureMode: read('architectureMode')
      };
    }

    function applyDesignInputSnapshot(inputs) {
      if (!inputs) return;
      Object.entries(inputs).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value !== null && value !== undefined) el.value = value;
      });
    }

    function designSnapshot(reason) {
      return {
        ts: new Date().toISOString(),
        reason: reason || 'edit',
        inputs: designInputSnapshot(),
        flags: deepClone(flags),
        tapes: deepClone(tapes),
        drawingStations: deepClone(drawingStations),
        flagConstraints: deepClone(flagConstraints),
        cadDraftEntities: deepClone(cadDraftEntities)
      };
    }

    function renderDesignHistory() {
      const tbody = document.getElementById('historyRows');
      if (!tbody) return;
      const latestRows = designHistory.slice(-8).reverse();
      tbody.innerHTML = latestRows.map((item, i) => {
        const t = new Date(item.ts);
        const label = Number.isNaN(t.valueOf()) ? item.ts : t.toLocaleTimeString();
        return `<tr><td>${i === 0 ? '<strong>Current</strong>' : 'Step'}</td><td>${item.reason}</td><td>${label}</td></tr>`;
      }).join('');
      const undo = document.getElementById('historyUndoBtn');
      const redo = document.getElementById('historyRedoBtn');
      if (undo) undo.disabled = designHistory.length <= 1;
      if (redo) redo.disabled = designFuture.length === 0;
    }

    function applyDesignSnapshot(snapshot) {
      if (!snapshot) return;
      applyDesignInputSnapshot(snapshot.inputs);
      flags = deepClone(snapshot.flags || []);
      tapes = deepClone(snapshot.tapes || []);
      drawingStations = deepClone(snapshot.drawingStations || []);
      flagConstraints = deepClone(snapshot.flagConstraints || defaultFlagConstraints(flags.length));
      cadDraftEntities = deepClone(snapshot.cadDraftEntities || []);
      selectedDrawingStationIndex = null;
      selectedFlagIndex = null;
      cadDraftSelectedIndex = null;
      ensureDrawingStations();
      ensureConstraintCoverage();
      renderFlagEditor();
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawDesign(latest);
      drawCad3d();
      updateValidationReadout();
      renderDesignHistory();
      setAppStatus(`Design restored: ${snapshot.reason}`);
    }

    function designHistoryCommit(reason) {
      const snap = designSnapshot(reason);
      const prev = designHistory[designHistory.length - 1];
      if (prev && JSON.stringify({ ...snap, ts: '' }) === JSON.stringify({ ...prev, ts: '' })) {
        renderDesignHistory();
        return;
      }
      designHistory.push(snap);
      if (designHistory.length > 120) designHistory.shift();
      designFuture = [];
      renderDesignHistory();
    }

    function undoDesignHistory(button) {
      if (designHistory.length <= 1) return;
      const current = designHistory.pop();
      designFuture.push(current);
      applyDesignSnapshot(deepClone(designHistory[designHistory.length - 1]));
      if (button) flashButton(button, 'Undo');
    }

    function redoDesignHistory(button) {
      if (!designFuture.length) return;
      const snap = designFuture.pop();
      designHistory.push(deepClone(snap));
      applyDesignSnapshot(deepClone(snap));
      if (button) flashButton(button, 'Redo');
    }

    async function loadBuildFingerprint() {
      try {
        const res = await fetch('/api/build');
        if (!res.ok) throw new Error(`build api ${res.status}`);
        const meta = await res.json();
        const ver = document.getElementById('fpVersion');
        const commit = document.getElementById('fpCommit');
        const built = document.getElementById('fpBuilt');
        if (ver) ver.textContent = meta.version || '-';
        if (commit) commit.textContent = (meta.commit || '-').slice(0, 12);
        if (built) built.textContent = meta.build_time || '-';
      } catch (error) {
        writeCadConsole(`Build fingerprint load failed: ${error.message || String(error)}`);
      }
    }

    function runSmokeTest(button) {
      const smoke = document.getElementById('fpSmoke');
      const checks = [
        typeof run === 'function',
        typeof drawCad3d === 'function',
        typeof cad3dMouseDown === 'function',
        typeof setCadDraftTool === 'function',
        typeof runButtonAudit === 'function',
        Boolean(document.getElementById('cad3dCanvas')),
        Boolean(document.getElementById('fpSmokeBtn'))
      ];
      const ok = checks.every(Boolean);
      if (smoke) {
        smoke.textContent = ok ? 'PASS' : 'FAIL';
        smoke.classList.toggle('fp-ok', ok);
        smoke.classList.toggle('fp-bad', !ok);
      }
      setAppStatus(ok ? 'Smoke test passed: core CAD wiring healthy.' : 'Smoke test failed: check console for missing bindings.', !ok);
      writeCadConsole(`Smoke test ${ok ? 'PASS' : 'FAIL'} (${checks.filter(Boolean).length}/${checks.length})`);
      if (button) flashButton(button, ok ? 'PASS' : 'FAIL');
      return ok;
    }

    function setAppStatus(message, isBad) {
      const status = document.getElementById('appStatus');
      if (!status) return;
      status.textContent = message;
      status.classList.toggle('bad', Boolean(isBad));
      debugState.lastStatus = message;
      debugState.statusKind = isBad ? 'bad' : 'ok';
      if (isBad) {
        debugState.lastError = message;
        debugState.errors += 1;
      }
      renderDebugHealth();
    }

    function isViewerMode() {
      return APP_MODE === 'viewer';
    }

    function applyViewerMode() {
      if (!isViewerMode()) return;
      debugState.mode = 'viewer';
      document.body.classList.add('viewer-mode');
      const badge = document.querySelector('.build-badge');
      if (badge) badge.innerHTML += '<span class="viewer-note">Viewer Mode</span>';

      document.querySelectorAll('input, select, textarea').forEach(element => {
        element.disabled = true;
      });

      document.querySelectorAll('button').forEach(button => {
        if (!VIEWER_ALLOWED_BUTTON_IDS.has(button.id)) {
          button.disabled = true;
          button.classList.add('viewer-locked');
        }
      });

      const projectFile = document.getElementById('projectFile');
      if (projectFile) projectFile.disabled = true;
      setAppStatus('Viewer mode active: edits and exports are locked.');
    }

    function renderDebugHealth() {
      const body = document.getElementById('debugHealth');
      if (!body) return;
      const rows = [
        ['Mode', debugState.mode],
        ['Boot Time', debugState.bootTime],
        ['Last Action', debugState.lastAction],
        ['Last Status', debugState.lastStatus],
        ['Status', debugState.statusKind.toUpperCase()],
        ['Strict Mode', debugState.strictMode ? 'ON' : 'OFF'],
        ['Error Count', String(debugState.errors)],
        ['Last Error', debugState.lastError],
        ['Button Audit', debugState.buttonAudit]
      ];
      body.innerHTML = rows
        .map(([label, value]) => `<tr><th>${label}</th><td>${value || '-'}</td></tr>`)
        .join('');
    }

    window.onerror = function(message, source, line, column) {
      setAppStatus(`JavaScript crashed: ${message} at ${line}:${column}`, true);
      const consolePanel = document.getElementById('cadConsole');
      if (consolePanel) {
        consolePanel.textContent += `\n[APP ERROR] ${message} at ${line}:${column}`;
      }
      return false;
    };

    if (typeof window.addEventListener === 'function') {
      window.addEventListener('unhandledrejection', event => {
        const reason = event.reason?.message || event.reason || 'unknown promise failure';
        setAppStatus(`Async app error: ${reason}`, true);
        writeCadConsole(`Async app error: ${reason}`);
      });
    }

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

    function numberOr(value, fallback) {
      const n = Number(value);
      return Number.isFinite(n) ? n : fallback;
    }

    function defaultFlagConstraints(flagCount) {
      const constraints = [
        { id: 'length_step', type: 'length_step', scope: 'all flags', value: 5, enabled: true },
        { id: 'min_tip_ratio', type: 'min_tip_ratio', scope: 'all flags', value: 0.35, enabled: true },
        { id: 'bias_pair_angle_abs', type: 'bias_pair_angle_abs', scope: 'bias layers', value: 45, enabled: true }
      ];
      for (let i = 0; i < flagCount; i++) {
        constraints.push({ id: `flag_${i}_horizontal`, type: 'horizontal', scope: `flag ${i + 1}`, value: 1, enabled: true });
      }
      return constraints;
    }

    function ensureConstraintCoverage() {
      const hasGlobal = flagConstraints.some(c => c.type === 'length_step');
      if (!hasGlobal) {
        flagConstraints = defaultFlagConstraints(flags.length);
      }
      for (let i = 0; i < flags.length; i++) {
        const id = `flag_${i}_horizontal`;
        if (!flagConstraints.some(c => c.id === id)) {
          flagConstraints.push({ id, type: 'horizontal', scope: `flag ${i + 1}`, value: 1, enabled: true });
        }
      }
    }

    function normalizeFlag(flag) {
      return {
        ...flag,
        length: Math.max(60, numberOr(flag.length, 320)),
        root: Math.max(8, numberOr(flag.root, 70)),
        tip: Math.max(4, numberOr(flag.tip, 40)),
        angle: Math.max(-89, Math.min(89, numberOr(flag.angle, 0))),
        name: String(flag.name || 'Flag'),
        station: String(flag.station || 'Custom'),
        layer: String(flag.layer || 'custom'),
        locked: Boolean(flag.locked)
      };
    }

    function normalizeFlags() {
      flags = flags.map(normalizeFlag);
    }

    function renderConstraintTable() {
      ensureConstraintCoverage();
      const rows = flagConstraints.map((constraint, index) => `
        <tr>
          <td>${constraint.type}</td>
          <td>${constraint.scope}</td>
          <td><input type="number" step="0.01" value="${constraint.value}" onchange="updateConstraint(${index}, 'value', this.value)"></td>
          <td><input type="checkbox" ${constraint.enabled ? 'checked' : ''} onchange="updateConstraint(${index}, 'enabled', this.checked)"></td>
        </tr>
      `).join('');
      const tbody = document.getElementById('constraintRows');
      if (tbody) tbody.innerHTML = rows;
      renderConstraintFailures();
    }

    function collectConstraintFailures() {
      const errors = [];
      const warnings = [];
      const seenStationLayer = new Set();

      const enabled = flagConstraints.filter(c => c && c.enabled);
      enabled.forEach(constraint => {
        if (constraint.type === 'length_step' && numberOr(constraint.value, 0) <= 0) {
          errors.push('Length step must be greater than 0.');
        }
        if (constraint.type === 'min_tip_ratio') {
          const ratio = numberOr(constraint.value, 0);
          if (ratio <= 0 || ratio > 1) {
            errors.push('Min tip ratio must be > 0 and <= 1.');
          }
        }
        if (constraint.type === 'bias_pair_angle_abs') {
          const angle = Math.abs(numberOr(constraint.value, 0));
          if (angle <= 0 || angle >= 90) {
            errors.push('Bias pair angle must be between 0 and 90 degrees.');
          }
        }
      });

      flags.forEach((flag, index) => {
        const name = flag?.name || `Flag ${index + 1}`;
        const root = numberOr(flag?.root, NaN);
        const tip = numberOr(flag?.tip, NaN);
        const station = String(flag?.station || 'Custom').trim().toLowerCase();
        const layer = String(flag?.layer || 'custom').trim().toLowerCase();
        const key = `${station}|${layer}`;
        if (seenStationLayer.has(key)) {
          warnings.push(`${name}: station conflict (${flag.station}/${flag.layer}) duplicated.`);
        } else {
          seenStationLayer.add(key);
        }
        if (Number.isFinite(root) && Number.isFinite(tip) && tip > root) {
          warnings.push(`${name}: tip width is greater than root width; taper may be non-manufacturable.`);
        }

        const h = flagConstraints.find(c => c.id === `flag_${index}_horizontal` && c.enabled);
        const v = flagConstraints.find(c => c.id === `flag_${index}_vertical` && c.enabled);
        const a = flagConstraints.find(c => c.id === `flag_${index}_angle` && c.enabled);
        const l = flagConstraints.find(c => c.id === `flag_${index}_length` && c.enabled);

        if (h && v) errors.push(`${name}: over-constrained (horizontal + vertical both active).`);
        if (h && a) errors.push(`${name}: over-constrained (horizontal conflicts with explicit angle).`);
        if (l && numberOr(l.value, 0) <= 0) errors.push(`${name}: explicit length must be > 0.`);
      });

      flagConstraints.forEach(constraint => {
        const m = /^flag_(\\d+)_/.exec(String(constraint.id || ''));
        if (m) {
          const idx = Number(m[1]);
          if (!Number.isInteger(idx) || idx < 0 || idx >= flags.length) {
            warnings.push(`Constraint ${constraint.id} points to a missing flag index.`);
          }
        }
      });
      return { errors, warnings };
    }

    function renderConstraintFailures() {
      const tbody = document.getElementById('constraintFailureRows');
      if (!tbody) return;
      const state = collectConstraintFailures();
      const rows = [];
      if (state.errors.length === 0 && state.warnings.length === 0) {
        rows.push(['OK', 'No constraint conflicts found.']);
      } else {
        state.errors.slice(0, 8).forEach(msg => rows.push(['Error', msg]));
        state.warnings.slice(0, 8).forEach(msg => rows.push(['Warn', msg]));
      }
      tbody.innerHTML = rows.map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
    }

    function updateConstraint(index, key, value) {
      if (!flagConstraints[index]) return;
      if (key === 'enabled') {
        flagConstraints[index][key] = Boolean(value);
      } else if (key === 'value') {
        flagConstraints[index][key] = numberOr(value, flagConstraints[index][key]);
      } else {
        flagConstraints[index][key] = value;
      }
      drawFlags();
    }

    function selectedConstraintValue() {
      return numberOr(document.getElementById('constraintValueInput')?.value, 0);
    }

    function clearFlagConstraintByType(flagIndex, type) {
      let changed = false;
      flagConstraints.forEach(constraint => {
        if (constraint.id === `flag_${flagIndex}_${type}` && constraint.enabled) {
          constraint.enabled = false;
          changed = true;
        }
      });
      return changed;
    }

    function upsertFlagConstraint(flagIndex, type, value, enabled, scope) {
      const id = `flag_${flagIndex}_${type}`;
      const existing = flagConstraints.find(c => c.id === id);
      if (existing) {
        existing.value = numberOr(value, existing.value);
        existing.enabled = Boolean(enabled);
        existing.scope = scope || existing.scope;
        return existing;
      }
      const created = {
        id,
        type,
        scope: scope || `flag ${flagIndex + 1}`,
        value: numberOr(value, 0),
        enabled: Boolean(enabled)
      };
      flagConstraints.push(created);
      return created;
    }

    function applySelectedConstraint(type, button) {
      if (selectedFlagIndex === null || !flags[selectedFlagIndex]) {
        setAppStatus('Select a flag first, then apply a constraint.', true);
        writeCadConsole('Constraint action blocked: no selected flag.');
        return;
      }
      flashButton(button, 'Applied');
      const flag = flags[selectedFlagIndex];
      const value = selectedConstraintValue();
      let conflictNote = '';

      if (type === 'horizontal') {
        if (clearFlagConstraintByType(selectedFlagIndex, 'angle')) {
          conflictNote = 'Angle constraint disabled due to horizontal lock.';
        }
        upsertFlagConstraint(selectedFlagIndex, 'horizontal', 1, true, `${flag.name} horizontal`);
      } else if (type === 'vertical') {
        upsertFlagConstraint(selectedFlagIndex, 'vertical', 1, true, `${flag.name} vertical`);
      } else if (type === 'length') {
        if (value <= 0) {
          setAppStatus('Length constraint must be greater than 0.', true);
          return;
        }
        upsertFlagConstraint(selectedFlagIndex, 'length', value, true, `${flag.name} length`);
      } else if (type === 'angle') {
        const clamped = Math.max(-89, Math.min(89, value));
        if (clearFlagConstraintByType(selectedFlagIndex, 'horizontal')) {
          conflictNote = 'Horizontal constraint disabled due to explicit angle.';
        }
        upsertFlagConstraint(selectedFlagIndex, 'angle', clamped, true, `${flag.name} angle`);
      }

      if (conflictNote) writeCadConsole(conflictNote);
      applyFlagConstraints();
      renderConstraintTable();
      drawFlags();
    }

    function applyFlagConstraints(button) {
      if (button) flashButton(button, 'Applied');
      normalizeFlags();
      ensureConstraintCoverage();
      const failures = collectConstraintFailures();
      if (failures.errors.length > 0) {
        renderConstraintFailures();
        setAppStatus(`Constraint solver failed: ${failures.errors[0]}`, true);
        writeCadConsole(`Constraint solve failed with ${failures.errors.length} error(s).`);
        return;
      }
      let adjustments = 0;
      const byType = type => flagConstraints.find(c => c.type === type && c.enabled);
      const lengthStep = byType('length_step');
      const minTipRatio = byType('min_tip_ratio');
      const biasAbs = byType('bias_pair_angle_abs');

      flags = flags.map((flag, index) => {
        let next = normalizeFlag(flag);
        if (lengthStep && lengthStep.value > 0) {
          const snapped = Math.round(next.length / lengthStep.value) * lengthStep.value;
          if (snapped !== next.length) adjustments++;
          next.length = Math.max(60, snapped);
        }
        if (minTipRatio && minTipRatio.value > 0) {
          const minTip = next.root * minTipRatio.value;
          if (next.tip < minTip) {
            next.tip = Math.max(4, minTip);
            adjustments++;
          }
        }
        const h = flagConstraints.find(c => c.id === `flag_${index}_horizontal` && c.enabled);
        if (h && next.angle !== 0) {
          next.angle = 0;
          adjustments++;
        }
        const explicitAngle = flagConstraints.find(c => c.id === `flag_${index}_angle` && c.enabled);
        if (explicitAngle) {
          const angleTarget = Math.max(-89, Math.min(89, numberOr(explicitAngle.value, next.angle)));
          if (next.angle !== angleTarget) {
            next.angle = angleTarget;
            adjustments++;
          }
        }
        const explicitLength = flagConstraints.find(c => c.id === `flag_${index}_length` && c.enabled);
        if (explicitLength) {
          const lenTarget = Math.max(60, numberOr(explicitLength.value, next.length));
          if (next.length !== lenTarget) {
            next.length = lenTarget;
            adjustments++;
          }
        }
        if (biasAbs && next.layer.toLowerCase().includes('bias')) {
          const target = Math.abs(biasAbs.value);
          const sign = next.angle < 0 ? -1 : 1;
          const angled = sign * target;
          if (next.angle !== angled) {
            next.angle = angled;
            adjustments++;
          }
        }
        return next;
      });
      updateFlagTableValues();
      drawFlags();
      renderConstraintFailures();
      writeCadConsole(`Constraint solver applied (${adjustments} adjustment${adjustments === 1 ? '' : 's'}).`);
      setAppStatus(`Constraint solver applied: ${adjustments} adjustment${adjustments === 1 ? '' : 's'}.`);
    }

    function resetFlagConstraints(button) {
      flashButton(button, 'Reset');
      flagConstraints = defaultFlagConstraints(flags.length);
      renderConstraintTable();
      drawFlags();
      writeCadConsole('Constraint set reset to defaults.');
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
      if (viewName === 'drawing') drawDesign(latest);
      if (viewName === 'fit') renderFitBridge();
      if (viewName === 'flags') renderFlagEditor();
      if (viewName === 'tape') renderTapeCad();
      if (viewName === 'stack') renderStackCad();
      if (viewName === 'cad3d') {
        updateArchitecturePanel();
        drawCad3d();
      }
    }

    function setSketchTool(tool, button) {
      if (isViewerMode()) return;
      sketchTool = tool;
      document.querySelectorAll('.cad-tool, .sketch-icon').forEach(item => item.classList.remove('active'));
      if (button) button.classList.add('active');
      drawFlags();
    }

    function handleSketchMenu(action, button) {
      if (button) flashButton(button, 'OK');
      if (action === 'file') {
        writeCadConsole('Sketch menu: File -> use Save Project / Load Project below.');
      } else if (action === 'edit') {
        writeCadConsole('Sketch menu: Edit -> select a flag and use Duplicate/Delete/Mirror.');
      } else if (action === 'view') {
        const snap = document.getElementById('snapGrid');
        if (snap) snap.checked = !snap.checked;
        drawFlags();
        writeCadConsole(`Sketch menu: View -> Snap grid ${snap && snap.checked ? 'ON' : 'OFF'}.`);
      } else if (action === 'new-group') {
        addFlag();
        writeCadConsole('Sketch menu: New Group -> added new flag group.');
      } else if (action === 'sketch') {
        setSketchTool('line');
        writeCadConsole('Sketch menu: Sketch -> line tool active.');
      } else if (action === 'constrain') {
        applyFlagConstraints();
        writeCadConsole('Sketch menu: Constrain -> applied active constraints.');
      } else if (action === 'analyze') {
        run();
        writeCadConsole('Sketch menu: Analyze -> shaft analysis started.');
      } else if (action === 'help') {
        setAppStatus('Sketch help: select flag, drag corner or L/R/T handles, then apply constraints.');
        writeCadConsole('Sketch menu: Help -> interaction guide posted in status bar.');
      }
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
          gcode_pass_count: document.getElementById('passCount').value,
          cpm_clamp_length_in: document.getElementById('cpmClampIn')?.value || '5.0',
          cpm_overall_weight_g: document.getElementById('cpmOverallWeight')?.value || '205',
          cpm_profile_weight_g: document.getElementById('cpmProfileWeight')?.value || '255',
          cpm_overall_k: document.getElementById('cpmOverallK')?.value || '14.7',
          cpm_zone_k: document.getElementById('cpmZoneK')?.value || '8.5'
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
        ['Clamp Length', (latest.cpm_calibration?.clamp_length_in ?? 5).toFixed(2) + ' in'],
        ['CPM Weights', `${(latest.cpm_calibration?.overall_weight_g ?? 205).toFixed(0)}g / ${(latest.cpm_calibration?.profile_weight_g ?? 255).toFixed(0)}g`],
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
      updateValidationReadout();
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

    function buildFitCadPacket() {
      if (!latestFitProfile) return null;
      const targetCpm = numberOr(document.getElementById('target')?.value, latestFitProfile.target_cpm);
      const wrapAngle = numberOr(document.getElementById('angle')?.value, latestFitProfile.wrap_angle_deg);
      const cadFlagCount = flags.length;
      return {
        version: 'ae-fitcad-1',
        generated_at: new Date().toISOString(),
        fitting_target: latestFitProfile,
        cad_state: {
          target_cpm_input: targetCpm,
          wrap_angle_input: wrapAngle,
          flag_count: cadFlagCount,
          architecture_mode: document.getElementById('architectureMode')?.value || 'flag_wrap'
        },
        transfer: {
          set_target_cpm: latestFitProfile.target_cpm,
          set_wrap_angle_deg: latestFitProfile.wrap_angle_deg,
          bias_pair_deg: [latestFitProfile.wrap_angle_deg, -latestFitProfile.wrap_angle_deg],
          tip_strategy: latestFitProfile.tip_strategy
        }
      };
    }

    function renderFitBridge(direction) {
      const chip = document.getElementById('fitSyncState');
      const table = document.getElementById('fitBridge');
      const score = document.getElementById('fitScore');
      if (!table || !score) return;

      if (!latestFitProfile) {
        if (chip) chip.textContent = 'Waiting on fit target';
        table.innerHTML = '<tr><td colspan="2">Generate a fit target to initialize bridge packet.</td></tr>';
        score.innerHTML = '<tr><td colspan="2">No score yet.</td></tr>';
        return;
      }

      fitCadBridge = {
        direction: direction || (fitCadBridge?.direction || 'fit-generated'),
        synced_at: new Date().toLocaleTimeString(),
        packet: buildFitCadPacket()
      };

      const packet = fitCadBridge.packet;
      if (chip) chip.textContent = `${fitCadBridge.direction} @ ${fitCadBridge.synced_at}`;
      table.innerHTML = [
        ['Direction', fitCadBridge.direction],
        ['Synced At', fitCadBridge.synced_at],
        ['Packet Version', packet.version],
        ['CAD Mode', packet.cad_state.architecture_mode],
        ['CAD Flag Count', String(packet.cad_state.flag_count)],
        ['Transfer CPM', packet.transfer.set_target_cpm.toFixed(1)],
        ['Transfer Wrap Angle', packet.transfer.set_wrap_angle_deg.toFixed(0) + ' deg']
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');

      const cpmDelta = Math.abs(packet.transfer.set_target_cpm - packet.cad_state.target_cpm_input);
      const wrapDelta = Math.abs(packet.transfer.set_wrap_angle_deg - packet.cad_state.wrap_angle_input);
      const fitQuality = Math.max(0, 100 - cpmDelta * 6 - wrapDelta * 1.6);
      const torqueWindow = latestFitProfile.torque_target_deg <= 3.4 ? 'Stout' : latestFitProfile.torque_target_deg <= 3.9 ? 'Balanced' : 'Active';
      score.innerHTML = [
        ['Fit Quality Index', fitQuality.toFixed(1) + ' / 100'],
        ['CPM Alignment Error', cpmDelta.toFixed(2)],
        ['Angle Alignment Error', wrapDelta.toFixed(2) + ' deg'],
        ['Torque Window', torqueWindow],
        ['Launch Intent', latestFitProfile.launch_bias]
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
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
      renderFitBridge('fit-generated');
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
      designHistoryCommit('fit->cad apply');
      run();
      renderFitBridge('fit->cad apply');
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

    function downloadFitCadPacket(button) {
      if (!latestFitProfile) runFitToBuild(button);
      const packet = buildFitCadPacket();
      if (!packet) return;
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify(packet, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaft-fit-cad-bridge-packet.json';
      a.click();
      URL.revokeObjectURL(url);
      renderFitBridge('fit->cad packet');
      writeCadConsole('Exported Fit/CAD bridge packet.');
    }

    function pullCadIntoFit(button) {
      const speed = numberOr(document.getElementById('speed')?.value, 105);
      const target = numberOr(document.getElementById('target')?.value, 255);
      const angle = numberOr(document.getElementById('angle')?.value, 45);
      const launch = latest?.launch_simulation?.launch_angle_deg ?? 13.5;
      const spin = latest?.launch_simulation?.spin_rpm ?? 2650;
      document.getElementById('fitSpeed').value = speed.toFixed(0);
      document.getElementById('fitLaunch').value = Number(launch).toFixed(1);
      document.getElementById('fitSpin').value = Number(spin).toFixed(0);
      if (angle >= 50) {
        document.getElementById('fitTransition').value = 'Hard';
      } else if (angle <= 38) {
        document.getElementById('fitTransition').value = 'Smooth';
      } else {
        document.getElementById('fitTransition').value = 'Medium';
      }
      flashButton(button, 'Pulled');
      runFitToBuild();
      if (latestFitProfile) latestFitProfile.target_cpm = target;
      renderFitBridge('cad->fit pull');
      writeCadConsole('Pulled CAD state into fitting inputs and regenerated fit target.');
    }

    function drawingSnap(value) {
      const snap = document.getElementById('drawSnapGrid');
      return snap && snap.checked ? Math.round(value / 5) * 5 : value;
    }

    function setDrawingTool(tool, button) {
      if (isViewerMode()) return;
      drawingTool = tool;
      document.querySelectorAll('#drawingView .cad-tool').forEach(item => item.classList.remove('active'));
      if (button) button.classList.add('active');
      const selection = document.getElementById('drawSelectionLabel');
      if (selection) {
        selection.textContent = `Tool: ${tool} | ${selectedDrawingStationIndex === null ? 'No station selected' : `S${selectedDrawingStationIndex + 1} selected`}`;
      }
      drawDesign(latest);
    }

    function defaultDrawingStations() {
      return [
        { z: 0, od: 15.0 },
        { z: 254, od: 13.0 },
        { z: 508, od: 11.0 },
        { z: 762, od: 9.0 },
        { z: 1016, od: 7.0 }
      ];
    }

    function ensureDrawingStations() {
      if (!drawingStations.length) drawingStations = defaultDrawingStations();
      drawingStations = drawingStations
        .map(s => ({ z: Math.max(0, numberOr(s.z, 0)), od: Math.max(1, numberOr(s.od, 1)) }))
        .sort((a, b) => a.z - b.z);
      if (selectedDrawingStationIndex !== null) {
        selectedDrawingStationIndex = Math.max(0, Math.min(selectedDrawingStationIndex, drawingStations.length - 1));
      }
    }

    function renderDrawingStationRows() {
      const tbody = document.getElementById('drawingStationsRows');
      if (!tbody) return;
      tbody.innerHTML = drawingStations.map((s, i) => `
        <tr style="${selectedDrawingStationIndex === i ? 'background:#e5f5f1;' : ''}">
          <td>${i + 1}</td>
          <td><input type="number" value="${Math.round(s.z)}" step="1" onchange="updateDrawingStation(${i}, 'z', this.value)"></td>
          <td><input type="number" value="${s.od.toFixed(2)}" step="0.1" onchange="updateDrawingStation(${i}, 'od', this.value)"></td>
        </tr>
      `).join('');
    }

    function updateDrawingStation(index, key, value) {
      if (!drawingStations[index]) return;
      drawingStations[index][key] = numberOr(value, drawingStations[index][key]);
      ensureDrawingStations();
      designHistoryCommit(`drawing station ${index + 1} ${key}`);
      drawDesign(latest);
    }

    function addDrawingStation(button) {
      ensureDrawingStations();
      const last = drawingStations[drawingStations.length - 1];
      const prev = drawingStations[drawingStations.length - 2] || { z: 0, od: 15 };
      const newZ = Math.max(1, Math.round((prev.z + last.z) / 2));
      const newOd = Math.max(1, (prev.od + last.od) / 2);
      drawingStations.splice(drawingStations.length - 1, 0, { z: newZ, od: newOd });
      selectedDrawingStationIndex = drawingStations.length - 2;
      if (button) flashButton(button, 'Added');
      designHistoryCommit('drawing station added');
      drawDesign(latest);
    }

    function deleteSelectedDrawingStation(button) {
      ensureDrawingStations();
      if (selectedDrawingStationIndex === null || drawingStations.length <= 2) return;
      if (selectedDrawingStationIndex === 0 || selectedDrawingStationIndex === drawingStations.length - 1) return;
      drawingStations.splice(selectedDrawingStationIndex, 1);
      selectedDrawingStationIndex = Math.min(selectedDrawingStationIndex, drawingStations.length - 1);
      if (button) flashButton(button, 'Deleted');
      designHistoryCommit('drawing station deleted');
      drawDesign(latest);
    }

    function resetDrawingProfile(button) {
      drawingStations = defaultDrawingStations();
      selectedDrawingStationIndex = null;
      if (button) flashButton(button, 'Reset');
      designHistoryCommit('drawing profile reset');
      drawDesign(latest);
    }

    function drawingCanvasPoint(event) {
      const canvas = document.getElementById('designCanvas');
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * canvas.width / rect.width,
        y: (event.clientY - rect.top) * canvas.height / rect.height
      };
    }

    function drawingMouseDown(event) {
      if (isViewerMode()) return;
      ensureDrawingStations();
      const canvas = document.getElementById('designCanvas');
      const left = 76;
      const right = canvas.width - 72;
      const centerY = 205;
      const bottomBand = 338;
      const p = drawingCanvasPoint(event);
      const totalLength = drawingStations[drawingStations.length - 1].z || 1016;
      const maxOd = Math.max(...drawingStations.map(s => s.od), 1);
      let best = null;
      drawingStations.forEach((s, i) => {
        const x = left + (s.z / totalLength) * (right - left);
        const y = centerY - (s.od / maxOd) * (bottomBand - centerY) * 0.6;
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < 12 && (!best || d < best.d)) best = { i, d };
      });
      if (best) {
        selectedDrawingStationIndex = best.i;
        drawingDragActive = drawingTool === 'move' || drawingTool === 'select';
      } else {
        if (drawingTool === 'add') {
          const z = Math.max(1, Math.min(totalLength - 1, drawingSnap(((p.x - left) / (right - left)) * totalLength)));
          let insertIndex = drawingStations.findIndex(s => s.z > z);
          if (insertIndex < 0) insertIndex = drawingStations.length - 1;
          if (insertIndex <= 0) insertIndex = 1;
          const prev = drawingStations[insertIndex - 1];
          const next = drawingStations[insertIndex];
          const t = (z - prev.z) / Math.max(1, next.z - prev.z);
          const interpOd = prev.od + (next.od - prev.od) * t;
          drawingStations.splice(insertIndex, 0, { z, od: Math.max(1, drawingSnap(interpOd)) });
          selectedDrawingStationIndex = insertIndex;
          drawingDragActive = false;
        } else {
          selectedDrawingStationIndex = null;
        }
        drawingDragActive = false;
      }
      if (drawingTool === 'delete' && selectedDrawingStationIndex !== null) {
        deleteSelectedDrawingStation();
      }
      drawDesign(latest);
    }

    function drawingMouseMove(event) {
      if (isViewerMode()) return;
      if (!drawingDragActive || selectedDrawingStationIndex === null) return;
      if (drawingTool !== 'move' && drawingTool !== 'select') return;
      const canvas = document.getElementById('designCanvas');
      const left = 76;
      const right = canvas.width - 72;
      const centerY = 205;
      const bottomBand = 338;
      const p = drawingCanvasPoint(event);
      ensureDrawingStations();
      const totalLength = drawingStations[drawingStations.length - 1].z || 1016;
      const maxOd = Math.max(...drawingStations.map(s => s.od), 1);

      const station = drawingStations[selectedDrawingStationIndex];
      if (selectedDrawingStationIndex !== 0 && selectedDrawingStationIndex !== drawingStations.length - 1) {
        const zRaw = ((p.x - left) / (right - left)) * totalLength;
        const prevZ = drawingStations[selectedDrawingStationIndex - 1].z + 5;
        const nextZ = drawingStations[selectedDrawingStationIndex + 1].z - 5;
        if (!(document.getElementById('drawOrthoLock')?.checked)) {
          station.z = Math.max(prevZ, Math.min(nextZ, drawingSnap(zRaw)));
        }
      }
      const yClamp = Math.max(80, Math.min(bottomBand - 10, p.y));
      const odRaw = ((centerY - yClamp) / ((bottomBand - centerY) * 0.6)) * maxOd;
      station.od = Math.max(1, drawingSnap(Math.abs(odRaw)));
      drawDesign(latest);
    }

    function drawingMouseUp() {
      drawingDragActive = false;
    }

    function drawDesign(data) {
      ensureDrawingStations();
      const canvas = document.getElementById('designCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const left = 76;
      const right = canvas.width - 72;
      const centerY = 205;
      const topBand = 72;
      const bottomBand = 338;
      const totalLength = drawingStations[drawingStations.length - 1].z || 1016;
      const maxOd = Math.max(...drawingStations.map(s => s.od), 1);
      const mapX = z => left + (z / totalLength) * (right - left);
      const mapYTop = od => centerY - (od / maxOd) * (bottomBand - centerY) * 0.6;
      const mapYBottom = od => centerY + (od / maxOd) * (bottomBand - centerY) * 0.6;

      ctx.fillStyle = '#101918';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#243532';
      ctx.lineWidth = 1;
      for (let x = left; x <= right; x += 50) {
        ctx.beginPath(); ctx.moveTo(x, topBand); ctx.lineTo(x, bottomBand); ctx.stroke();
      }
      for (let y = topBand; y <= bottomBand; y += 34) {
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
      }

      ctx.beginPath();
      drawingStations.forEach((s, i) => {
        const x = mapX(s.z);
        const y = mapYTop(s.od);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      for (let i = drawingStations.length - 1; i >= 0; i--) {
        const s = drawingStations[i];
        ctx.lineTo(mapX(s.z), mapYBottom(s.od));
      }
      ctx.closePath();
      ctx.fillStyle = '#d7fff6';
      ctx.globalAlpha = 0.88;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#35c7b2';
      ctx.lineWidth = 2;
      ctx.stroke();

      drawingStations.forEach((s, i) => {
        const x = mapX(s.z);
        const y = mapYTop(s.od);
        ctx.fillStyle = selectedDrawingStationIndex === i ? '#f2b84b' : '#ffffff';
        ctx.strokeStyle = '#0f3d38';
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#f2b84b';
        ctx.font = '11px Arial';
        ctx.fillText(`${Math.round(s.z)}mm / ${s.od.toFixed(1)}mm`, x - 30, y - 10);
      });

      if (drawingTool === 'dimension' && selectedDrawingStationIndex !== null && drawingStations[selectedDrawingStationIndex + 1]) {
        const a = drawingStations[selectedDrawingStationIndex];
        const b = drawingStations[selectedDrawingStationIndex + 1];
        const ax = mapX(a.z);
        const bx = mapX(b.z);
        const y = bottomBand + 20;
        drawDimension(ctx, ax, y, bx, y, `${Math.round(b.z - a.z)} mm`);
      }

      const toolText = drawingDragActive ? 'Drag station' : selectedDrawingStationIndex === null ? 'Select station' : `Station #${selectedDrawingStationIndex + 1}`;
      const drawLength = document.getElementById('drawLength');
      if (drawLength) drawLength.textContent = `${Math.round(totalLength)} mm`;
      const drawButt = document.getElementById('drawButt');
      if (drawButt) drawButt.textContent = `${drawingStations[0].od.toFixed(1)} mm`;
      const drawTip = document.getElementById('drawTip');
      if (drawTip) drawTip.textContent = `${drawingStations[drawingStations.length - 1].od.toFixed(1)} mm`;
      const drawTool = document.getElementById('drawTool');
      if (drawTool) drawTool.textContent = `${drawingTool} | ${toolText}`;
      const selection = document.getElementById('drawSelectionLabel');
      if (selection) {
        selection.textContent = selectedDrawingStationIndex === null
          ? `Tool: ${drawingTool} | No station selected`
          : `Tool: ${drawingTool} | S${selectedDrawingStationIndex + 1} @ ${Math.round(drawingStations[selectedDrawingStationIndex].z)} mm, OD ${drawingStations[selectedDrawingStationIndex].od.toFixed(1)} mm`;
      }
      document.getElementById('drawingDims').innerHTML = [
        ['Overall Length', `${Math.round(totalLength)} mm / ${(totalLength / 25.4).toFixed(2)} in`],
        ['Butt OD', `${drawingStations[0].od.toFixed(1)} mm`],
        ['Tip OD', `${drawingStations[drawingStations.length - 1].od.toFixed(1)} mm`],
        ['Station Count', String(drawingStations.length)],
        ['Selected Station', selectedDrawingStationIndex === null ? 'none' : `#${selectedDrawingStationIndex + 1}`],
        ['G-Code Units', data?.gcode_settings?.units || 'mm'],
        ['Pass Count', String(data?.gcode_settings?.pass_count ?? '-')]
      ].map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');
      document.getElementById('segmentSchedule').innerHTML = drawingStations.map((s, i) =>
        `<tr><td>S${i + 1}</td><td>${s.od.toFixed(1)} mm</td><td>${Math.round(s.z)} mm</td></tr>`
      ).join('');
      renderDrawingStationRows();
    }

    function renderFlagEditor() {
      normalizeFlags();
      ensureConstraintCoverage();
      if (selectedFlagIndex !== null && selectedFlagIndex >= flags.length) selectedFlagIndex = flags.length - 1;
      if (flags.length === 0) selectedFlagIndex = null;
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
      renderConstraintTable();
      drawFlags();
    }

    function requireSelectedFlag(actionName) {
      if (selectedFlagIndex === null || !flags[selectedFlagIndex]) {
        setAppStatus(`${actionName} blocked: select a flag first.`, true);
        writeCadConsole(`${actionName} blocked: no selected flag.`);
        return false;
      }
      return true;
    }

    function selectAdjacentFlag(step, button) {
      if (!flags.length) return;
      if (button) flashButton(button, 'Selected');
      if (selectedFlagIndex === null) {
        selectedFlagIndex = step >= 0 ? 0 : flags.length - 1;
      } else {
        const next = selectedFlagIndex + step;
        selectedFlagIndex = ((next % flags.length) + flags.length) % flags.length;
      }
      drawFlags();
    }

    function duplicateSelectedFlag(button) {
      if (!requireSelectedFlag('Duplicate flag')) return;
      flashButton(button, 'Duplicated');
      const source = normalizeFlag(flags[selectedFlagIndex]);
      const clone = {
        ...source,
        name: `${source.name} copy`,
        station: source.station || 'Custom'
      };
      flags.splice(selectedFlagIndex + 1, 0, clone);
      selectedFlagIndex += 1;
      flagConstraints = defaultFlagConstraints(flags.length);
      renderFlagEditor();
      writeCadConsole(`Duplicated flag: ${source.name}`);
    }

    function deleteSelectedFlag(button) {
      if (!requireSelectedFlag('Delete selected flag')) return;
      flashButton(button, 'Deleted');
      const removed = flags[selectedFlagIndex];
      flags.splice(selectedFlagIndex, 1);
      if (flags.length === 0) selectedFlagIndex = null;
      else selectedFlagIndex = Math.min(selectedFlagIndex, flags.length - 1);
      flagConstraints = defaultFlagConstraints(flags.length);
      renderFlagEditor();
      writeCadConsole(`Deleted selected flag: ${removed.name}`);
    }

    function mirrorSelectedFlagAngle(button) {
      if (!requireSelectedFlag('Mirror angle')) return;
      flashButton(button, 'Mirrored');
      const flag = flags[selectedFlagIndex];
      flag.angle = -numberOr(flag.angle, 0);
      updateFlagTableValues();
      drawFlags();
      writeCadConsole(`Mirrored angle for ${flag.name} to ${flag.angle} deg.`);
    }

    function applyDimensionPreset(scope, button) {
      const lengthInput = document.getElementById('dimLengthInput');
      const rootInput = document.getElementById('dimRootInput');
      const tipInput = document.getElementById('dimTipInput');
      const angleRule = document.getElementById('dimAngleRule')?.value || 'keep';
      if (!lengthInput || !rootInput || !tipInput) return;

      const targetLength = Math.max(1, numberOr(lengthInput.value, 360));
      const targetRoot = Math.max(1, numberOr(rootInput.value, 76));
      const targetTip = Math.max(1, numberOr(tipInput.value, 58));

      const applyAngle = (flag, index) => {
        if (angleRule === 'zero') {
          flag.angle = 0;
        } else if (angleRule === 'bias_pair') {
          if ((flag.layer || '').toLowerCase().includes('bias') || /bias/i.test(flag.name || '')) {
            flag.angle = index % 2 === 0 ? 45 : -45;
          }
        }
      };

      if (scope === 'selected') {
        if (!requireSelectedFlag('Apply dimension preset')) return;
        const selected = flags[selectedFlagIndex];
        selected.length = targetLength;
        selected.root = targetRoot;
        selected.tip = targetTip;
        applyAngle(selected, selectedFlagIndex);
        flags[selectedFlagIndex] = normalizeFlag(selected);
      } else if (scope === 'all') {
        flags = flags.map((flag, index) => {
          const next = { ...flag, length: targetLength, root: targetRoot, tip: targetTip };
          applyAngle(next, index);
          return normalizeFlag(next);
        });
      } else if (scope === 'progressive') {
        const count = Math.max(flags.length - 1, 1);
        flags = flags.map((flag, index) => {
          const t = index / count;
          const length = targetLength - t * Math.max(0, targetLength * 0.28);
          const root = targetRoot - t * Math.max(0, targetRoot * 0.35);
          const tip = targetTip - t * Math.max(0, targetTip * 0.35);
          const next = { ...flag, length, root, tip };
          applyAngle(next, index);
          return normalizeFlag(next);
        });
      }

      if (button) flashButton(button, 'Applied');
      updateFlagTableValues();
      drawFlags();
      renderConstraintTable();
      updateValidationReadout();
      writeCadConsole(`Dimension preset applied (${scope}).`);
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
        flags[index][key] = numberOr(value, flags[index][key]);
      } else {
        flags[index][key] = value;
      }
      flags[index] = normalizeFlag(flags[index]);
      designHistoryCommit(`flag ${index + 1} updated`);
      drawFlags();
    }

    function addFlag(button) {
      flashButton(button, 'Added');
      flags.push({name: 'New flag', length: 320, root: 70, tip: 48, angle: 0, station: 'Custom', layer: 'custom', locked: false});
      ensureConstraintCoverage();
      designHistoryCommit('flag added');
      renderFlagEditor();
    }

    function addTriangleFlag(button) {
      flashButton(button, 'Added');
      flags.push({name: 'Triangle bias flag', length: 340, root: 76, tip: 4, angle: 45, station: 'Custom', layer: 'bias', locked: false});
      ensureConstraintCoverage();
      designHistoryCommit('triangle flag added');
      renderFlagEditor();
    }

    function deleteFlag(index, button) {
      flashButton(button, 'Deleted');
      flags.splice(index, 1);
      flagConstraints = defaultFlagConstraints(flags.length);
      designHistoryCommit('flag deleted');
      renderFlagEditor();
    }

    function resetFlags(button) {
      flashButton(button, 'Reset');
      flags = defaultFlags();
      flagConstraints = defaultFlagConstraints(flags.length);
      designHistoryCommit('flags reset');
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
      if (isViewerMode()) return;
      const point = canvasPoint(event);
      let dimBest = null;
      dimensionHandles.forEach(handle => {
        const d = Math.hypot(point.x - handle.x, point.y - handle.y);
        if (d < 13 && (!dimBest || d < dimBest.distance)) {
          dimBest = { ...handle, distance: d };
        }
      });
      if (dimBest) {
        selectedFlagIndex = dimBest.flagIndex;
        activeDrag = { kind: 'dimension', flagIndex: dimBest.flagIndex, dimension: dimBest.dimension };
        drawFlags();
        return;
      }
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
        activeDrag = { kind: 'corner', ...best };
        drawFlags();
        return;
      }
      selectedFlagIndex = null;
      activeDrag = null;
      drawFlags();
    }

    function flagMouseMove(event) {
      if (isViewerMode()) return;
      if (!activeDrag) return;
      const point = canvasPoint(event);
      const geometry = flagGeometry[activeDrag.flagIndex];
      if (!geometry) return;
      const flag = flags[activeDrag.flagIndex];
      if (document.getElementById('lockDimensions').checked || flag.locked) return;
      if (activeDrag.kind === 'dimension') {
        if (activeDrag.dimension === 'length') {
          flag.length = Math.max(60, snapValue((point.x - geometry.x) / geometry.scale));
        } else if (activeDrag.dimension === 'root') {
          flag.root = Math.max(8, snapValue((Math.abs(point.y - geometry.y) * 2) / geometry.scale));
        } else if (activeDrag.dimension === 'tip') {
          flag.tip = Math.max(8, snapValue((Math.abs(point.y - geometry.y) * 2) / geometry.scale));
        }
        flags[activeDrag.flagIndex] = normalizeFlag(flag);
        updateFlagTableValues();
        drawFlags();
        return;
      }
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
      if (isViewerMode()) return;
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

    function drawDimHandle(ctx, x, y, label, active) {
      ctx.beginPath();
      ctx.fillStyle = active ? '#ff2d20' : '#b24ac7';
      ctx.strokeStyle = '#f4d3ff';
      ctx.lineWidth = 1.5;
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#f4d3ff';
      ctx.font = '700 11px Arial';
      ctx.fillText(label, x - 10, y - 12);
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
      dimensionHandles = [];
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

        if (selectedFlagIndex === index) {
          const lengthHandle = { x: x + flag.length * scale, y: y + flag.root * scale / 2 + 30, flagIndex: index, dimension: 'length' };
          const rootHandle = { x: x - 18, y, flagIndex: index, dimension: 'root' };
          const tipHandle = { x: x + flag.length * scale + 22, y, flagIndex: index, dimension: 'tip' };
          dimensionHandles.push(lengthHandle, rootHandle, tipHandle);
          drawDimHandle(
            ctx,
            lengthHandle.x,
            lengthHandle.y,
            'L',
            activeDrag && activeDrag.kind === 'dimension' && activeDrag.flagIndex === index && activeDrag.dimension === 'length'
          );
          drawDimHandle(
            ctx,
            rootHandle.x,
            rootHandle.y,
            'R',
            activeDrag && activeDrag.kind === 'dimension' && activeDrag.flagIndex === index && activeDrag.dimension === 'root'
          );
          drawDimHandle(
            ctx,
            tipHandle.x,
            tipHandle.y,
            'T',
            activeDrag && activeDrag.kind === 'dimension' && activeDrag.flagIndex === index && activeDrag.dimension === 'tip'
          );
        }
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
      updateValidationReadout();
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
      if (!ensureExportReady('Flag JSON export', false)) return;
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
      if (!ensureExportReady('Flag SVG export', false)) return;
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
      return lines.join('\\n');
    }

    function downloadFlagDxf(button) {
      if (!ensureExportReady('Flag DXF export', false)) return;
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
      updateValidationReadout();
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
      updateValidationReadout();
      designHistoryCommit(`tape ${index + 1} updated`);
    }

    function addTape(button) {
      flashButton(button, 'Added');
      tapes.push({name: 'New UD tape strip', startIn: 31, length: 200, width: 10, thickness: 0.125, angle: 0, layer: 'between braid layers'});
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
      updateValidationReadout();
      designHistoryCommit('tape strip added');
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
      updateValidationReadout();
      designHistoryCommit('bias tape pair added');
    }

    function deleteTape(index, button) {
      flashButton(button, 'Deleted');
      tapes.splice(index, 1);
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
      updateValidationReadout();
      designHistoryCommit('tape strip deleted');
    }

    function resetTapes(button) {
      flashButton(button, 'Reset');
      tapes = defaultTapes();
      renderTapeCad();
      refreshTapeEngineering();
      stackLayers = generatedStackLayers();
      renderStackCad();
      drawCad3d();
      updateValidationReadout();
      designHistoryCommit('tape cad reset');
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
      if (!ensureExportReady('Tape JSON export', false)) return;
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
      if (!ensureExportReady('Stack JSON export', false)) return;
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
      return lines.join('\\n');
    }

    function downloadBuildSheet(button) {
      if (!ensureExportReady('Build sheet export', false)) return;
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
        flag_constraints: flagConstraints,
        stack_layers: ensureStackLayers()
      };
    }

    function downloadProject(button) {
      if (!ensureExportReady('Project save', false)) return;
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
          flags = project.flags.map(normalizeFlag);
          flagConstraints = defaultFlagConstraints(flags.length);
          renderFlagEditor();
        }
        if (Array.isArray(project.flag_constraints)) {
          flagConstraints = project.flag_constraints.map(item => ({
            id: String(item.id || ''),
            type: String(item.type || 'custom'),
            scope: String(item.scope || 'all flags'),
            value: numberOr(item.value, 0),
            enabled: Boolean(item.enabled)
          }));
          ensureConstraintCoverage();
          renderConstraintTable();
          drawFlags();
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
      if (/error|failed|exception/i.test(String(message))) {
        debugState.lastError = String(message);
        debugState.errors += 1;
      }
      renderDebugHealth();
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

    function collectValidationIssues(requireLatest) {
      const errors = [];
      const warnings = [];
      if (requireLatest && !latest) {
        errors.push('Run Analyze Shaft before manufacturing export.');
      }
      if (!Array.isArray(flags) || flags.length === 0) {
        errors.push('At least one flag is required.');
      }
      flags.forEach((flag, index) => {
        const name = flag?.name || `Flag ${index + 1}`;
        const length = numberOr(flag?.length, NaN);
        const root = numberOr(flag?.root, NaN);
        const tip = numberOr(flag?.tip, NaN);
        const angle = numberOr(flag?.angle, NaN);
        if (!Number.isFinite(length) || length <= 0) errors.push(`${name}: length must be > 0.`);
        if (!Number.isFinite(root) || root <= 0) errors.push(`${name}: root width must be > 0.`);
        if (!Number.isFinite(tip) || tip <= 0) errors.push(`${name}: tip width must be > 0.`);
        if (Number.isFinite(root) && Number.isFinite(tip) && tip > root * 1.35) {
          warnings.push(`${name}: tip is unusually large versus root.`);
        }
        if (!Number.isFinite(angle) || angle < -89 || angle > 89) {
          errors.push(`${name}: angle must stay between -89 and 89 deg.`);
        }
      });

      tapes.forEach((tape, index) => {
        const name = tape?.name || `Tape ${index + 1}`;
        const startIn = numberOr(tape?.startIn, NaN);
        const length = numberOr(tape?.length, NaN);
        const width = numberOr(tape?.width, NaN);
        const thickness = numberOr(tape?.thickness, NaN);
        if (!Number.isFinite(startIn) || startIn < 11 || startIn > 41) errors.push(`${name}: start station must be 11-41 in.`);
        if (!Number.isFinite(length) || length <= 0) errors.push(`${name}: length must be > 0.`);
        if (!Number.isFinite(width) || width <= 0) errors.push(`${name}: width must be > 0.`);
        if (!Number.isFinite(thickness) || thickness <= 0) errors.push(`${name}: thickness must be > 0.`);
      });

      const hasBiasConstraint = flagConstraints.some(c => c.enabled && c.type === 'bias_pair_angle_abs');
      const hasHorizontalBias = flags.some((flag, index) => {
        const h = flagConstraints.find(c => c.id === `flag_${index}_horizontal` && c.enabled);
        return h && String(flag.layer || '').toLowerCase().includes('bias');
      });
      if (hasBiasConstraint && hasHorizontalBias) {
        warnings.push('Bias angle constraint and horizontal bias constraint are both active.');
      }
      const constraintState = collectConstraintFailures();
      constraintState.errors.forEach(msg => errors.push(`Constraint: ${msg}`));
      constraintState.warnings.forEach(msg => warnings.push(`Constraint: ${msg}`));
      return { errors, warnings };
    }

    function updateValidationReadout() {
      const tbody = document.getElementById('validationReadout');
      if (!tbody) return;
      const state = collectValidationIssues(false);
      const rows = [];
      rows.push(['Errors', String(state.errors.length)]);
      rows.push(['Warnings', String(state.warnings.length)]);
      if (state.errors.length === 0) rows.push(['Status', 'Ready for export']);
      if (state.errors.length > 0) {
        state.errors.slice(0, 4).forEach(message => rows.push(['Error', message]));
      }
      if (state.warnings.length > 0) {
        state.warnings.slice(0, 4).forEach(message => rows.push(['Warning', message]));
      }
      tbody.innerHTML = rows.map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');
    }

    function ensureExportReady(actionName, requireLatest) {
      const state = collectValidationIssues(requireLatest);
      updateValidationReadout();
      if (state.errors.length > 0) {
        setAppStatus(`${actionName} blocked: ${state.errors[0]}`, true);
        writeCadConsole(`${actionName} blocked. ${state.errors.length} validation error(s).`);
        return false;
      }
      if (state.warnings.length > 0) {
        writeCadConsole(`${actionName}: warning(s) present (${state.warnings.length}). Proceeding.`);
      }
      return true;
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

    function cadCanvasPoint(event) {
      const canvas = document.getElementById('cad3dCanvas');
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function setCadDraftTool(tool, button) {
      if (isViewerMode()) return;
      cadDraftTool = tool;
      document.querySelectorAll('#cad3dView #cadDraftSelectBtn, #cad3dView #cadDraftLineBtn, #cad3dView #cadDraftRectBtn, #cad3dView #cadDraftCircleBtn, #cad3dView #cadDraftTriangleBtn')
        .forEach(item => item.classList.remove('active'));
      if (button) button.classList.add('active');
      const status = document.getElementById('cadDraftStatus');
      if (status) status.textContent = `Tool: ${tool}`;
      drawCad3d();
    }

    function cloneCadDraftEntities() {
      return JSON.parse(JSON.stringify(cadDraftEntities));
    }

    function cadDraftHistorySyncButtons() {
      const undo = document.getElementById('cadDraftUndoBtn');
      const redo = document.getElementById('cadDraftRedoBtn');
      if (undo) undo.disabled = cadDraftHistory.length <= 1;
      if (redo) redo.disabled = cadDraftFuture.length === 0;
    }

    function cadDraftCommitState(reason) {
      const snapshot = cloneCadDraftEntities();
      const last = cadDraftHistory[cadDraftHistory.length - 1];
      if (JSON.stringify(snapshot) === JSON.stringify(last)) {
        cadDraftHistorySyncButtons();
        return;
      }
      cadDraftHistory.push(snapshot);
      if (cadDraftHistory.length > 120) cadDraftHistory.shift();
      cadDraftFuture = [];
      cadDraftHistorySyncButtons();
      designHistoryCommit(`cad draft: ${reason || 'edit'}`);
      if (reason) writeCadConsole(`Draft state saved: ${reason}`);
    }

    function undoCadDraft(button) {
      if (cadDraftHistory.length <= 1) return;
      const current = cadDraftHistory.pop();
      cadDraftFuture.push(current);
      cadDraftEntities = JSON.parse(JSON.stringify(cadDraftHistory[cadDraftHistory.length - 1]));
      cadDraftSelectedIndex = null;
      if (button) flashButton(button, 'Undo');
      cadDraftHistorySyncButtons();
      drawCad3d();
    }

    function redoCadDraft(button) {
      if (!cadDraftFuture.length) return;
      const next = cadDraftFuture.pop();
      cadDraftEntities = JSON.parse(JSON.stringify(next));
      cadDraftHistory.push(JSON.parse(JSON.stringify(next)));
      cadDraftSelectedIndex = null;
      if (button) flashButton(button, 'Redo');
      cadDraftHistorySyncButtons();
      drawCad3d();
    }

    function cadDraftDiagnostics() {
      const diagnostics = [];
      if (!cadDraftEntities.length) diagnostics.push({ level: 'info', text: 'No sketch entities yet.' });
      const canvas = document.getElementById('cad3dCanvas');
      const width = canvas?.width || 900;
      const height = canvas?.height || 520;
      cadDraftEntities.forEach((entity, idx) => {
        if (entity.type === 'circle') {
          if (entity.r < 5) diagnostics.push({ level: 'error', text: `E${idx + 1}: circle radius is too small.` });
          if (entity.x - entity.r < 0 || entity.x + entity.r > width || entity.y - entity.r < 0 || entity.y + entity.r > height) {
            diagnostics.push({ level: 'warn', text: `E${idx + 1}: circle is partly outside canvas.` });
          }
          return;
        }
        const w = Math.abs(entity.x2 - entity.x1);
        const h = Math.abs(entity.y2 - entity.y1);
        if (entity.type === 'line' && Math.hypot(w, h) < 8) diagnostics.push({ level: 'error', text: `E${idx + 1}: line too short.` });
        if ((entity.type === 'rect' || entity.type === 'triangle') && (w < 8 || h < 8)) diagnostics.push({ level: 'error', text: `E${idx + 1}: ${entity.type} too small.` });
        const minX = Math.min(entity.x1, entity.x2);
        const maxX = Math.max(entity.x1, entity.x2);
        const minY = Math.min(entity.y1, entity.y2);
        const maxY = Math.max(entity.y1, entity.y2);
        if (minX < 0 || maxX > width || minY < 0 || maxY > height) diagnostics.push({ level: 'warn', text: `E${idx + 1}: ${entity.type} is partly outside canvas.` });
      });
      return diagnostics;
    }

    function renderCadDraftDiagnostics() {
      const tbody = document.getElementById('cadDraftDiagnostics');
      if (!tbody) return;
      const rows = cadDraftDiagnostics();
      tbody.innerHTML = rows.map(row => {
        const label = row.level === 'error' ? 'Error' : row.level === 'warn' ? 'Warning' : 'Info';
        return `<tr><td>${label}</td><td>${row.text}</td></tr>`;
      }).join('');
    }

    function cadEntityHit(entity, p) {
      if (!entity) return false;
      if (entity.type === 'circle') {
        const dx = p.x - entity.x;
        const dy = p.y - entity.y;
        return Math.hypot(dx, dy) <= Math.max(8, entity.r + 6);
      }
      const x1 = Math.min(entity.x1, entity.x2);
      const x2 = Math.max(entity.x1, entity.x2);
      const y1 = Math.min(entity.y1, entity.y2);
      const y2 = Math.max(entity.y1, entity.y2);
      return p.x >= x1 - 8 && p.x <= x2 + 8 && p.y >= y1 - 8 && p.y <= y2 + 8;
    }

    function cad3dMouseDown(event) {
      if (isViewerMode()) return;
      const p = cadCanvasPoint(event);
      if (cadDraftTool === 'select') {
        cadDraftSelectedIndex = null;
        for (let i = cadDraftEntities.length - 1; i >= 0; i--) {
          if (cadEntityHit(cadDraftEntities[i], p)) {
            cadDraftSelectedIndex = i;
            cadDraftDrag = { startX: p.x, startY: p.y };
            cadDraftMoveStartSnapshot = cloneCadDraftEntities();
            break;
          }
        }
        drawCad3d();
        return;
      }
      cadDraftStart = p;
      cadDraftPreview = { type: cadDraftTool, x1: p.x, y1: p.y, x2: p.x, y2: p.y };
      drawCad3d();
    }

    function cad3dMouseMove(event) {
      if (isViewerMode()) return;
      const p = cadCanvasPoint(event);
      if (cadDraftDrag && cadDraftSelectedIndex !== null && cadDraftEntities[cadDraftSelectedIndex]) {
        const entity = cadDraftEntities[cadDraftSelectedIndex];
        const dx = p.x - cadDraftDrag.startX;
        const dy = p.y - cadDraftDrag.startY;
        cadDraftDrag = { startX: p.x, startY: p.y };
        if (entity.type === 'circle') {
          entity.x += dx;
          entity.y += dy;
        } else {
          entity.x1 += dx; entity.x2 += dx;
          entity.y1 += dy; entity.y2 += dy;
        }
        drawCad3d();
        return;
      }
      if (!cadDraftPreview) return;
      cadDraftPreview.x2 = p.x;
      cadDraftPreview.y2 = p.y;
      drawCad3d();
    }

    function cad3dMouseUp() {
      if (cadDraftDrag) {
        cadDraftDrag = null;
        if (cadDraftMoveStartSnapshot) {
          const before = JSON.stringify(cadDraftMoveStartSnapshot);
          const after = JSON.stringify(cadDraftEntities);
          if (before !== after) cadDraftCommitState('move entity');
          cadDraftMoveStartSnapshot = null;
        }
        return;
      }
      if (!cadDraftPreview || !cadDraftStart) return;
      const e = cadDraftPreview;
      if (e.type === 'circle') {
        const r = Math.hypot(e.x2 - e.x1, e.y2 - e.y1);
        if (r > 4) cadDraftEntities.push({ type: 'circle', x: e.x1, y: e.y1, r });
      } else {
        const minSize = Math.abs(e.x2 - e.x1) + Math.abs(e.y2 - e.y1);
        if (minSize > 6) cadDraftEntities.push({ type: e.type, x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2 });
      }
      cadDraftSelectedIndex = cadDraftEntities.length - 1;
      cadDraftPreview = null;
      cadDraftStart = null;
      cadDraftCommitState('create entity');
      drawCad3d();
    }

    function deleteCadDraftSelected(button) {
      if (cadDraftSelectedIndex === null || !cadDraftEntities[cadDraftSelectedIndex]) return;
      cadDraftEntities.splice(cadDraftSelectedIndex, 1);
      cadDraftSelectedIndex = null;
      if (button) flashButton(button, 'Deleted');
      cadDraftCommitState('delete entity');
      drawCad3d();
    }

    function clearCadDraft(button) {
      if (!cadDraftEntities.length) return;
      cadDraftEntities = [];
      cadDraftSelectedIndex = null;
      cadDraftPreview = null;
      cadDraftStart = null;
      if (button) flashButton(button, 'Cleared');
      cadDraftCommitState('clear sketch');
      drawCad3d();
    }

    function drawCadDraftEntity(ctx, entity, selected) {
      ctx.save();
      ctx.strokeStyle = selected ? '#ffbf3f' : '#f2b84b';
      ctx.fillStyle = 'rgba(242,184,75,0.14)';
      ctx.lineWidth = selected ? 2.6 : 1.8;
      if (entity.type === 'line') {
        ctx.beginPath(); ctx.moveTo(entity.x1, entity.y1); ctx.lineTo(entity.x2, entity.y2); ctx.stroke();
      } else if (entity.type === 'rect') {
        const x = Math.min(entity.x1, entity.x2);
        const y = Math.min(entity.y1, entity.y2);
        const w = Math.abs(entity.x2 - entity.x1);
        const h = Math.abs(entity.y2 - entity.y1);
        ctx.fillRect(x, y, w, h);
        ctx.strokeRect(x, y, w, h);
      } else if (entity.type === 'triangle') {
        const x = Math.min(entity.x1, entity.x2);
        const y = Math.min(entity.y1, entity.y2);
        const w = Math.abs(entity.x2 - entity.x1);
        const h = Math.abs(entity.y2 - entity.y1);
        ctx.beginPath();
        ctx.moveTo(x + w / 2, y);
        ctx.lineTo(x + w, y + h);
        ctx.lineTo(x, y + h);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else if (entity.type === 'circle') {
        ctx.beginPath();
        ctx.arc(entity.x, entity.y, entity.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawCadDraftLayer(ctx) {
      cadDraftEntities.forEach((entity, index) => drawCadDraftEntity(ctx, entity, index === cadDraftSelectedIndex));
      if (cadDraftPreview) {
        const preview = cadDraftPreview.type === 'circle'
          ? { type: 'circle', x: cadDraftPreview.x1, y: cadDraftPreview.y1, r: Math.hypot(cadDraftPreview.x2 - cadDraftPreview.x1, cadDraftPreview.y2 - cadDraftPreview.y1) }
          : cadDraftPreview;
        drawCadDraftEntity(ctx, preview, false);
      }
      const status = document.getElementById('cadDraftStatus');
      if (status) {
        status.textContent = cadDraftSelectedIndex === null
          ? `Tool: ${cadDraftTool} | Entities: ${cadDraftEntities.length}`
          : `Tool: ${cadDraftTool} | Selected: #${cadDraftSelectedIndex + 1}`;
      }
      cadDraftHistorySyncButtons();
      renderCadDraftDiagnostics();
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
      drawCadDraftLayer(ctx);

      const script = document.getElementById('cadScript');
      if (script) script.value = shaftCadScript();
      updateArchitecturePanel();
      updateCadInspector();
    }

    function setCadPreset(preset, button) {
      const dark = document.getElementById('cadDarkMode');
      const axis = document.getElementById('cadShowAxis');
      const grid = document.getElementById('cadShowGrid');
      const smooth = document.getElementById('cadSmooth');
      const zoomFit = document.getElementById('cadZoomFit');
      if (!dark || !axis || !grid || !smooth || !zoomFit) return;
      if (preset === 'dark') {
        dark.checked = true;
        axis.checked = true;
        grid.checked = true;
        smooth.checked = true;
        zoomFit.checked = false;
      } else if (preset === 'light') {
        dark.checked = false;
        axis.checked = true;
        grid.checked = true;
        smooth.checked = false;
        zoomFit.checked = false;
      } else if (preset === 'inspect') {
        dark.checked = false;
        axis.checked = true;
        grid.checked = true;
        smooth.checked = true;
        zoomFit.checked = true;
      }
      flashButton(button, 'Applied');
      drawCad3d();
      writeCadConsole(`View preset applied: ${preset}`);
    }

    function syncCadScript(button) {
      const script = document.getElementById('cadScript');
      if (!script) return;
      script.value = shaftCadScript();
      flashButton(button, 'Synced');
      writeCadConsole('CAD script synchronized with current project state.');
    }

    function downloadCadScript(button) {
      if (!ensureExportReady('CAD export', true)) return;
      flashButton(button, 'Exported');
      const exportType = document.getElementById('cadExportType').value;
      let content = shaftCadScript();
      let filename = 'shaft-parametric-model.jscad';
      if (exportType === 'STEP recipe') {
        content = cadQueryStepRecipe();
        filename = 'shaft-step-recipe.py';
      } else if (exportType === 'STL recipe') {
        content = '# STL preview recipe\\n# Lower fidelity visual check export for shaft envelope.\\n\\n' + shaftCadScript();
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
      if (!ensureExportReady('Analysis JSON export', true)) return;
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
      if (!ensureExportReady('Mandrel G-code export', true)) return;
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
      debugState.lastAction = name;
      renderDebugHealth();
      if (isViewerMode() && !VIEWER_ALLOWED_BUTTON_IDS.has(name)) {
        setAppStatus('Viewer mode active: this action is locked.');
        return;
      }
      try {
        const result = callback();
        if (result && typeof result.catch === 'function') {
          result.catch(error => {
            setAppStatus(`${name} failed: ${error.message || String(error)}`, true);
            writeCadConsole(`${name} failed: ${error.message || String(error)}`);
          });
        }
      } catch (error) {
        setAppStatus(`${name} failed: ${error.message || String(error)}`, true);
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

    function buttonRoutes() {
      return {
        simTab: () => showView('simulation'),
        fitTab: () => showView('fit'),
        drawTab: () => showView('drawing'),
        flagTab: () => showView('flags'),
        tapeTab: () => showView('tape'),
        stackTab: () => showView('stack'),
        cad3dTab: () => showView('cad3d'),
        analyzeBtn: button => run(button),
        historyUndoBtn: button => undoDesignHistory(button),
        historyRedoBtn: button => redoDesignHistory(button),
        debugAuditBtn: button => runButtonAudit(button),
        exportJsonBtn: button => downloadJson(button),
        exportGcodeBtn: button => downloadGcode(button),
        fitGenerateBtn: button => runFitToBuild(button),
        fitApplyBtn: button => applyFitToCad(button),
        fitExportBtn: button => downloadFitProfile(button),
        fitSyncPacketBtn: button => downloadFitCadPacket(button),
        fitPullCadBtn: button => pullCadIntoFit(button),
        drawAddStationBtn: button => addDrawingStation(button),
        drawDeleteStationBtn: button => deleteSelectedDrawingStation(button),
        drawResetProfileBtn: button => resetDrawingProfile(button),
        drawToolSelectBtn: button => setDrawingTool('select', button),
        drawToolMoveBtn: button => setDrawingTool('move', button),
        drawToolAddBtn: button => setDrawingTool('add', button),
        drawToolDimBtn: button => setDrawingTool('dimension', button),
        drawToolDeleteBtn: button => setDrawingTool('delete', button),
        sketchMenuFileBtn: button => handleSketchMenu('file', button),
        sketchMenuEditBtn: button => handleSketchMenu('edit', button),
        sketchMenuViewBtn: button => handleSketchMenu('view', button),
        sketchMenuNewGroupBtn: button => handleSketchMenu('new-group', button),
        sketchMenuSketchBtn: button => handleSketchMenu('sketch', button),
        sketchMenuConstrainBtn: button => handleSketchMenu('constrain', button),
        sketchMenuAnalyzeBtn: button => handleSketchMenu('analyze', button),
        sketchMenuHelpBtn: button => handleSketchMenu('help', button),
        flagAddBtn: button => addFlag(button),
        flagTriangleBtn: button => addTriangleFlag(button),
        flagResetBtn: button => resetFlags(button),
        flagJsonBtn: button => downloadFlagJson(button),
        flagSvgBtn: button => downloadFlagSvg(button),
        flagDxfBtn: button => downloadFlagDxf(button),
        constraintSelHorizontalBtn: button => applySelectedConstraint('horizontal', button),
        constraintSelVerticalBtn: button => applySelectedConstraint('vertical', button),
        constraintSelLengthBtn: button => applySelectedConstraint('length', button),
        constraintSelAngleBtn: button => applySelectedConstraint('angle', button),
        flagPrevBtn: button => selectAdjacentFlag(-1, button),
        flagNextBtn: button => selectAdjacentFlag(1, button),
        flagDuplicateBtn: button => duplicateSelectedFlag(button),
        flagDeleteSelectedBtn: button => deleteSelectedFlag(button),
        flagMirrorAngleBtn: button => mirrorSelectedFlagAngle(button),
        dimApplySelectedBtn: button => applyDimensionPreset('selected', button),
        dimApplyAllBtn: button => applyDimensionPreset('all', button),
        dimProgressiveBtn: button => applyDimensionPreset('progressive', button),
        constraintApplyBtn: button => applyFlagConstraints(button),
        constraintResetBtn: button => resetFlagConstraints(button),
        projectSaveBtn: button => downloadProject(button),
        projectLoadBtn: () => document.getElementById('projectFile')?.click(),
        tapeAddBtn: button => addTape(button),
        tapeBiasBtn: button => addBiasTapePair(button),
        tapeResetBtn: button => resetTapes(button),
        tapeJsonBtn: button => downloadTapeJson(button),
        stackGenerateBtn: button => regenerateStack(button),
        stackJsonBtn: button => downloadStackJson(button),
        stackSheetBtn: button => downloadBuildSheet(button),
        cadExportBtn: button => downloadCadScript(button),
        cadRefreshBtn: () => drawCad3d(),
        cadPresetDarkBtn: button => setCadPreset('dark', button),
        cadPresetLightBtn: button => setCadPreset('light', button),
        cadPresetInspectBtn: button => setCadPreset('inspect', button),
        cadSyncScriptBtn: button => syncCadScript(button),
        fpSmokeBtn: button => runSmokeTest(button),
        cadDraftSelectBtn: button => setCadDraftTool('select', button),
        cadDraftLineBtn: button => setCadDraftTool('line', button),
        cadDraftRectBtn: button => setCadDraftTool('rect', button),
        cadDraftCircleBtn: button => setCadDraftTool('circle', button),
        cadDraftTriangleBtn: button => setCadDraftTool('triangle', button),
        cadDraftUndoBtn: button => undoCadDraft(button),
        cadDraftRedoBtn: button => redoCadDraft(button),
        cadDraftDeleteBtn: button => deleteCadDraftSelected(button),
        cadDraftClearBtn: button => clearCadDraft(button)
      };
    }

    function emergencyClickRouter(event) {
      const button = event.target?.closest?.('button');
      if (!button || !button.id) return;
      const route = buttonRoutes()[button.id];
      if (!route) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      safeInvoke(button.id, () => route(button));
    }

    function setStrictMode(enabled) {
      debugState.strictMode = Boolean(enabled);
      const toggle = document.getElementById('strictModeToggle');
      if (toggle) toggle.checked = debugState.strictMode;
      renderDebugHealth();
      runButtonAudit();
    }

    function enforceStrictButtons(missingRoute) {
      if (!debugState.strictMode) {
        return;
      }
      missingRoute.forEach(button => {
        button.disabled = true;
        button.classList.add('viewer-locked');
        button.title = 'Disabled by strict mode: no button route.';
      });
    }

    function runButtonAudit(button) {
      const routes = buttonRoutes();
      const buttons = Array.from(document.querySelectorAll('button'));
      const missingId = buttons.filter(item => !item.id);
      const withId = buttons.filter(item => item.id);
      const missingRoute = withId.filter(item => !routes[item.id]);
      const deadRoute = Object.keys(routes).filter(id => !document.getElementById(id));
      const inlineOnly = buttons.filter(item => item.getAttribute('onclick') && !item.id);
      enforceStrictButtons(missingRoute);

      debugState.buttonAudit = `ok:${withId.length - missingRoute.length}/${withId.length}, no-id:${missingId.length}, route-miss:${missingRoute.length}, dead-route:${deadRoute.length}`;
      renderDebugHealth();

      const problems = [];
      if (missingId.length) problems.push(`Missing id: ${missingId.length}`);
      if (missingRoute.length) problems.push(`No route for id: ${missingRoute.map(b => b.id).join(', ')}`);
      if (deadRoute.length) problems.push(`Route target missing in DOM: ${deadRoute.join(', ')}`);
      if (inlineOnly.length) problems.push(`Inline-only buttons (advisory): ${inlineOnly.length}`);

      if (problems.length) {
        setAppStatus(`Button audit found issues (${problems.length}).`, true);
        writeCadConsole(`Button audit issues -> ${problems.join(' | ')}`);
      } else {
        setAppStatus('Button audit passed: all routed controls are wired.');
        writeCadConsole('Button audit passed: no missing route targets.');
      }

      if (button) flashButton(button, 'Audited');
    }

    function bootstrapButtons() {
      const routes = buttonRoutes();
      Object.keys(routes).forEach(id => bindClickById(id, button => routes[id](button)));
      if (typeof document.removeEventListener === 'function') {
        document.removeEventListener('click', emergencyClickRouter, true);
      }
      if (typeof document.addEventListener === 'function') {
        document.addEventListener('click', emergencyClickRouter, true);
      }
      setAppStatus('AE boot OK: JavaScript loaded, buttons bound, emergency click router active.');
      writeCadConsole('Button safety bootstrap active: id bindings loaded. Emergency click router active.');
      const strictToggle = document.getElementById('strictModeToggle');
      if (strictToggle) strictToggle.checked = debugState.strictMode;
      runButtonAudit();
    }

    window.showView = showView;
    window.setSketchTool = setSketchTool;
    window.handleSketchMenu = handleSketchMenu;
    window.run = run;
    window.runFitToBuild = runFitToBuild;
    window.applyFitToCad = applyFitToCad;
    window.downloadFitProfile = downloadFitProfile;
    window.downloadFitCadPacket = downloadFitCadPacket;
    window.pullCadIntoFit = pullCadIntoFit;
    window.updateDrawingStation = updateDrawingStation;
    window.addDrawingStation = addDrawingStation;
    window.deleteSelectedDrawingStation = deleteSelectedDrawingStation;
    window.resetDrawingProfile = resetDrawingProfile;
    window.setDrawingTool = setDrawingTool;
    window.drawingMouseDown = drawingMouseDown;
    window.drawingMouseMove = drawingMouseMove;
    window.drawingMouseUp = drawingMouseUp;
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
    window.renderConstraintTable = renderConstraintTable;
    window.updateConstraint = updateConstraint;
    window.applySelectedConstraint = applySelectedConstraint;
    window.selectAdjacentFlag = selectAdjacentFlag;
    window.duplicateSelectedFlag = duplicateSelectedFlag;
    window.deleteSelectedFlag = deleteSelectedFlag;
    window.mirrorSelectedFlagAngle = mirrorSelectedFlagAngle;
    window.applyDimensionPreset = applyDimensionPreset;
    window.applyFlagConstraints = applyFlagConstraints;
    window.resetFlagConstraints = resetFlagConstraints;
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
    window.setCadDraftTool = setCadDraftTool;
    window.runSmokeTest = runSmokeTest;
    window.cad3dMouseDown = cad3dMouseDown;
    window.cad3dMouseMove = cad3dMouseMove;
    window.cad3dMouseUp = cad3dMouseUp;
    window.undoCadDraft = undoCadDraft;
    window.redoCadDraft = redoCadDraft;
    window.deleteCadDraftSelected = deleteCadDraftSelected;
    window.clearCadDraft = clearCadDraft;
    window.setCadPreset = setCadPreset;
    window.syncCadScript = syncCadScript;
    window.downloadCadScript = downloadCadScript;
    window.downloadJson = downloadJson;
    window.downloadGcode = downloadGcode;
    window.undoDesignHistory = undoDesignHistory;
    window.redoDesignHistory = redoDesignHistory;
    window.setStrictMode = setStrictMode;
    window.runButtonAudit = runButtonAudit;
    window.bootstrapButtons = bootstrapButtons;

    function bootApp() {
      setAppStatus('AE boot starting: wiring controls and running first analysis...');
      loadBuildFingerprint();
      renderDebugHealth();
      renderDesignHistory();
      applyViewerMode();
      bootstrapButtons();
      ['target', 'head', 'speed', 'angle', 'material', 'method', 'architectureMode'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', () => designHistoryCommit(`input changed: ${id}`));
      });
      run().then(() => {
        if (designHistory.length === 0) designHistoryCommit('initial state');
        if (!isViewerMode()) {
          setAppStatus('AE boot OK: controls are live. If a button fails now, the status bar will show the exact error.');
        }
      }).catch(error => {
        setAppStatus(`Startup analysis failed: ${error.message || String(error)}`, true);
        writeCadConsole(error.message || String(error));
      });
    }

    if (document.readyState === 'loading' && typeof document.addEventListener === 'function') {
      document.addEventListener('DOMContentLoaded', bootApp);
    } else {
      bootApp();
    }
  </script>
</body>
</html>
"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/build")
def api_build() -> dict[str, str]:
    return {
        "version": APP_VERSION,
        "commit": APP_BUILD_COMMIT,
        "build_time": APP_BUILD_TIME,
    }


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


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
    cpm_clamp_length_in: float = 5.0,
    cpm_overall_weight_g: float = 205.0,
    cpm_profile_weight_g: float = 255.0,
    cpm_overall_k: float = 14.7,
    cpm_zone_k: float = 8.5,
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
        cpm_clamp_length_in=cpm_clamp_length_in,
        cpm_overall_weight_g=cpm_overall_weight_g,
        cpm_profile_weight_g=cpm_profile_weight_g,
        cpm_overall_k=cpm_overall_k,
        cpm_zone_k=cpm_zone_k,
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


@app.get("/api/fit/target")
def api_fit_target(
    speed_mph: float = 105.0,
    launch_deg: float = 13.5,
    spin_rpm: float = 2650.0,
    weight_g: float = 65.0,
    tempo: str = "Medium",
    transition: str = "Medium",
    release: str = "Mid",
    miss: str = "Neutral",
    feel: str = "Stable mid",
) -> dict[str, Any]:
    return fit_target_from_swing(
        speed_mph=speed_mph,
        launch_deg=launch_deg,
        spin_rpm=spin_rpm,
        weight_g=weight_g,
        tempo=tempo,
        transition=transition,
        release=release,
        miss=miss,
        feel=feel,
    )


@app.get("/api/fit-cad/bridge")
def api_fit_cad_bridge(
    speed_mph: float = 105.0,
    launch_deg: float = 13.5,
    spin_rpm: float = 2650.0,
    weight_g: float = 65.0,
    tempo: str = "Medium",
    transition: str = "Medium",
    release: str = "Mid",
    miss: str = "Neutral",
    feel: str = "Stable mid",
    architecture_mode: str = "flag_wrap",
) -> dict[str, Any]:
    fit_target = fit_target_from_swing(
        speed_mph=speed_mph,
        launch_deg=launch_deg,
        spin_rpm=spin_rpm,
        weight_g=weight_g,
        tempo=tempo,
        transition=transition,
        release=release,
        miss=miss,
        feel=feel,
    )
    return {
        "version": "ae-fitcad-1",
        "fitting_target": fit_target,
        "cad_transfer": {
            "target_cpm": fit_target["target_cpm"],
            "wrap_angle_deg": fit_target["wrap_angle_deg"],
            "architecture_mode": architecture_mode,
        },
    }
