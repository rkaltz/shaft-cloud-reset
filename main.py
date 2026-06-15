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

INCH_TO_M = 0.0254
RAW_DRIVER_LENGTH_RANGE_IN = (46.0, 47.0)
STANDARD_PLAYING_LENGTH_RANGE_IN = (45.0, 45.75)
STANDARD_DRIVER_TIP_OD_IN = 0.335
STANDARD_DRIVER_BUTT_OD_RANGE_IN = (0.590, 0.600)
STANDARD_DRIVER_WEIGHT_RANGE_G = (45.0, 85.0)


@dataclass
class Material:
    name: str
    e1_pa: float
    e2_pa: float
    g12_pa: float
    nu12: float
    density_kg_m3: float
    cost_per_kg: float
    family: str = "Carbon fiber"
    design_role: str = "General shaft laminate"
    data_quality: str = "Engineering estimate"


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
    "Mitsubishi MR70": Material("Mitsubishi MR70", 161e9, 8.7e9, 4.5e9, 0.32, 1600.0, 95.0, "Carbon fiber", "Smooth load, balanced strength/stiffness shaft body"),
    "Toray T1100G": Material("Toray T1100G", 215e9, 8.5e9, 4.2e9, 0.33, 1580.0, 125.0, "Carbon fiber", "High strength, stable premium driver shaft body"),
    "Hexcel IM7": Material("Hexcel IM7", 276e9, 14.0e9, 5.2e9, 0.31, 1620.0, 140.0, "Carbon fiber", "Firm mid/butt reinforcement and stout feel tuning"),
    "Toray T700S": Material("Toray T700S", 230e9, 15.0e9, 5.0e9, 0.30, 1600.0, 55.0, "Carbon fiber", "Lower-cost standard/intermediate modulus baseline"),
    "Toray T800H": Material("Toray T800H", 294e9, 13.0e9, 5.0e9, 0.31, 1590.0, 85.0, "Carbon fiber", "Lightweight premium mid/high modulus shaft body"),
    "Toray M40J": Material("Toray M40J", 377e9, 9.0e9, 4.4e9, 0.32, 1600.0, 185.0, "High modulus carbon", "Butt/mid stiffness without large mass increase"),
    "Toray M46J": Material("Toray M46J", 436e9, 8.0e9, 4.0e9, 0.32, 1600.0, 240.0, "Ultra high modulus carbon", "Very stiff local reinforcement; use carefully in tip"),
    "Mitsubishi Dialead K13C": Material("Mitsubishi Dialead K13C", 640e9, 7.0e9, 3.7e9, 0.32, 1700.0, 420.0, "Pitch-based high modulus carbon", "Specialty ultra-stiff strips, low-strain zone tuning"),
    "S-Glass Damping Layer": Material("S-Glass Damping Layer", 86e9, 86e9, 35.0e9, 0.22, 2000.0, 22.0, "Glass fiber", "Damping, toughness, hoop support, smoother feel"),
    "E-Glass Hoop Layer": Material("E-Glass Hoop Layer", 73e9, 73e9, 30.0e9, 0.22, 1950.0, 14.0, "Glass fiber", "Budget hoop stability and impact tolerance"),
    "Kevlar 49 Aramid": Material("Kevlar 49 Aramid", 130e9, 5.5e9, 2.8e9, 0.34, 1440.0, 65.0, "Aramid fiber", "Vibration damping and impact-tough bias/veil layer"),
    "Basalt Fiber": Material("Basalt Fiber", 89e9, 89e9, 32.0e9, 0.24, 2000.0, 18.0, "Basalt fiber", "Durable damping layer between glass and carbon behavior"),
    "Boron Fiber Prepreg": Material("Boron Fiber Prepreg", 400e9, 30.0e9, 14.0e9, 0.23, 2550.0, 520.0, "Boron fiber", "Heavy, expensive, very stable local reinforcement"),
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
AUDITOR_CPM_MIN = 0.0
AUDITOR_CPM_MAX = 999.0
CPM_SECTION_RANGES = {
    "Butt": {
        "stations_in": [41, 36],
        "soft": (140.0, 155.0),
        "medium": (155.0, 175.0),
        "stiff": (175.0, 190.0),
        "full_flex_delta_cpm": 10.0,
    },
    "Mid": {
        "stations_in": [31, 26, 21],
        "soft": (220.0, 250.0),
        "medium": (250.0, 290.0),
        "stiff": (290.0, 320.0),
        "full_flex_delta_cpm": 25.0,
    },
    "Tip": {
        "stations_in": [16, 11],
        "soft": (680.0, 740.0),
        "medium": (740.0, 820.0),
        "stiff": (820.0, 880.0),
        "full_flex_delta_cpm": 40.0,
    },
}


@dataclass
class CpmCalibration:
    clamp_length_in: float = 5.0
    overall_weight_g: float = 205.0
    profile_weight_g: float = 255.0
    overall_k: float = 14.7
    zone_k: float = 8.5


DEFAULT_CPM_CAL = CpmCalibration()


def auditor_cpm_reading(value: float) -> float:
    return max(AUDITOR_CPM_MIN, min(AUDITOR_CPM_MAX, float(value)))


def cpm_section_for_station(station_in: float) -> str:
    station = int(round(station_in))
    for section, reference in CPM_SECTION_RANGES.items():
        if station in reference["stations_in"]:
            return section
    return "Unknown"


def cpm_range_label(section: str, cpm: float) -> str:
    reference = CPM_SECTION_RANGES.get(section)
    if not reference:
        return "unknown"
    for label in ("soft", "medium", "stiff"):
        low, high = reference[label]
        if low <= cpm <= high:
            return label
    if cpm < reference["soft"][0]:
        return "below soft"
    return "above stiff"


def cpm_section_reference(section: str) -> dict[str, Any]:
    reference = CPM_SECTION_RANGES[section]
    return {
        "section": section,
        "stations_in": reference["stations_in"],
        "soft_range_cpm": reference["soft"],
        "medium_range_cpm": reference["medium"],
        "stiff_range_cpm": reference["stiff"],
        "full_flex_delta_cpm": reference["full_flex_delta_cpm"],
    }


def default_segments(base_angle: float = 45.0, thickness_m: float = 0.000125) -> list[Segment]:
    layup = [
        Ply(0.0, thickness_m),
        Ply(base_angle, thickness_m),
        Ply(-base_angle, thickness_m),
        Ply(0.0, thickness_m),
    ]
    return [
        Segment("Butt", 0.2921, 0.600 * INCH_TO_M, 0.520 * INCH_TO_M, layup.copy()),
        Segment("Upper mid", 0.2921, 0.540 * INCH_TO_M, 0.460 * INCH_TO_M, layup.copy()),
        Segment("Lower mid", 0.2921, 0.430 * INCH_TO_M, 0.350 * INCH_TO_M, layup.copy()),
        Segment("Tip", 0.2921, STANDARD_DRIVER_TIP_OD_IN * INCH_TO_M, 0.255 * INCH_TO_M, layup.copy()),
    ]


def area_moment_i(od: float, id_: float) -> float:
    return (pi / 64.0) * (od**4 - id_**4)


def polar_moment_j(od: float, id_: float) -> float:
    return (pi / 32.0) * (od**4 - id_**4)


def transformed_modulus(material: Material, angle_deg: float) -> float:
    angle = radians(angle_deg)
    c = cos(angle)
    s = sin(angle)
    nu21 = material.nu12 * material.e2_pa / material.e1_pa
    denom = max(1e-9, 1.0 - material.nu12 * nu21)
    q11 = material.e1_pa / denom
    q22 = material.e2_pa / denom
    q12 = material.nu12 * material.e2_pa / denom
    q66 = material.g12_pa
    return q11 * c**4 + 2.0 * (q12 + 2.0 * q66) * s**2 * c**2 + q22 * s**4


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


def driver_shaft_spec_check(segments: list[Segment], mass_g: float) -> dict[str, Any]:
    raw_length_in = total_length(segments) / INCH_TO_M
    butt_od_in = segments[0].outer_diameter_m / INCH_TO_M
    tip_od_in = segments[-1].outer_diameter_m / INCH_TO_M
    flags: list[str] = []
    if not (RAW_DRIVER_LENGTH_RANGE_IN[0] <= raw_length_in <= RAW_DRIVER_LENGTH_RANGE_IN[1]):
        flags.append("Raw driver shaft length should normally be 46-47 inches before trimming.")
    if abs(tip_od_in - STANDARD_DRIVER_TIP_OD_IN) > 0.003:
        flags.append("Driver/wood graphite tip OD should normally target 0.335 inch.")
    if not (STANDARD_DRIVER_BUTT_OD_RANGE_IN[0] <= butt_od_in <= STANDARD_DRIVER_BUTT_OD_RANGE_IN[1]):
        flags.append("Men's driver butt OD should normally sit around 0.590-0.600 inch.")
    if not (STANDARD_DRIVER_WEIGHT_RANGE_G[0] <= mass_g <= STANDARD_DRIVER_WEIGHT_RANGE_G[1]):
        flags.append("Modeled shaft mass is outside the common 45-85g driver shaft range.")
    return {
        "category": "composite_driver_shaft",
        "raw_length_in": round(raw_length_in, 3),
        "common_raw_length_in": {"min": RAW_DRIVER_LENGTH_RANGE_IN[0], "max": RAW_DRIVER_LENGTH_RANGE_IN[1]},
        "common_playing_length_in": {
            "min": STANDARD_PLAYING_LENGTH_RANGE_IN[0],
            "max": STANDARD_PLAYING_LENGTH_RANGE_IN[1],
            "note": "Playing length depends on head, adapter, trimming, and grip build.",
        },
        "tip_od_in": round(tip_od_in, 4),
        "standard_tip_od_in": STANDARD_DRIVER_TIP_OD_IN,
        "butt_od_in": round(butt_od_in, 4),
        "standard_butt_od_in": {
            "min": STANDARD_DRIVER_BUTT_OD_RANGE_IN[0],
            "max": STANDARD_DRIVER_BUTT_OD_RANGE_IN[1],
        },
        "mass_g": round(mass_g, 2),
        "common_weight_range_g": {
            "min": STANDARD_DRIVER_WEIGHT_RANGE_G[0],
            "max": STANDARD_DRIVER_WEIGHT_RANGE_G[1],
        },
        "fit_for_driver_baseline": not flags,
        "flags": flags,
    }


def cpm_effective_length_m(total_length_m: float, clamp_length_in: float) -> float:
    return max(0.08, total_length_m - clamp_length_in * 0.0254)


def overall_cpm(segments: list[Segment], material: Material, calibration: CpmCalibration) -> float:
    length = total_length(segments)
    effective_length = cpm_effective_length_m(length, calibration.clamp_length_in)
    ei = average_ei(segments, material)
    return calibration.overall_k * sqrt(ei / ((calibration.overall_weight_g / 1000.0) * effective_length**3))


def zone_profile(segments: list[Segment], material: Material, calibration: CpmCalibration) -> list[dict[str, Any]]:
    ei = average_ei(segments, material)
    clamp = calibration.clamp_length_in
    rows = []
    for station in ZONE_STATIONS_IN:
        effective_span = max(1.0, station - clamp)
        formula_cpm = calibration.zone_k * sqrt(
            ei / ((calibration.profile_weight_g / 1000.0) * (effective_span * 0.0254) ** 3)
        )
        cpm = auditor_cpm_reading(formula_cpm)
        section = cpm_section_for_station(station)
        section_reference = CPM_SECTION_RANGES[section]
        cpm_class = cpm_range_label(section, cpm)
        rows.append(
            {
                "station_in": float(station),
                "section": section,
                "effective_span_in": effective_span,
                "cpm": cpm,
                "raw_model_cpm": formula_cpm,
                "cpm_class": cpm_class,
                "soft_range_cpm": section_reference["soft"],
                "medium_range_cpm": section_reference["medium"],
                "stiff_range_cpm": section_reference["stiff"],
                "full_flex_delta_cpm": section_reference["full_flex_delta_cpm"],
                "analyzer_limited": formula_cpm > AUDITOR_CPM_MAX or formula_cpm < AUDITOR_CPM_MIN,
                "analyzer_range": f"{AUDITOR_CPM_MIN:.0f}-{AUDITOR_CPM_MAX:.0f}",
            }
        )
    return rows


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


def clamp_value(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def avg(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def behavior_label_from_butt_cpm(cpm: float) -> str:
    if cpm < 245:
        return "smooth / active overall behavior"
    if cpm < 265:
        return "balanced overall behavior"
    if cpm < 285:
        return "stable / firm overall behavior"
    return "very stable / tour-stout overall behavior"


def zone_cpm_values(overall: float, zones: list[dict[str, float]]) -> list[float]:
    return [auditor_cpm_reading(overall)] + [auditor_cpm_reading(float(row["cpm"])) for row in zones]


def analyze_behavior_fingerprint(cpm_values: list[float], torque_deg: float) -> dict[str, Any]:
    butt = cpm_values[0]
    handle = avg(cpm_values[0:3])
    mid = avg(cpm_values[3:6])
    tip = avg(cpm_values[6:8])
    gradient = tip - butt
    kickpoint_percent = clamp_value(52.9 - gradient * 0.015, 45.0, 52.9)
    kickpoint_label = "low kickpoint" if kickpoint_percent < 48.0 else "high kickpoint" if kickpoint_percent > 51.0 else "mid kickpoint"
    return {
        "measurement_order": ["Butt", "41", "36", "31", "26", "21", "16", "11"],
        "overall_behavior_cpm": butt,
        "handle_behavior_cpm": handle,
        "mid_behavior_cpm": mid,
        "tip_behavior_cpm": tip,
        "profile_gradient": gradient,
        "kickpoint_percent": kickpoint_percent,
        "kickpoint_label": kickpoint_label,
        "overall_behavior": behavior_label_from_butt_cpm(butt),
        "handle_behavior": "high handle stability" if handle >= 300 else "controlled handle stability" if handle >= 270 else "smooth handle response",
        "mid_behavior": "low droop / strong load control" if mid >= 425 else "balanced load timing" if mid >= 380 else "active mid loading",
        "tip_behavior": "low launch / low spin tip control" if tip >= 540 else "mid launch / controlled spin tip" if tip >= 470 else "higher launch / active tip response",
        "torque_behavior": "high torsional control" if torque_deg <= 2.8 else "balanced torsional response" if torque_deg <= 3.5 else "active torsional feel",
        "selection_rule": "Do not select by retail flex labels. Use measured CPM shape, torque, dynamic bend, and launch behavior.",
    }


def swing_load_factor(speed_mph: float, transition: str = "Medium", tempo: str = "Medium", release: str = "Mid") -> float:
    transition_factor = {"Smooth": 0.9, "Medium": 1.0, "Hard": 1.25, "Aggressive": 1.25}.get(transition, 1.0)
    tempo_factor = {"Smooth": 0.94, "Medium": 1.0, "Aggressive": 1.12, "Fast": 1.12}.get(tempo, 1.0)
    release_factor = {"Early": 0.85, "Mid": 1.0, "Late": 1.25}.get(release, 1.0)
    return (speed_mph / 100.0) * transition_factor * tempo_factor * release_factor


def dynamic_bend_model(cpm_values: list[float], speed_mph: float, transition: str = "Medium", tempo: str = "Medium", release: str = "Mid") -> dict[str, Any]:
    load = swing_load_factor(speed_mph, transition, tempo, release) * 100.0
    handle = avg(cpm_values[0:3])
    mid = avg(cpm_values[3:6])
    tip = avg(cpm_values[6:8])
    bend_profile = [
        (load / max(cpm_values[0], 1.0)) * 0.35,
        (load / max(handle, 1.0)) * 0.55,
        (load / max(handle, 1.0)) * 0.75,
        load / max(mid, 1.0),
        (load / max(mid, 1.0)) * 1.15,
        (load / max(mid, 1.0)) * 1.25,
        (load / max(tip, 1.0)) * 1.35,
        (load / max(tip, 1.0)) * 1.5,
    ]
    max_index = bend_profile.index(max(bend_profile))
    station = ["Butt", "41", "36", "31", "26", "21", "16", "11"][max_index]
    return {
        "bend_profile": [round(value, 3) for value in bend_profile],
        "max_deflection_index": max_index,
        "max_bend_station": station,
        "max_deflection_proxy": round(max(bend_profile), 3),
        "load_style": "mid-load bend" if (load / max(mid, 1.0)) > (load / max(handle, 1.0)) * 1.25 else "handle-stable bend",
        "release_behavior": "active release" if (load / max(tip, 1.0)) > 0.22 else "controlled release",
    }


def impact_deflection_model(cpm_values: list[float], speed_mph: float, transition: str = "Medium", tempo: str = "Medium", release: str = "Mid") -> dict[str, Any]:
    shaft_load = swing_load_factor(speed_mph, transition, tempo, release)
    butt = cpm_values[0]
    mid = avg(cpm_values[3:6])
    tip = avg(cpm_values[6:8])
    forward = shaft_load * (520.0 / max(tip, 1.0)) * 0.95
    droop = shaft_load * (400.0 / max(mid, 1.0)) * 0.55
    twist = shaft_load * (275.0 / max(butt, 1.0)) * 0.35
    return {
        "forward_deflection_in": round(forward, 2),
        "droop_deflection_in": round(droop, 2),
        "twist_deflection_deg": round(twist, 2),
        "impact_behavior": "high kick / active tip at impact" if forward > 1.2 else "stable tip / low dynamic loft" if forward < 0.65 else "higher toe droop / timing sensitive" if droop > 0.75 else "controlled impact delivery",
    }


def ball_flight_prediction(speed_mph: float, impact: dict[str, Any]) -> dict[str, Any]:
    ball_speed = speed_mph * 1.47
    dynamic_loft = 10.5 + impact["forward_deflection_in"] * 4.2
    launch_angle = dynamic_loft * 0.82 + speed_mph * 0.015
    spin_rate = 1800.0 + dynamic_loft * 145.0 + impact["droop_deflection_in"] * 350.0 - speed_mph * 3.0
    carry = ball_speed * 2.35 + launch_angle * 3.8 - spin_rate * 0.006
    return {
        "ball_speed_mph": round(ball_speed, 1),
        "dynamic_loft_deg": round(dynamic_loft, 1),
        "launch_angle_deg": round(launch_angle, 1),
        "spin_rate_rpm": round(spin_rate),
        "carry_yards": round(carry),
        "flight_window": "low penetrating" if launch_angle < 10 and spin_rate < 2200 else "high spinny" if launch_angle > 15 and spin_rate > 3000 else "optimized driver window" if 11 <= launch_angle <= 14.5 and 2200 <= spin_rate <= 2800 else "playable neutral",
    }


def speed_gain_prediction(cpm_values: list[float], speed_mph: float, transition: str = "Medium", release: str = "Mid") -> dict[str, Any]:
    mid = avg(cpm_values[3:6])
    tip = avg(cpm_values[6:8])
    ideal_mid = 430.0 if transition in {"Hard", "Aggressive"} else 370.0 if transition == "Smooth" else 400.0
    ideal_tip = 540.0 if release == "Late" else 460.0 if release == "Early" else 500.0
    mid_match = clamp_value(1.0 - abs(mid - ideal_mid) / ideal_mid, 0.0, 1.0)
    tip_match = clamp_value(1.0 - abs(tip - ideal_tip) / ideal_tip, 0.0, 1.0)
    efficiency = clamp_value(mid_match * 0.45 + tip_match * 0.55, 0.0, 1.0)
    max_gain = 3.2 if transition in {"Hard", "Aggressive"} else 2.0
    gain = max_gain * efficiency
    return {
        "base_speed_mph": speed_mph,
        "gain_mph": round(gain, 2),
        "final_speed_mph": round(speed_mph + gain, 2),
        "carry_gain_yards": round(gain * 2.7),
        "timing_efficiency_pct": round(efficiency * 100),
    }


def locked_butt_optimizer(cpm_values: list[float], speed_mph: float, transition: str = "Medium", release: str = "Mid") -> dict[str, Any]:
    best = None
    for mid_delta in range(-60, 81, 10):
        for tip_delta in range(-80, 101, 10):
            candidate = cpm_values.copy()
            candidate[0] = cpm_values[0]
            for index in [3, 4, 5]:
                candidate[index] = auditor_cpm_reading(candidate[index] + mid_delta)
            for index in [6, 7]:
                candidate[index] = auditor_cpm_reading(candidate[index] + tip_delta)
            speed_gain = speed_gain_prediction(candidate, speed_mph, transition, release)
            smoothness_penalty = sum(abs(candidate[i] - candidate[i - 1]) for i in range(1, len(candidate))) / 1000.0
            score = speed_gain["gain_mph"] - smoothness_penalty
            if best is None or score > best["score"]:
                best = {
                    "score": round(score, 3),
                    "mid_delta_cpm": mid_delta,
                    "tip_delta_cpm": tip_delta,
                    "profile": [round(value, 1) for value in candidate],
                    "speed_gain": speed_gain,
                }
    return {
        "locked_butt_cpm": round(cpm_values[0], 1),
        "best": best,
        "rule": "Butt CPM remains locked; only mid, tip, and torque behavior should move around it.",
    }


def behavior_intelligence(
    overall: float,
    zones: list[dict[str, float]],
    torque_deg: float,
    speed_mph: float,
    transition: str = "Medium",
    tempo: str = "Medium",
    release: str = "Mid",
) -> dict[str, Any]:
    cpm_values = zone_cpm_values(overall, zones)
    fingerprint = analyze_behavior_fingerprint(cpm_values, torque_deg)
    dynamic = dynamic_bend_model(cpm_values, speed_mph, transition, tempo, release)
    impact = impact_deflection_model(cpm_values, speed_mph, transition, tempo, release)
    flight = ball_flight_prediction(speed_mph, impact)
    speed_gain = speed_gain_prediction(cpm_values, speed_mph, transition, release)
    optimizer = locked_butt_optimizer(cpm_values, speed_mph, transition, release)
    return {
        "engine": "AE behavior intelligence",
        "cpm_values": [round(value, 1) for value in cpm_values],
        "cpm_section_ranges": [cpm_section_reference(section) for section in ("Butt", "Mid", "Tip")],
        "cpm_range_rule": "A full flex CPM delta changes by section: butt about 10 CPM, mid about 25 CPM, tip 40 CPM or more.",
        "fingerprint": fingerprint,
        "dynamic_bend": dynamic,
        "impact_deflection": impact,
        "ball_flight_prediction": flight,
        "speed_gain_prediction": speed_gain,
        "locked_butt_optimizer": optimizer,
    }


def fit_build_brief(
    target_cpm: float,
    torque_target: float,
    wrap_angle: float,
    launch_bias: str,
    tip_strategy: str,
    speed_mph: float,
    tempo: str,
    transition: str,
    release: str,
    miss: str,
    feel: str,
) -> dict[str, Any]:
    torque_window = "stout" if torque_target <= 3.4 else "balanced" if torque_target <= 3.9 else "active"
    material = "Mitsubishi MR70"
    if speed_mph >= 105:
        material = "Toray T800H"
    if speed_mph >= 112 or transition == "Hard":
        material = "Toray M40J"
    if speed_mph >= 118 or feel == "Boardy/stout":
        material = "Toray M46J"
    if speed_mph < 98 and feel == "Softer load":
        material = "Toray T700S"
    if feel == "Boardy/stout" and speed_mph < 108:
        material = "Hexcel IM7"
    architecture = "braid_tape_braid" if transition == "Hard" else "flag_wrap"
    if launch_bias.startswith("lower"):
        architecture = "automated_tape" if transition != "Hard" else "braid_tape_braid"
    if feel == "Softer load":
        architecture = "hybrid_flag_helix"

    intent = (
        f"Build a {target_cpm:.1f} CPM shaft with a {torque_window} torque window, "
        f"{launch_bias}, and {feel.lower()} feel."
    )
    rationale = [
        f"{speed_mph:.0f} mph speed sets the base stiffness target.",
        f"{tempo} tempo and {transition} transition adjust load stability.",
        f"{release} release timing tunes how much the tip can recover.",
        f"{miss} miss pattern biases the shaft away from the common miss.",
    ]
    build_steps = [
        f"Set global target CPM to {target_cpm:.1f}.",
        f"Use {material} as the starting material assumption.",
        f"Set primary bias pair near +/-{wrap_angle:.0f} degrees.",
        "Add a 0 degree butt/mid axial stability flag.",
        tip_strategy.capitalize() + ".",
        "Run CPM, torque, EI, and launch checks before freezing the CAD packet.",
    ]
    if feel == "Softer load":
        build_steps.insert(4, "Add a thin S-glass or aramid damping layer before increasing carbon stiffness.")
    if material in {"Toray M46J", "Mitsubishi Dialead K13C"}:
        build_steps.append("Keep ultra-high-modulus material local; avoid making the whole shaft brittle or harsh.")
    risks = []
    if transition == "Hard" and feel == "Softer load":
        risks.append("Hard transition conflicts with soft-load feel; prototype both torque and tip response before committing.")
    if miss == "Right" and launch_bias.startswith("lower"):
        risks.append("Right miss plus lower-launch target can feel too tip-stiff if overbuilt.")
    if torque_target <= 2.8:
        risks.append("Very low torque target may require extra hoop/braid support and could add harsh feel.")
    if speed_mph >= 115:
        risks.append("High-speed player: validate tip recovery and face closure with real range data.")
    if not risks:
        risks.append("No major conflict detected; still validate against measured CPM and player feedback.")

    test_plan = [
        "Build one baseline prototype from the generated CAD packet.",
        "Measure 7-zone CPM and compare each station to the target profile.",
        "Hit-test launch, spin, start line, and miss pattern before changing CAD.",
        "Adjust one variable at a time: wrap angle, tip flag width, or hoop/braid support.",
    ]
    return {
        "intent": intent,
        "torque_window": torque_window,
        "recommended_material": material,
        "recommended_architecture": architecture,
        "rationale": rationale,
        "build_steps": build_steps,
        "risk_flags": risks,
        "test_plan": test_plan,
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
    brief = fit_build_brief(
        target_cpm,
        torque_target,
        wrap_angle,
        launch_bias,
        tip_strategy,
        speed_mph,
        tempo,
        transition,
        release,
        miss,
        feel,
    )
    return {
        "target_cpm": target_cpm,
        "target_cpm_window": {"low": target_cpm - 3.0, "high": target_cpm + 3.0},
        "target_weight_g": weight_g,
        "torque_target_deg": torque_target,
        "wrap_angle_deg": wrap_angle,
        "launch_bias": launch_bias,
        "tip_strategy": tip_strategy,
        "zone_profile": profile,
        "builder_brief": brief,
        "cad_translation": {
            "set_target_cpm": target_cpm,
            "set_wrap_angle_deg": wrap_angle,
            "bias_pair_deg": [wrap_angle, -wrap_angle],
            "tip_strategy": tip_strategy,
            "recommended_architecture": brief["recommended_architecture"],
            "recommended_material": brief["recommended_material"],
        },
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


SHAFT_REFERENCE_DATABASE: list[dict[str, Any]] = [
    {
        "name": "Smooth loader mid-launch reference",
        "speed_range": [88, 102],
        "tempo": "Smooth",
        "transition": "Smooth",
        "profile": "active handle, stable mid, responsive tip",
        "material_family": "T700S / MR70 style intermediate modulus",
        "best_for": "players who need load feel without over-stiff tip recovery",
    },
    {
        "name": "Neutral tour-weight reference",
        "speed_range": [98, 110],
        "tempo": "Medium",
        "transition": "Medium",
        "profile": "balanced butt/mid/tip with neutral launch",
        "material_family": "T800H style high-strength carbon",
        "best_for": "baseline fitting and first prototype validation",
    },
    {
        "name": "Hard transition anti-left reference",
        "speed_range": [106, 118],
        "tempo": "Aggressive",
        "transition": "Hard",
        "profile": "firm handle, reinforced mid, tip/torque control",
        "material_family": "M40J / high-modulus bias support",
        "best_for": "fast loaders who close the face quickly or fight left misses",
    },
    {
        "name": "High-speed low-spin reference",
        "speed_range": [116, 130],
        "tempo": "Aggressive",
        "transition": "Hard",
        "profile": "localized ultra-high-modulus support with guarded feel",
        "material_family": "M46J / local pitch-fiber style reinforcement",
        "best_for": "very high-speed players after lower launch and tighter dispersion",
    },
]


def shaft_reference_matches(speed_mph: float, tempo: str, transition: str, miss: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in SHAFT_REFERENCE_DATABASE:
        low, high = item["speed_range"]
        score = 0
        if low <= speed_mph <= high:
            score += 3
        if item["tempo"] == tempo:
            score += 1
        if item["transition"] == transition:
            score += 2
        if miss == "Left" and "anti-left" in item["name"].lower():
            score += 2
        if miss == "High spin" and "low-spin" in item["name"].lower():
            score += 2
        if score:
            match = dict(item)
            match["match_score"] = score
            matches.append(match)
    return sorted(matches, key=lambda item: item["match_score"], reverse=True)[:3]


def diy_driver_tuneup(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate face-impact and DIY fitting observations into next fitting moves."""

    impact_pattern = str(payload.get("impact_pattern", "unknown") or "unknown").lower()
    vertical_impact = str(payload.get("vertical_impact", "unknown") or "unknown").lower()
    head_weight_feel = str(payload.get("head_weight_feel", "unknown") or "unknown").lower()
    current_length = float(payload.get("current_length_in", 45.5) or 45.5)
    gripped_down = float(payload.get("gripped_down_in", 0.0) or 0.0)
    pw_shaft_weight = float(payload.get("pw_shaft_weight_g", 120.0) or 120.0)
    added_head_weight = float(payload.get("added_head_weight_g", 0.0) or 0.0)

    effective_length = max(42.0, current_length - gripped_down)
    recommended_driver_shaft_weight = max(45.0, min(85.0, pw_shaft_weight * 0.5))
    actions: list[str] = []
    warnings: list[str] = []
    lead_tape_plan: list[str] = []
    shaft_notes: list[str] = []

    if impact_pattern in {"heel", "heel side", "all over", "scattered"}:
        actions.append("Test shorter playing length before cutting: grip down in 0.5 inch steps and mark the grip with tape.")
        actions.append("Retest impact marks until the strike pattern moves out of heel/scattered contact toward center-to-slight-toe.")
    elif impact_pattern in {"toe", "toe side"}:
        actions.append("Toe-side impact may mean the club is too short, but first check whether total/head weight is too high for the player.")
        warnings.append("Toe impact can be a player response to excessive weight, not only a length problem.")
    elif impact_pattern in {"ideal", "upper toe", "smiley"}:
        actions.append("Length is near the maximum useful range. Preserve this length unless launch/spin or dispersion proves otherwise.")
    else:
        actions.append("Start with face impact marks. The shaft builder should not guess before strike location is known.")

    if vertical_impact in {"low", "below center", "below vcog"}:
        actions.append("Raise tee height after length is stable; low-face contact generally adds spin.")
    elif vertical_impact in {"high", "above vcog", "too high"}:
        actions.append("Lower tee height slightly if impact is too high; above-center can cut spin, but too high costs ball speed.")
    elif vertical_impact in {"upper toe", "ideal"}:
        actions.append("Target upper-toe / slightly above-center contact: it can add launch and reduce spin without giving up smash.")

    if head_weight_feel in {"light", "too light"}:
        lead_tape_plan.append("Add lead tape one stripe at a time, blind-test feel and impact, then dial back from clearly too much.")
    elif head_weight_feel in {"heavy", "too heavy"}:
        lead_tape_plan.append("Reduce added head weight or test a lighter build before blaming shaft flex.")
        warnings.append("If the player starts pulling the club, excessive total/head weight can move impact opposite the expected direction.")
    else:
        lead_tape_plan.append("Use lead tape only after length/tee are controlled; avoid chasing swing-weight numbers.")

    lead_tape_plan.extend(
        [
            "Test nine sole positions: front/center/back crossed with heel/center/toe.",
            "Front sole tends to reduce dynamic loft and increases gear-effect influence.",
            "Back sole adds MOI/dynamic loft and reduces gear-effect severity.",
            "Toe placement biases fade; heel placement biases draw; center is neutral.",
            "Crown placement can raise VCOG and add spin compared with sole placement.",
        ]
    )

    shaft_notes.append(
        f"Driver shaft weight starting point from PW rule: about {recommended_driver_shaft_weight:.0f} g uncut if the PW shaft is {pw_shaft_weight:.0f} g."
    )
    shaft_notes.append("Simulate higher shaft/total weight by adding tape near the shaft balance point, not randomly on the head.")
    shaft_notes.append("Do not cut until tape-shorter and lead-tape tests show the direction is repeatable.")
    if added_head_weight > 0:
        shaft_notes.append(f"With {added_head_weight:.1f} g added head weight, check manufacturer tip-trim guidance; common driver rule is roughly 1/8 inch per 2.5 g, but graphite varies.")
    shaft_notes.append("Graphite wood tip trimming changes launch/tip behavior more than it changes flex; do not expect tip trim to turn R into S.")

    return {
        "effective_test_length_in": effective_length,
        "recommended_driver_shaft_weight_g": recommended_driver_shaft_weight,
        "impact_pattern": impact_pattern,
        "vertical_impact": vertical_impact,
        "head_weight_feel": head_weight_feel,
        "actions": actions,
        "lead_tape_plan": lead_tape_plan,
        "shaft_notes": shaft_notes,
        "warnings": warnings,
        "boundary": "This is a fitting workflow guide. Use strike pattern, feel, and launch monitor proof before changing CAD or cutting a shaft.",
    }


def visual_fitting_read(payload: dict[str, Any]) -> dict[str, Any]:
    """Use visual-fitting observations to detect player/shaft chemistry problems."""

    tempo_control = str(payload.get("visual_tempo_control", "unknown") or "unknown").lower()
    rhythm_float = str(payload.get("visual_rhythm_float", "unknown") or "unknown").lower()
    transition_move = str(payload.get("visual_transition_move", "unknown") or "unknown").lower()
    player_commitment = str(payload.get("visual_commitment", "unknown") or "unknown").lower()
    one_arm_shoulder = str(payload.get("visual_one_arm_shoulder", "unknown") or "unknown").lower()
    power_leaks = str(payload.get("visual_power_leaks", "unknown") or "unknown").lower()

    diagnosis: list[str] = []
    fitting_moves: list[str] = []
    shaft_design_bias: list[str] = []
    warnings: list[str] = []

    if tempo_control in {"inconsistent", "slow/insecure", "slow", "loose"} or rhythm_float in {"no float", "loose", "insecure"}:
        diagnosis.append("Tempo/rhythm looks insecure; the player may not trust the club or shaft load.")
        fitting_moves.append("Test more shaft weight or a stronger butt/mid section before assuming the player needs lighter.")
        shaft_design_bias.append("Add handle/mid feedback and resistance without immediately over-stiffening the tip.")

    if transition_move in {"jump start", "hips slide", "back and hips", "struggle"}:
        diagnosis.append("Player appears to jump-start transition, which often points to too much total weight or too stiff a handle/mid profile.")
        fitting_moves.append("Back down total/shaft weight a few grams and retest transition before changing launch profile.")
        shaft_design_bias.append("Reduce total-weight target or soften handle/mid load response while preserving face control.")

    if one_arm_shoulder in {"drop", "drops", "can't hold", "too heavy"}:
        diagnosis.append("One-arm shoulder drop suggests the total weight is above the player's useful upper limit.")
        fitting_moves.append("Lower shaft/total weight and retest until the left shoulder can control the club through the bottom.")
        shaft_design_bias.append("Cap the shaft weight recommendation and avoid adding mass to solve feel.")

    if player_commitment in {"kill ball", "overplay", "aggressive", "sparks"} or power_leaks in {"multiple bursts", "sparks", "leaking", "staged"}:
        diagnosis.append("Player is overplaying the club and leaking power in stages.")
        fitting_moves.append("Check whether butt/mid/tip are too stiff or feedback is too harsh, then reduce the trigger that makes him fight the shaft.")
        shaft_design_bias.append("Use smoother load feedback or damping; do not chase lower launch by making the tip brutally stiff.")

    if player_commitment in {"weak", "timid", "not committed"}:
        diagnosis.append("Player looks under-committed; this can be a club that is too light/weak, not necessarily a weak player.")
        fitting_moves.append("Test added shaft weight or MOI/resistance to see whether speed and commitment wake up.")
        shaft_design_bias.append("Raise weight/resistance trial before recommending a lighter shaft.")

    if not diagnosis:
        diagnosis.append("No obvious visual-fit conflict recorded. Use impact marks and launch data as the main proof.")
        fitting_moves.append("Keep the current shaft direction and change one variable at a time.")
        shaft_design_bias.append("Neutral visual fit: preserve feel while validating CPM, torque, launch, and dispersion.")

    warnings.extend(
        [
            "Shaft labels are not enough; a high-launch or low-launch label can produce the opposite result if it changes the player's motion.",
            "Use loft/head/ball to tune ball flight when possible; do not force the shaft to solve every flight problem and ruin feel.",
            "The right shaft is the player's dancing partner: trust visible rhythm, balance, and contact proof over catalog claims.",
        ]
    )

    return {
        "observations": {
            "tempo_control": tempo_control,
            "rhythm_float": rhythm_float,
            "transition_move": transition_move,
            "player_commitment": player_commitment,
            "one_arm_shoulder": one_arm_shoulder,
            "power_leaks": power_leaks,
        },
        "diagnosis": diagnosis,
        "fitting_moves": fitting_moves,
        "shaft_design_bias": shaft_design_bias,
        "warnings": warnings,
        "boundary": "Visual fitting is a directional read. Confirm with impact marks, launch monitor data, and player feedback.",
    }


def rollout_target_percent(speed_mph: float) -> float:
    """Howard Jones style driver rollout target: faster players need lower rollout percentage."""

    anchors = [(80.0, 13.0), (90.0, 12.0), (100.0, 11.0), (110.0, 10.0), (120.0, 9.0)]
    if speed_mph <= anchors[0][0]:
        return anchors[0][1]
    if speed_mph >= anchors[-1][0]:
        return anchors[-1][1]
    for (speed_a, pct_a), (speed_b, pct_b) in zip(anchors, anchors[1:]):
        if speed_a <= speed_mph <= speed_b:
            ratio = (speed_mph - speed_a) / (speed_b - speed_a)
            return pct_a + (pct_b - pct_a) * ratio
    return 11.0


def driver_launch_rollout_optimizer(payload: dict[str, Any]) -> dict[str, Any]:
    """Judge driver launch/spin/loft direction from club speed, carry, rollout, and PW carry."""

    speed_mph = float(payload.get("speed_mph", 105.0) or 105.0)
    launch_deg = float(payload.get("launch_deg", 13.5) or 13.5)
    attack_angle = float(payload.get("attack_angle_deg", 0.0) or 0.0)
    carry_yards = float(payload.get("carry_yards", 0.0) or 0.0)
    total_yards = float(payload.get("total_yards", 0.0) or 0.0)
    pw_carry_yards = float(payload.get("pw_carry_yards", 0.0) or 0.0)
    target_rollout_pct = rollout_target_percent(speed_mph)

    actual_rollout_pct: float | None = None
    rollout_read = "missing carry/total proof"
    recommendations: list[str] = []
    proof_steps: list[str] = []

    if carry_yards > 0 and total_yards > carry_yards:
        rollout_yards = total_yards - carry_yards
        actual_rollout_pct = rollout_yards / total_yards * 100.0
        delta = actual_rollout_pct - target_rollout_pct
        if delta > 1.0:
            rollout_read = "too much rollout for target carry/roll mix"
            recommendations.append("Spin/launch window may be too low for the player; test more loft, higher launch, or more spin before changing shaft stiffness.")
        elif delta < -1.0:
            rollout_read = "not enough rollout for target carry/roll mix"
            recommendations.append("Spin/launch window may be too high; test lower loft or spin control before blaming shaft weight.")
        else:
            rollout_read = "rollout is inside the target window"
            recommendations.append("Carry/roll mix is near optimized for the measured club speed.")
    else:
        recommendations.append("Measure carry and total with laser/GPS or launch monitor to judge rollout percentage.")

    if attack_angle >= 4.0 and launch_deg < 12.0:
        recommendations.append("Positive attack angle with low launch points to insufficient dynamic loft or low-face strike, not necessarily a shaft problem.")
    if attack_angle <= -2.0 and launch_deg > 15.0:
        recommendations.append("Negative attack angle with high launch can still spin too much; verify strike height and spin before adding loft.")

    pw_driver_carry_target: float | None = None
    pw_read = "PW carry not provided"
    if pw_carry_yards > 0:
        pw_driver_carry_target = pw_carry_yards * 2.03
        if carry_yards > 0:
            carry_delta = carry_yards - pw_driver_carry_target
            if carry_delta < -10.0:
                pw_read = "driver carry is short versus PW relationship"
                recommendations.append("Driver is underperforming relative to the PW reference; check impact, launch/spin, and playing length.")
            elif carry_delta > 10.0:
                pw_read = "driver carry is above PW relationship"
                recommendations.append("Driver carry is strong relative to PW; verify PW is a good working reference before changing driver setup.")
            else:
                pw_read = "driver carry matches PW relationship"
        else:
            pw_read = "PW reference target calculated, driver carry missing"

    proof_steps.extend(
        [
            "Use the same ball and normal course/range conditions when measuring carry and rollout.",
            "Compare rollout percentage to the club-speed target before deciding loft/spin changes.",
            "Use PW carry x 2.03 only when the PW is a good working reference club.",
            "Separate ball-flight tuning from shaft-feel tuning: loft/head/ball often solve flight cleaner than shaft tip alone.",
        ]
    )

    return {
        "speed_mph": speed_mph,
        "attack_angle_deg": attack_angle,
        "launch_deg": launch_deg,
        "target_rollout_pct": target_rollout_pct,
        "actual_rollout_pct": actual_rollout_pct,
        "rollout_read": rollout_read,
        "pw_driver_carry_target": pw_driver_carry_target,
        "pw_read": pw_read,
        "recommendations": recommendations,
        "proof_steps": proof_steps,
        "boundary": "Rollout percentage assumes good rollout conditions. Wet turf, wind, slope, ball, and landing angle can distort the read.",
    }


def static_length_lie_fit(payload: dict[str, Any]) -> dict[str, Any]:
    """Initial static iron fit from height and wrist-to-floor before dynamic validation."""

    height_in = float(payload.get("height_in", 69.0) or 69.0)
    wrist_to_floor_in = float(payload.get("wrist_to_floor_in", 34.0) or 34.0)
    standard_7i_length = 37.0

    # Calibrated from the provided height/WTF chart: use it as a starting map, not a final fit.
    length_delta = round(((height_in - 69.0) * 0.10 + (wrist_to_floor_in - 34.0) * 0.24) * 4.0) / 4.0
    length_delta = max(-1.5, min(2.0, length_delta))
    seven_iron_length = standard_7i_length + length_delta

    lie_delta = round((wrist_to_floor_in - 34.0) * 1.0 - (height_in - 69.0) * 0.22)
    lie_delta = int(max(-2, min(6, lie_delta)))
    lie_label = "standard"
    if lie_delta > 0:
        lie_label = f"{lie_delta} deg upright"
    elif lie_delta < 0:
        lie_label = f"{abs(lie_delta)} deg flat"

    notes = [
        "Use height and wrist-to-floor only as the initial build position.",
        "Confirm lie dynamically with face/sole marks, ball flight, and impact location.",
        "Grip, posture, hand height, toe droop, and swing delivery can override the static chart.",
        "For AE ShaftCAD, this is a setup baseline before the camera, visual fitting, and impact-mark layers take over.",
    ]
    if abs(length_delta) >= 1.0:
        notes.append("Large length adjustment: validate posture and strike before applying the full chart value.")
    if abs(lie_delta) >= 3:
        notes.append("Large lie adjustment: confirm with dynamic lie testing before bending/building.")

    return {
        "height_in": height_in,
        "wrist_to_floor_in": wrist_to_floor_in,
        "standard_7i_length_in": standard_7i_length,
        "recommended_7i_length_in": seven_iron_length,
        "length_delta_in": length_delta,
        "initial_lie_delta_deg": lie_delta,
        "initial_lie_label": lie_label,
        "notes": notes,
        "boundary": "Static charts are starting points only; the final fit comes from dynamic strike, posture, and ball-flight proof.",
    }


def shaft_sensation_quality_read(payload: dict[str, Any]) -> dict[str, Any]:
    """Blend subjective impact sensation with shot quality so speed is not the only shaft selector."""

    speed_mph = float(payload.get("speed_mph", 105.0) or 105.0)
    impact_sensation = str(payload.get("impact_sensation", "unknown") or "unknown").lower()
    miss_direction = str(payload.get("shot_miss_direction", "unknown") or "unknown").lower()
    quality_score = float(payload.get("shot_quality_score", 0.0) or 0.0)
    accuracy_score = float(payload.get("shot_accuracy_score", 0.0) or 0.0)
    preference_score = float(payload.get("shaft_preference_score", 0.0) or 0.0)
    current_flex = str(payload.get("current_flex_label", "unknown") or "unknown").lower()
    current_weight = float(payload.get("current_shaft_weight_g", 0.0) or 0.0)

    findings: list[str] = [
        "Do not select shaft flex from club speed alone; compare full profile, quality, accuracy, and feel.",
        "Use 7-zone shaft profile and subjective impact sensation, not only butt frequency or a printed flex label.",
    ]
    recommendations: list[str] = []
    design_bias: list[str] = []

    if speed_mph >= 112:
        findings.append("High club speed does not automatically mean the stiffest shaft wins.")
        design_bias.append("Keep softer/profile-active candidates in the test set even for high-speed players.")

    if impact_sensation in {"harsh", "dead", "boardy", "hard"}:
        recommendations.append("Test a softer or more active profile before adding stiffness; harsh feedback can make the player fight the shaft.")
        design_bias.append("Soften feedback in the butt/tip sections or add damping while maintaining enough weight for control.")
    elif impact_sensation in {"loose", "whippy", "unstable"}:
        recommendations.append("Test more stability through weight, torque, or mid/tip control before assuming the player needs a stiffer label.")
        design_bias.append("Add stability locally; avoid making the entire shaft boardy.")
    elif impact_sensation in {"solid", "easy", "loaded", "comfortable"}:
        recommendations.append("Protect this feel while tuning launch, spin, and dispersion.")
        design_bias.append("Preserve the current load feedback and adjust only the section causing the measured miss.")
    else:
        recommendations.append("Capture a simple pairwise preference after two shafts; subjective feel should become data, not a guess.")

    if miss_direction in {"left", "hook", "pull left"}:
        recommendations.append("Left misses with a soft/light feel can indicate the shaft is not stable enough for delivery.")
        design_bias.append("Add mid/tip stability or torque control without jumping straight to the stiffest/heaviest build.")
    elif miss_direction in {"right", "slice", "push right"}:
        recommendations.append("Right misses with harsh/stiff feel can indicate the player cannot square the face comfortably.")
        design_bias.append("Restore load/release feedback before reducing loft or forcing a lower-launch tip.")

    if quality_score and preference_score:
        if preference_score >= 7 and quality_score < 5:
            recommendations.append("Player likes the feel but quality is weak; keep the feel direction and fix the section causing dispersion.")
        elif quality_score >= 6 and preference_score < 5:
            recommendations.append("Objective result is decent but sensation is poor; do not trust repeatability until feel improves.")
        elif quality_score >= 6 and preference_score >= 7:
            recommendations.append("Feel and shot quality agree; use this profile as the comparison anchor.")

    if current_flex in {"s", "stiff", "x", "x-stiff", "extra stiff"} and impact_sensation in {"harsh", "dead", "boardy", "hard"}:
        recommendations.append("Strong evidence to include regular/softer-profile candidates in comparison testing.")
    if current_weight >= 78 and miss_direction in {"right", "slice", "push right"}:
        recommendations.append("Heavy/stiff right-miss pattern: test lower total weight or more active release profile.")

    return {
        "impact_sensation": impact_sensation,
        "shot_miss_direction": miss_direction,
        "shot_quality_score": quality_score,
        "shot_accuracy_score": accuracy_score,
        "shaft_preference_score": preference_score,
        "findings": findings,
        "recommendations": recommendations,
        "design_bias": design_bias,
        "study_anchor": "Burger/Senner 2014: impact sensation and 7-zone shaft profile belong in shaft fitting; speed alone is insufficient.",
        "boundary": "Subjective sensation is not proof by itself. Pair it with distance, accuracy, face impact, and repeatability.",
    }


def wishon_profile_guard(payload: dict[str, Any]) -> dict[str, Any]:
    """Wishon-style guardrails for bend profile, torque, and trimming decisions."""

    speed_mph = float(payload.get("speed_mph", 105.0) or 105.0)
    transition = str(payload.get("transition", payload.get("visual_transition_move", "unknown")) or "unknown").lower()
    tempo = str(payload.get("tempo", payload.get("visual_tempo_control", "unknown")) or "unknown").lower()
    release = str(payload.get("release", "Mid") or "Mid").lower()
    miss_direction = str(payload.get("shot_miss_direction", "unknown") or "unknown").lower()
    impact_sensation = str(payload.get("impact_sensation", "unknown") or "unknown").lower()
    current_torque = float(payload.get("current_torque_deg", 0.0) or 0.0)

    findings = [
        "Use measured 7-point bend profile data before trusting R/S/X flex labels.",
        "Butt, mid, and tip sections should be treated separately because different swing phases load different shaft sections.",
        "Torque is mainly an accuracy/feel guardrail; weight, overall stiffness, and bend profile usually matter more.",
    ]
    profile_requirements = [
        "Store CPM/frequency at seven stations and classify butt, mid, and tip stiffness independently.",
        "Compare profile shape against known shafts instead of comparing only butt CPM.",
        "When a target shaft is known, search for profile-match candidates by percentage, weight, torque, and availability.",
    ]
    recommendations: list[str] = []
    trimming_notes: list[str] = []
    torque_notes: list[str] = []

    aggressive = "hard" in transition or "jump" in transition or "aggressive" in tempo or speed_mph >= 112
    if aggressive:
        recommendations.append("Strong transition / fast tempo: prioritize profile stability and consider the firmer trim family before chasing a stiffer printed flex.")
    else:
        recommendations.append("Smooth or moderate move: keep softer/profile-active candidates alive and let impact quality decide.")

    if current_torque >= 5.0 and aggressive:
        torque_notes.append("High torque with aggressive transition can allow the head to over-rotate and produce left/hook bias.")
    elif current_torque > 0 and current_torque <= 3.0 and impact_sensation in {"harsh", "dead", "boardy"}:
        torque_notes.append("Very low torque can feel less solid/comfortable for some players; do not over-tighten torque if feel suffers.")
    else:
        torque_notes.append("Treat torque as a fine-tuning variable after length, weight, profile, and strike pattern are under control.")

    if miss_direction in {"left", "hook", "pull left"} and aggressive:
        recommendations.append("Left miss with aggressive transition: add torque/profile stability locally before changing the whole shaft.")
    if miss_direction in {"right", "slice", "push right"} and impact_sensation in {"harsh", "dead", "boardy"}:
        recommendations.append("Right miss with harsh/stiff feedback: test more active release feel before reducing loft or adding tip stiffness.")

    trimming_notes.extend(
        [
            "Driver wood trim starts at 0 inch tip trim; butt trim to final length after fitting.",
            "Increasing tip trim by 0.5 inch should mostly feel slightly firmer, not radically change launch/spin.",
            "Increasing tip trim by 1 inch is a stronger stiffness change; launch/spin effects are still modest and show most for later-release players.",
            "Decreasing tip trim softens feel; do not use trimming as a substitute for selecting the correct bend profile.",
        ]
    )
    if release == "late":
        trimming_notes.append("Late release player: tip-trim changes are more likely to show in launch/spin, so validate carefully.")

    return {
        "findings": findings,
        "profile_requirements": profile_requirements,
        "recommendations": recommendations,
        "torque_notes": torque_notes,
        "trimming_notes": trimming_notes,
        "source_anchor": "Tom Wishon Shaft Selector / trimming / torque guidance: bend profile beats flex label; torque is secondary to weight, stiffness, and profile.",
        "boundary": "Wishon guardrails are fitting logic, not a manufacturer-specific prescription. Validate with measured profile, impact marks, and player testing.",
    }


def fitting_interview_read(payload: dict[str, Any]) -> dict[str, Any]:
    """Pre-fit interview summary from driver/iron fitting intake questions."""

    interview = payload.get("fitting_interview") or {}
    club_type = str(interview.get("club_type", "driver") or "driver").lower()
    tendencies = [str(item).lower() for item in interview.get("poor_shot_tendencies", [])]
    wants = [str(item).lower() for item in interview.get("personal_wants", [])]
    pain = str(interview.get("physical_pain", "unknown") or "unknown").lower()
    limitations = str(interview.get("physical_limitations", "unknown") or "unknown").lower()
    confidence = str(interview.get("confidence", "unknown") or "unknown").lower()
    weight_feel = str(interview.get("club_weight_feel", "unknown") or "unknown").lower()
    goal = str(interview.get("immediate_goal", "unknown") or "unknown").lower()
    handicap_trend = str(interview.get("handicap_trend", "unknown") or "unknown").lower()

    start_points: list[str] = []
    watch_items: list[str] = []
    fitter_questions: list[str] = []

    if pain == "yes" or limitations == "yes":
        start_points.append("Start with comfort and repeatability before chasing speed.")
        watch_items.append("Do not force heavy, long, or harsh builds until pain/limitation notes are understood.")
        fitter_questions.append("Where does the swing hurt, and does it change through the round?")

    if "slice" in tendencies or "stop slicing" in wants or "push right" in tendencies or "stop pushing" in wants:
        start_points.append("Begin with face delivery, strike location, playing length, and release feel.")
        watch_items.append("Right-miss pattern: avoid making the shaft so stiff/boardy the player cannot square it.")
    if "hook" in tendencies or "stop hooking" in wants or "pull left" in tendencies or "stop pulling" in wants:
        start_points.append("Begin with torque/profile stability, face angle, and left-bias control.")
        watch_items.append("Left-miss pattern: check high-torque/light/soft combinations before adding loft or length.")
    if "very inconsistent" in tendencies or "straight but unsolid hit" in tendencies or "more consistent" in wants or "drive the ball with more consistency" in wants:
        start_points.append("Begin with center-contact controls: length, total weight, swingweight, and impact pattern.")
    if "hit very low" in tendencies or "hit the ball higher" in wants:
        start_points.append("Check launch window, dynamic loft, shaft tip response, and loft before changing flex label.")
    if "sky it" in tendencies or "hit the ball lower" in wants:
        start_points.append("Check impact height, attack angle, tee/ball position, and spin before stiffening everything.")
    if "hit the ball longer" in wants:
        start_points.append("Distance goal: protect contact quality first, then test speed, launch, and spin gains.")
    if confidence == "no confidence":
        watch_items.append("Low confidence: use smaller test changes and show the player clear cause/effect.")
    if weight_feel == "too heavy":
        start_points.append("Current club feels heavy: test lower total weight or shorter length before adding head weight.")
    elif weight_feel == "too light":
        start_points.append("Current club feels light: test more head/shaft weight and watch face control.")
    if "find out" in goal:
        fitter_questions.append("Is the goal validation of the current club, a rebuild, or a new shaft design?")
    if handicap_trend == "going up":
        watch_items.append("Handicap trending up: prioritize misses, confidence, and playable dispersion over max-distance claims.")

    if club_type == "iron":
        start_points.append("Iron path: include static length/lie, dynamic lie marks, shaft weight, and contact pattern early.")
    else:
        start_points.append("Driver path: include loft, face angle, playing length, strike height, and carry/roll proof early.")

    if not start_points:
        start_points.append("Start with baseline interview, current specs, impact marks, and three clean swings.")

    return {
        "club_type": club_type,
        "start_points": start_points,
        "watch_items": watch_items,
        "fitter_questions": fitter_questions,
        "source": "Maltby-style driver/iron personal fitting interview",
        "captured": interview,
    }


def manufacturing_zones(fit: dict[str, Any], swing: dict[str, Any]) -> list[dict[str, Any]]:
    transition = fit["inputs"]["transition"]
    release = fit["inputs"]["release"]
    miss = fit["inputs"]["miss"]
    load_index = swing["shaft_load_index"]
    torque = fit["torque_target_deg"]
    return [
        {
            "zone": "Butt / handle",
            "design_goal": "Preserve load feel without letting the handle collapse.",
            "layup_note": "Use axial 0 degree stability with light hoop support; increase butt flag width when load index exceeds 72.",
            "qc_target": "41 inch and 36 inch CPM should step smoothly without a dead handle.",
            "trigger": f"{transition} transition, load index {load_index:.0f}",
        },
        {
            "zone": "Mid / recovery",
            "design_goal": "Control kick timing and keep face delivery predictable.",
            "layup_note": f"Bias pair near +/-{fit['wrap_angle_deg']:.0f} degrees; add braid/tape/braid support for hard transitions.",
            "qc_target": "31/26/21 inch CPM slope must not show a flat spot.",
            "trigger": f"{release} release timing",
        },
        {
            "zone": "Tip / launch",
            "design_goal": fit["tip_strategy"],
            "layup_note": "Use local tip flag changes first; avoid overbuilding the whole shaft to solve a tip-only problem.",
            "qc_target": "16 inch and 11 inch stations stay inside target window; torque validates before player test.",
            "trigger": f"{fit['launch_bias']}, {miss} miss",
        },
        {
            "zone": "Torque / feel shell",
            "design_goal": f"Hold roughly {torque:.2f} deg torque while protecting feel.",
            "layup_note": "Use hoop/helix/braid as a shell variable; validate torque before adding stiffer carbon everywhere.",
            "qc_target": "Torque, EI, CPM, and range feedback agree before freezing CAD.",
            "trigger": f"face closure {swing['face_closure_rate']:.0f}, tempo {fit['inputs']['tempo']}",
        },
    ]


def swing_capture_to_fit(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate camera/manual swing capture metrics into a buildable shaft target."""

    speed_mph = float(payload.get("speed_mph", 105.0) or 105.0)
    launch_deg = float(payload.get("launch_deg", 13.5) or 13.5)
    spin_rpm = float(payload.get("spin_rpm", 2650.0) or 2650.0)
    weight_g = float(payload.get("weight_g", 65.0) or 65.0)
    tempo_seconds = float(payload.get("tempo_seconds", 1.05) or 1.05)
    transition_load = float(payload.get("transition_load", 55.0) or 55.0)
    release_score = float(payload.get("release_score", 50.0) or 50.0)
    closure_rate = float(payload.get("face_closure_rate", 50.0) or 50.0)
    attack_angle = float(payload.get("attack_angle_deg", 0.0) or 0.0)
    face_to_path = float(payload.get("face_to_path_deg", 0.0) or 0.0)
    shaft_load_index = float(payload.get("shaft_load_index", transition_load) or transition_load)
    hand_path = str(payload.get("hand_path", "neutral") or "neutral")
    motion_quality = float(payload.get("motion_quality", 70.0) or 70.0)
    motion_score = float(payload.get("motion_score", 50.0) or 50.0)

    tempo = "Smooth" if tempo_seconds >= 1.18 else "Aggressive" if tempo_seconds <= 0.9 or motion_score >= 72 else "Medium"
    transition = "Hard" if transition_load >= 68 or shaft_load_index >= 72 or motion_score >= 78 else "Smooth" if transition_load <= 38 else "Medium"
    release = "Late" if release_score >= 64 else "Early" if release_score <= 36 else "Mid"
    miss = "Left" if closure_rate >= 68 or face_to_path >= 3.0 else "Right" if closure_rate <= 32 or face_to_path <= -3.0 else "High spin" if spin_rpm >= 3100 else "Low launch" if launch_deg <= 10.5 or attack_angle <= -2.0 else "Neutral"
    feel = "Boardy/stout" if transition == "Hard" and speed_mph >= 108 else "Softer load" if tempo == "Smooth" and transition != "Hard" else "Stable mid"

    fit = fit_target_from_swing(
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
    fit["swing_capture"] = {
        "source": payload.get("source", "camera/manual"),
        "speed_mph": speed_mph,
        "tempo_seconds": tempo_seconds,
        "transition_load": transition_load,
        "release_score": release_score,
        "face_closure_rate": closure_rate,
        "attack_angle_deg": attack_angle,
        "face_to_path_deg": face_to_path,
        "shaft_load_index": shaft_load_index,
        "hand_path": hand_path,
        "motion_quality": motion_quality,
        "motion_score": motion_score,
        "derived_inputs": {
            "tempo": tempo,
            "transition": transition,
            "release": release,
            "miss": miss,
            "feel": feel,
        },
        "confidence": "usable" if motion_quality >= 65 else "manual review required",
        "boundary": "Camera metrics are fitting inputs, not final manufacturing proof. Validate with CPM and range testing.",
    }
    fit["why_this_fit"] = [
        f"{speed_mph:.0f} mph speed sets the base stiffness and weight class.",
        f"{tempo} tempo with {transition} transition drives the handle/mid stability target.",
        f"{release} release timing and {closure_rate:.0f} face-closure score shape tip recovery.",
        f"{launch_deg:.1f} deg launch, {spin_rpm:.0f} rpm spin, and {attack_angle:.1f} deg attack angle set the launch/spin bias.",
        f"{hand_path} hand path and {face_to_path:.1f} deg face-to-path are treated as directional fit clues, not final proof.",
    ]
    fit["manufacturing_zones"] = manufacturing_zones(fit, fit["swing_capture"])
    fit["proof_requirements"] = [
        "Capture at least three clean swings before trusting the camera profile.",
        "Compare the generated 7-zone CPM target against the measured shaft after build.",
        "Validate launch, spin, start line, and face delivery on a launch monitor.",
        "Change one build variable at a time so the database learns what actually moved performance.",
        "Store prototype results in the shaft database before declaring the recipe proven.",
    ]
    fit["shaft_database_matches"] = shaft_reference_matches(speed_mph, tempo, transition, miss)
    fit["diy_driver_tuneup"] = diy_driver_tuneup(payload)
    fit["visual_fitting"] = visual_fitting_read(payload)
    fit["launch_rollout_optimizer"] = driver_launch_rollout_optimizer(payload)
    fit["static_length_lie"] = static_length_lie_fit(payload)
    fit["shaft_sensation_quality"] = shaft_sensation_quality_read(payload)
    fit["wishon_profile_guard"] = wishon_profile_guard(payload)
    fit["fitting_interview"] = fitting_interview_read(payload)
    return fit


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
        "; Golf shaft tapered mandrel core based on shaft inner diameter stations",
    ]
    z_pos = 0.0
    for index, segment in enumerate(segments, start=1):
        start_radius = segment.inner_diameter_m * radius_scale
        z_next = z_pos + segment.length_m * linear_scale
        end_radius = segment.inner_diameter_m * radius_scale
        if index < len(segments):
            end_radius = segments[index].inner_diameter_m * radius_scale
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
    """Create a solid tapered mandrel core from shaft ID stations."""
    z = 0.0
    work = cq.Workplane("XY")

    for index, segment in enumerate(SEGMENTS):
        radius = segment["id_mm"] / 2.0
        work = work.workplane(offset=z).circle(radius)
        z += segment["length_mm"]

        if index == len(SEGMENTS) - 1:
            final_radius = segment["id_mm"] / 2.0
            work = work.workplane(offset=z).circle(final_radius)

    return work.loft(combine=True)


if __name__ == "__main__":
    shaft = make_shaft_envelope()
    cq.exporters.export(shaft, "shaftcad_shaft_envelope.step")
    cq.exporters.export(make_mandrel_core(), "shaftcad_mandrel_core.step")
    print("Exported shaftcad_shaft_envelope.step and shaftcad_mandrel_core.step")
'''


def mandrel_station_table(segments: list[Segment]) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    z_mm = 0.0
    for segment in segments:
        rows.append(
            {
                "station": f"{segment.name} start",
                "z_mm": round(z_mm, 3),
                "shaft_od_mm": round(segment.outer_diameter_m * 1000.0, 3),
                "mandrel_od_mm": round(segment.inner_diameter_m * 1000.0, 3),
            }
        )
        z_mm += segment.length_m * 1000.0
    last = segments[-1]
    rows.append(
        {
            "station": f"{last.name} end",
            "z_mm": round(z_mm, 3),
            "shaft_od_mm": round(last.outer_diameter_m * 1000.0, 3),
            "mandrel_od_mm": round(last.inner_diameter_m * 1000.0, 3),
        }
    )
    return rows


def ply_schedule(
    segments: list[Segment],
    material: Material,
    architecture_key: str,
    wrap_angle_deg: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 1
    for segment in segments:
        for ply_index, ply in enumerate(segment.layup, start=1):
            purpose = "axial EI / CPM stability" if abs(ply.angle_deg) < 1 else "bias torsion and recovery"
            if abs(abs(ply.angle_deg) - 90.0) < 1:
                purpose = "hoop crush support"
            rows.append(
                {
                    "order": order,
                    "zone": segment.name,
                    "ply": ply_index,
                    "material": material.name,
                    "fiber_angle_deg": round(ply.angle_deg, 2),
                    "thickness_mm": round(ply.thickness_m * 1000.0, 4),
                    "purpose": purpose,
                    "architecture": architecture_key,
                    "note": "Prototype schedule; confirm exact prepreg areal weight and resin system with manufacturer.",
                }
            )
            order += 1
    if architecture_key in {"tubular_braid", "braid_tape_braid"}:
        rows.append(
            {
                "order": order,
                "zone": "Full length",
                "ply": "braid sleeve",
                "material": material.name,
                "fiber_angle_deg": round(wrap_angle_deg, 2),
                "thickness_mm": 0.08,
                "purpose": "balanced +/- braid sleeve for torsion symmetry",
                "architecture": architecture_key,
                "note": "Sleeve angle is a manufacturing target; supplier must set carrier count and pick count.",
            }
        )
    return rows


def flag_template_schedule(segments: list[Segment], wrap_angle_deg: float) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    z_mm = 0.0
    layer_specs = [
        ("axial", 0.0, 1.0),
        ("bias_plus", wrap_angle_deg, 0.62),
        ("bias_minus", -wrap_angle_deg, 0.62),
        ("hoop_support", 90.0, 0.38),
    ]
    for index, segment in enumerate(segments):
        length_mm = segment.length_m * 1000.0
        root_circumference = pi * segment.outer_diameter_m * 1000.0
        next_segment = segments[index + 1] if index + 1 < len(segments) else segment
        tip_circumference = pi * next_segment.outer_diameter_m * 1000.0
        for name, angle, coverage in layer_specs:
            templates.append(
                {
                    "id": f"{segment.name.lower().replace(' ', '_')}_{name}",
                    "zone": segment.name,
                    "start_z_mm": round(z_mm, 3),
                    "end_z_mm": round(z_mm + length_mm, 3),
                    "flat_pattern_length_mm": round(length_mm, 3),
                    "root_wrap_width_mm": round(root_circumference * coverage, 3),
                    "tip_wrap_width_mm": round(tip_circumference * coverage, 3),
                    "fiber_angle_deg": round(angle, 2),
                    "ply_thickness_mm": 0.125,
                    "seam_clock_deg": 180 if "minus" in name else 0,
                    "cut_file_layer": name,
                }
            )
        z_mm += length_mm
    return templates


def build_manufacturer_handoff(
    segments: list[Segment],
    material: Material,
    method_key: str,
    method: dict[str, Any],
    architecture_key: str,
    architecture: dict[str, Any],
    wrap_angle_deg: float,
    target_cpm: float,
    overall_cpm_value: float,
    zones: list[dict[str, float]],
    torsion_value: float,
    behavior: dict[str, Any],
    gcode: str,
    step_recipe: str,
    driver_spec_check: dict[str, Any],
) -> dict[str, Any]:
    capped_zones = [zone for zone in zones if bool(zone.get("analyzer_limited"))]
    warnings = [
        "Prototype handoff only; manufacturer must validate laminate, resin, cure cycle, sanding allowance, and destructive test samples.",
        "Material properties are engineering estimates unless replaced by supplier datasheets.",
    ]
    if capped_zones:
        warnings.append("One or more CPM stations hit the 0-999 Auditor display cap; use raw_model_cpm only as simulation context.")
    warnings.extend(driver_spec_check.get("flags", []))
    return {
        "package": "AE ShaftCAD Manufacturer Handoff Pack",
        "readiness_level": "prototype_quote_and_first_article",
        "design_intent": {
            "target_cpm": round(target_cpm, 2),
            "predicted_cpm": round(overall_cpm_value, 2),
            "cpm_error": round(overall_cpm_value - target_cpm, 2),
            "torsion_deg_at_15nm": round(torsion_value, 3),
            "architecture": architecture_key,
            "manufacturing_method": method_key,
            "material": material.name,
            "behavior_summary": behavior.get("fingerprint", {}),
        },
        "driver_shaft_spec_check": driver_spec_check,
        "mandrel_geometry": {
            "basis": "shaft inner diameter stations",
            "total_length_mm": round(total_length(segments) * 1000.0, 3),
            "stations": mandrel_station_table(segments),
        },
        "shaft_envelope": {
            "basis": "finished outer diameter stations before paint/sanding allowance",
            "segments": [
                {
                    "name": segment.name,
                    "length_mm": round(segment.length_m * 1000.0, 3),
                    "outer_diameter_mm": round(segment.outer_diameter_m * 1000.0, 3),
                    "inner_diameter_mm": round(segment.inner_diameter_m * 1000.0, 3),
                    "nominal_wall_mm": round((segment.outer_diameter_m - segment.inner_diameter_m) * 500.0, 3),
                }
                for segment in segments
            ],
        },
        "ply_schedule": ply_schedule(segments, material, architecture_key, wrap_angle_deg),
        "flag_templates": flag_template_schedule(segments, wrap_angle_deg),
        "exports": {
            "mandrel_gcode": gcode,
            "cadquery_step_recipe": step_recipe,
            "required_cut_exports": ["flag_template_dxf", "flag_template_svg", "ply_schedule_json"],
        },
        "tolerances": {
            "mandrel_od_mm": "+/-0.03 prototype, tighten after first article",
            "flag_length_mm": "+/-0.50",
            "flag_width_mm": "+/-0.25",
            "fiber_angle_deg": "+/-1.0",
            "raw_weight_g": "+/-1.5",
            "finished_cpm": "+/-3 CPM overall, +/-5 CPM station profile",
            "torque_deg": "+/-0.2 deg after process is locked",
        },
        "qc_checklist": [
            "Verify mandrel station diameters before layup.",
            "Confirm prepreg material, ply thickness, resin system, and shelf life.",
            "Cut axial, bias, and hoop/support flags from the exported templates.",
            "Clock seams away from each other through the stack.",
            "Record raw layup weight before cure.",
            "Cure using manufacturer-approved prepreg cycle.",
            "Measure finished OD, weight, balance point, straightness, torque, and 7-zone CPM.",
            "Hit-test launch, spin, start line, and miss tendency before changing more than one variable.",
        ],
        "revision_loop": [
            "If overall CPM is high, reduce wall/thickness scale or soften axial material first.",
            "If tip CPM/launch is too stiff, reduce tip hoop density before weakening handle stability.",
            "If torque is too loose, increase bias/braid support before adding full-length mass.",
            "If feel is harsh, localize high-modulus carbon and add damping veil/glass/aramid selectively.",
        ],
        "warnings": warnings,
        "manufacturer_question_list": [
            "What prepreg systems and ply thicknesses are available?",
            "Can the shop cut DXF/SVG flag templates directly?",
            "What mandrel tolerance and taper resolution can be held?",
            "What cure cycle, shrink tape, sanding, and paint allowance should be modeled?",
            "What first-article QC data can be returned for model calibration?",
        ],
        "architecture_note": architecture.get("cad_role", ""),
        "method_note": method.get("note", ""),
    }


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
    material_e1_pa: float | None = None,
    material_e2_pa: float | None = None,
    material_g12_pa: float | None = None,
    material_nu12: float | None = None,
    material_density_kg_m3: float | None = None,
    material_cost_per_kg: float | None = None,
) -> dict[str, Any]:
    material = MATERIALS.get(material_name, MATERIALS["Mitsubishi MR70"])
    if all(v is not None for v in [material_e1_pa, material_e2_pa, material_g12_pa, material_nu12, material_density_kg_m3, material_cost_per_kg]):
        material = Material(
            name=material_name,
            e1_pa=max(1.0, float(material_e1_pa)),
            e2_pa=max(1.0, float(material_e2_pa)),
            g12_pa=max(1.0, float(material_g12_pa)),
            nu12=max(0.0, min(0.49, float(material_nu12))),
            density_kg_m3=max(1.0, float(material_density_kg_m3)),
            cost_per_kg=max(0.0, float(material_cost_per_kg)),
        )
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
    behavior = behavior_intelligence(cpm, zones, torsion, head_speed_mph)
    driver_spec_check = driver_shaft_spec_check(segments, mass * 1000.0)
    gcode = generate_mandrel_gcode(
        segments,
        units=gcode_units,
        rapid_feed=gcode_rapid_feed,
        cut_feed=gcode_cut_feed,
        spin_feed=gcode_spin_feed,
        spindle_rpm=gcode_spindle_rpm,
        tool_number=gcode_tool_number,
        pass_count=gcode_pass_count,
    )
    step_recipe = generate_cadquery_step_recipe(segments)
    manufacturer_handoff = build_manufacturer_handoff(
        segments,
        material,
        method_key,
        method,
        architecture_mode,
        architecture,
        wrap_angle_deg,
        target_cpm,
        cpm,
        zones,
        torsion,
        behavior,
        gcode,
        step_recipe,
        driver_spec_check,
    )
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
        "driver_shaft_spec_check": driver_spec_check,
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
        "behavior_intelligence": behavior,
        "gcode": gcode,
        "cadquery_step_recipe": step_recipe,
        "manufacturer_handoff": manufacturer_handoff,
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
    main { display: grid; grid-template-columns: 360px 1fr; gap: 0; min-height: calc(100vh - 111px); }
    body.camera-focus main { grid-template-columns: 1fr; }
    body.camera-focus main > section:first-child { display: none; }
    section { background: #f8fbfa; border-right: 1px solid #b9c8c4; padding: 16px; }
    section.workspace { background: #eef2f0; border-right: 0; padding: 0; }
    .workspace-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; background: #ffffff; border-bottom: 1px solid #cdd9d6; padding: 12px 14px; }
    .workspace-title { font-size: 18px; font-weight: 700; }
    .tabs { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
    .tab { width: auto; margin: 0; padding: 8px 12px; min-height: 38px; background: #d7e2df; color: #17211f; border: 1px solid #b9c8c4; border-radius: 6px; }
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
    .quick-start { background: #ffffff; border: 1px solid #cbd8d5; border-left: 5px solid #17695f; border-radius: 8px; padding: 12px; margin: 10px 0 14px; }
    .quick-start strong { display: block; margin-bottom: 4px; font-size: 15px; }
    .quick-start span { display: block; color: #50615e; font-size: 13px; line-height: 1.35; }
    .primary-actions { position: sticky; top: 0; z-index: 3; background: #f8fbfa; border: 1px solid #cbd8d5; border-radius: 8px; padding: 10px; margin-top: 14px; box-shadow: 0 8px 18px rgba(23, 33, 31, 0.08); }
    .primary-actions button { margin-top: 8px; }
    .primary-actions .secondary-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    details.control-group { border: 1px solid #cbd8d5; border-radius: 8px; background: #ffffff; margin-top: 12px; overflow: hidden; }
    details.control-group summary { cursor: pointer; padding: 11px 12px; font-weight: 800; color: #17211f; background: #eef5f3; }
    details.control-group .control-body { padding: 0 12px 12px; }
    .guidance-card { background: #ffffff; border: 1px solid #cbd8d5; border-left: 5px solid #17695f; border-radius: 8px; padding: 12px; margin: 12px 0 14px; display: grid; grid-template-columns: minmax(150px, 0.7fr) 1fr; gap: 10px; align-items: center; }
    .guidance-card.warn { border-left-color: #d9911f; }
    .guidance-card.bad { border-left-color: #b3261e; }
    .guidance-card span { display: block; color: #50615e; font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .guidance-card strong { display: block; font-size: 20px; margin-top: 3px; }
    .guidance-card p { margin: 0; color: #263834; line-height: 1.4; }
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
    .shaft-data-grid { display: grid; grid-template-columns: minmax(320px, 0.75fr) minmax(520px, 1.25fr); gap: 14px; align-items: start; }
    .shaft-data-card { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 8px; padding: 12px; }
    .shaft-data-card h3 { margin-top: 0; }
    .auditor-table input { margin: 0; padding: 8px; }
    .auditor-table td, .auditor-table th { vertical-align: top; }
    .auditor-readout { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
    .auditor-readout .card { background: #eef5f3; border: 1px solid #cbd8d5; }
    .fit-builder-brief { border: 1px solid #cbd8d5; background: #f9fbfa; border-radius: 6px; padding: 12px; margin: 12px 0; }
    .fit-builder-brief h3 { margin-top: 0; }
    .camera-fit-layout { display: grid; grid-template-columns: minmax(360px, 1.2fr) minmax(320px, 0.8fr); gap: 14px; align-items: start; }
    body.camera-focus .camera-fit-layout { grid-template-columns: 1fr; }
    body.camera-focus .camera-stage video { min-height: clamp(300px, 34vw, 560px); }
    .camera-stage { background: #101918; color: #d7fff6; border: 1px solid #2d3f3c; border-radius: 8px; padding: 12px; }
    .camera-feed-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .camera-feed-card { border: 1px solid #344642; border-radius: 8px; padding: 8px; background: #0a1211; }
    .camera-feed-card h4 { margin: 0 0 7px; color: #ffffff; }
    .camera-stage video { width: 100%; aspect-ratio: 16 / 9; background: #050808; border: 1px solid #344642; border-radius: 6px; display: block; object-fit: cover; }
    .camera-stage canvas { display: none; }
    .camera-hud { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 10px; font-size: 13px; color: #c8d8d4; }
    .camera-hud strong { color: #ffffff; }
    .camera-controls { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; }
    .camera-controls button { margin-top: 0; }
    .camera-note { background: #fff8df; border: 1px solid #e7c56b; border-radius: 6px; color: #4d3600; padding: 10px; margin: 10px 0; font-size: 13px; line-height: 1.35; }
    .swing-meter { height: 12px; background: #dbe4e1; border-radius: 999px; overflow: hidden; }
    .swing-meter span { display: block; height: 100%; width: 0%; background: #17695f; transition: width 160ms linear; }
    .camera-result { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 8px; padding: 12px; }
    .camera-result h3 { margin-top: 0; }
    .interview-panel { border: 1px solid #cbd8d5; background: #f8fbfa; border-radius: 8px; padding: 10px; margin-bottom: 12px; }
    .interview-panel summary { cursor: pointer; font-weight: 800; color: #0d3f35; }
    .interview-checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 10px; margin-top: 8px; }
    .interview-checks label { display: flex; gap: 7px; align-items: center; margin: 0; font-weight: 500; font-size: 13px; }
    .interview-checks input { width: auto; margin: 0; }
    .camera-capture-list { display: grid; gap: 7px; margin-top: 8px; }
    .camera-capture-pill { border: 1px solid #d9e4e1; background: #eef5f3; border-radius: 6px; padding: 8px; font-size: 13px; }
    .camera-section-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
    .camera-section-card { border: 1px solid #cbd8d5; border-radius: 8px; padding: 10px; background: #f8fbfa; }
    .camera-section-card h4 { margin: 0 0 8px; color: #0d3f35; }
    .camera-section-card ul { margin: 0; padding-left: 18px; }
    .camera-section-card li { margin-bottom: 6px; }
    .camera-wide-card { grid-column: 1 / -1; }
    .brief-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .brief-card { border: 1px solid #d9e4e1; background: #ffffff; border-radius: 6px; padding: 10px; min-height: 96px; }
    .brief-card span { display: block; color: #50615e; font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .brief-card strong { display: block; color: #17211f; font-size: 20px; margin: 5px 0; }
    .brief-card p { margin: 6px 0 0; color: #344642; line-height: 1.35; }
    .brief-list { margin: 6px 0 0; padding-left: 18px; color: #243532; }
    .brief-list li { margin: 4px 0; }
    .risk-list li { color: #6d2d00; }
    .cad-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
    .cad-chip { background: #17211f; color: #d7fff6; padding: 10px; border-radius: 6px; font-size: 13px; }
    .cad-chip strong { display: block; color: white; font-size: 18px; margin-top: 4px; }
    .tool-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 10px 0; }
    .tool-row button { margin-top: 0; }
    .cad-toolbar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; margin: 10px 0; }
    .cad-tool { background: #243532; color: #d7fff6; border: 1px solid #45615b; padding: 8px; margin: 0; }
    .cad-tool.active { background: #6d2d76; color: white; }
    .cad-workspace { display: grid; grid-template-columns: 1fr 320px; gap: 12px; margin-top: 10px; }
    .cad-drawing-surface { background: #050808; border: 1px solid #344642; border-radius: 6px; padding: 8px; }
    .cad-drawing-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 2px 10px; }
    .cad-drawing-head h3 { margin: 0; font-size: 17px; }
    .cad-drawing-controls { display: flex; gap: 8px; flex-wrap: wrap; }
    .cad-drawing-controls .group-label { color: #9bb4ae; font-size: 11px; font-weight: 700; padding: 0 4px; align-self: center; }
    .cad-drawing-controls .cad-tool { width: auto; padding: 7px 10px; }
    .cad-drawing-controls .secondary { width: auto; padding: 7px 10px; margin-top: 0; }
    .cad-drawing-canvas { width: 100%; height: 78vh; min-height: 680px; max-height: 84vh; background: #101918; border: 1px solid #2d3f3c; border-radius: 4px; display: block; }
    .cad-right-panel { background: #ffffff; border: 1px solid #cbd8d5; border-radius: 6px; padding: 12px; max-height: 84vh; overflow: auto; }
    .cad-right-panel h3 { margin: 8px 0; }
    .cad-mini-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .cad-script-hidden { display: none; }
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
    @media (max-width: 1100px) {
      .cad-workspace { grid-template-columns: 1fr; }
      .cad-drawing-canvas { min-height: 520px; height: 64vh; }
      .cad-right-panel { max-height: none; }
    }
    @media (max-width: 900px) { main, .grid2, .guidance-card, .brief-grid, .shaft-data-grid, .camera-fit-layout, .camera-feed-grid, .camera-section-grid { grid-template-columns: 1fr; } .metrics { grid-template-columns: 1fr 1fr; } .workspace-head { align-items: flex-start; flex-direction: column; } .tabs { justify-content: flex-start; } }
    @media (max-width: 560px) { header { align-items: flex-start; flex-direction: column; } .metrics, .mini-grid, .primary-actions .secondary-row { grid-template-columns: 1fr; } }
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
      <div class="quick-start">
        <strong>Quick workflow</strong>
        <span>Set the shaft target, run the analysis, then move through Simulation, Fit-to-Build, and CAD when you want more detail.</span>
      </div>
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
      <div class="primary-actions">
        <button id="analyzeBtn" onclick="run(this)">Analyze Shaft</button>
        <div class="secondary-row">
          <button id="exportJsonBtn" class="secondary" onclick="downloadJson(this)">Export JSON</button>
          <button id="exportGcodeBtn" class="secondary" onclick="downloadGcode(this)">Export G-Code</button>
          <button id="exportMfgPackBtn" class="secondary" onclick="downloadManufacturerPack(this)">Export MFG Pack</button>
        </div>
      </div>
      <details class="control-group">
        <summary>Material Library</summary>
        <div class="control-body">
          <div class="tool-row">
            <button id="materialAddBtn" class="secondary">Add Material</button>
            <button id="materialDuplicateBtn" class="secondary">Duplicate Selected</button>
            <button id="materialDeleteBtn" class="secondary">Delete Selected</button>
          </div>
          <div class="tool-row">
            <button id="materialExportBtn" class="secondary">Export Materials</button>
            <button id="materialImportBtn" class="secondary">Import Materials</button>
            <input id="materialFile" type="file" accept="application/json,.json" style="display:none" onchange="loadMaterialsFile(event)">
          </div>
          <table class="editable-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>E1 (GPa)</th>
                <th>E2 (GPa)</th>
                <th>G12 (GPa)</th>
                <th>nu12</th>
                <th>Density</th>
                <th>Cost/kg</th>
                <th>Family</th>
                <th>Design Role</th>
              </tr>
            </thead>
            <tbody id="materialRows"></tbody>
          </table>
        </div>
      </details>
      <details class="control-group">
        <summary>G-Code Settings</summary>
        <div class="control-body">
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
        </div>
      </details>
      <details class="control-group">
        <summary>Debug / Health</summary>
        <div class="control-body">
          <div class="debug-panel">
            <table><tbody id="debugHealth"></tbody></table>
            <label><input id="strictModeToggle" type="checkbox" onchange="setStrictMode(this.checked)"> Strict button mode</label>
            <button id="debugAuditBtn" class="secondary" onclick="runButtonAudit(this)">Run Button Audit</button>
          </div>
        </div>
      </details>
      <details class="control-group">
        <summary>Design History</summary>
        <div class="control-body">
          <div class="history-panel">
            <div class="history-actions">
              <button id="historyUndoBtn" class="secondary">Undo Design</button>
              <button id="historyRedoBtn" class="secondary">Redo Design</button>
            </div>
            <table class="history-table"><tbody id="historyRows"></tbody></table>
          </div>
        </div>
      </details>
      <p><a href="/docs">Developer API tester</a></p>
    </section>
    <section class="workspace">
      <div class="workspace-head">
        <div class="workspace-title">AE ShaftCAD Workbench</div>
        <div class="tabs">
          <button class="tab active" id="simTab" onclick="showView('simulation')">Simulation</button>
          <button class="tab" id="shaftDataTab" onclick="showView('shaftData')">Shaft Data</button>
          <button class="tab" id="cameraTab" onclick="showView('camera')">Camera Fit</button>
          <button class="tab" id="fitTab" onclick="showView('fit')">Fit-to-Build</button>
          <button class="tab" id="drawTab" onclick="showView('cad3d')">CAD Workspace</button>
          <button class="tab" id="flagTab" onclick="showView('flags')">Flag CAD</button>
          <button class="tab" id="tapeTab" onclick="showView('tape')">TapeCAD</button>
          <button class="tab" id="stackTab" onclick="showView('stack')">StackCAD</button>
          <button class="tab" id="cad3dTab" onclick="showView('cad3d')" style="display:none">3D CAD</button>
        </div>
      </div>
      <div id="simulationView" class="view">
        <div class="metrics">
          <div class="card"><span>Overall CPM</span><strong id="cpm">-</strong></div>
          <div class="card"><span>CPM Error</span><strong id="error">-</strong></div>
          <div class="card"><span>Mass</span><strong id="mass">-</strong></div>
          <div class="card"><span>Torsion</span><strong id="torsion">-</strong></div>
        </div>
        <div id="guidanceCard" class="guidance-card">
          <div>
            <span>Next Move</span>
            <strong id="guidanceTitle">Run baseline</strong>
          </div>
          <p id="guidanceText">The default model will run on startup. Adjust CPM, head weight, material, or wrap angle, then analyze again.</p>
        </div>
        <div class="fit-builder-brief">
          <h3>Behavior Intelligence</h3>
          <div class="brief-grid">
            <div class="brief-card">
              <span>Fingerprint</span>
              <strong id="behaviorOverall">Waiting</strong>
              <p id="behaviorShape">Run analysis to read measured shaft behavior.</p>
            </div>
            <div class="brief-card">
              <span>Dynamic Bend</span>
              <strong id="behaviorBend">Waiting</strong>
              <p id="behaviorDynamic">Max bend and load style will appear here.</p>
            </div>
            <div class="brief-card">
              <span>Impact / Flight</span>
              <strong id="behaviorFlight">Waiting</strong>
              <p id="behaviorImpact">Impact deflection and flight window will appear here.</p>
            </div>
            <div class="brief-card">
              <span>Locked-Butt Optimizer</span>
              <strong id="behaviorOptimizer">Waiting</strong>
              <p id="behaviorOptimizeText">Butt CPM stays fixed while mid and tip are tuned.</p>
            </div>
          </div>
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
      <div id="shaftDataView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Source<strong>Auditor Frequency Analyzer</strong></div>
          <div class="cad-chip">Stations<strong>41 / 36 / 31 / 26 / 21 / 16 / 11</strong></div>
          <div class="cad-chip">Range<strong>0-999 CPM</strong></div>
          <div class="cad-chip">Status<strong id="shaftDataState">No profile loaded</strong></div>
        </div>
        <div class="shaft-data-grid">
          <div class="shaft-data-card">
            <h3>Shaft Identity</h3>
            <div class="mini-grid">
              <div><label>Manufacturer</label><input id="shaftDataMaker" type="text" value=""></div>
              <div><label>Model</label><input id="shaftDataModel" type="text" value=""></div>
              <div><label>Flex Label</label><input id="shaftDataFlex" type="text" value=""></div>
              <div><label>Raw Length (in)</label><input id="shaftDataRawLength" type="number" value="46" step="0.25"></div>
              <div><label>Weight (g)</label><input id="shaftDataWeight" type="number" value="65" step="0.1"></div>
              <div><label>Torque (deg)</label><input id="shaftDataTorque" type="number" value="3.5" step="0.1"></div>
              <div><label>Tip OD (in)</label><input id="shaftDataTipOd" type="number" value="0.335" step="0.001"></div>
              <div><label>Butt OD (in)</label><input id="shaftDataButtOd" type="number" value="0.600" step="0.001"></div>
              <div><label>Balance Point (in)</label><input id="shaftDataBalance" type="number" value="0" step="0.1"></div>
              <div><label>Trim State</label><select id="shaftDataTrimState"><option selected>raw uncut</option><option>butt trimmed</option><option>tip trimmed</option><option>installed pull</option></select></div>
            </div>
            <label>Profile Notes</label>
            <textarea id="shaftDataNotes" rows="5" style="width:100%; box-sizing:border-box; margin-top:5px; border:1px solid #b9c8c4; border-radius:6px; padding:10px;"></textarea>
            <div class="fit-actions">
              <button id="shaftDataAnalyzeBtn">Analyze Shaft Data</button>
              <button id="shaftDataImportBtn" class="secondary">Import Current Model</button>
              <button id="shaftDataApplyBtn" class="secondary">Use Butt CPM as Target</button>
            </div>
          </div>
          <div class="shaft-data-card">
            <h3>Auditor Frequency Analyzer Input</h3>
            <table class="auditor-table">
              <thead><tr><th>Station</th><th>Measured CPM</th><th>Section Read</th><th>Range Rule</th></tr></thead>
              <tbody id="shaftDataRows">
                <tr><td>41"</td><td><input id="shaftCpm41" data-station="41" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead41">-</td><td>Butt: 1 flex ~= 10 CPM</td></tr>
                <tr><td>36"</td><td><input id="shaftCpm36" data-station="36" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead36">-</td><td>Butt: 1 flex ~= 10 CPM</td></tr>
                <tr><td>31"</td><td><input id="shaftCpm31" data-station="31" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead31">-</td><td>Mid: 1 flex ~= 25 CPM</td></tr>
                <tr><td>26"</td><td><input id="shaftCpm26" data-station="26" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead26">-</td><td>Mid: 1 flex ~= 25 CPM</td></tr>
                <tr><td>21"</td><td><input id="shaftCpm21" data-station="21" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead21">-</td><td>Mid: 1 flex ~= 25 CPM</td></tr>
                <tr><td>16"</td><td><input id="shaftCpm16" data-station="16" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead16">-</td><td>Tip: 1 flex ~= 40+ CPM</td></tr>
                <tr><td>11"</td><td><input id="shaftCpm11" data-station="11" type="number" min="0" max="999" step="0.1" value=""></td><td id="shaftRead11">-</td><td>Tip: 1 flex ~= 40+ CPM; Auditor display capped at 999</td></tr>
              </tbody>
            </table>
            <div class="auditor-readout">
              <div class="card"><span>Butt Avg</span><strong id="shaftButtAvg">-</strong></div>
              <div class="card"><span>Mid Avg</span><strong id="shaftMidAvg">-</strong></div>
              <div class="card"><span>Tip Avg</span><strong id="shaftTipAvg">-</strong></div>
            </div>
            <h3>Profile Read</h3>
            <ul id="shaftDataFindings"><li>Enter Auditor CPM values, then analyze.</li></ul>
            <h3>Captured Shaft Packet</h3>
            <pre id="shaftDataPacket">No shaft data packet yet.</pre>
          </div>
        </div>
      </div>
      <div id="cameraView" class="view hidden">
        <div class="cad-strip">
          <div class="cad-chip">Workflow<strong>Swing Capture</strong></div>
          <div class="cad-chip">Input<strong>Camera / Manual</strong></div>
          <div class="cad-chip">Output<strong>Shaft Target</strong></div>
          <div class="cad-chip">Status<strong id="cameraFitState">Not started</strong></div>
        </div>
        <div class="camera-fit-layout">
          <div class="camera-stage">
            <h3>Camera-Based Fitting</h3>
            <div class="camera-feed-grid">
              <div class="camera-feed-card">
                <h4>Camera 1 - Face On</h4>
                <video id="cameraVideoFace" playsinline muted></video>
                <canvas id="cameraSampleCanvasFace" width="160" height="90"></canvas>
                <div class="swing-meter"><span id="cameraMotionMeterFace"></span></div>
              </div>
              <div class="camera-feed-card">
                <h4>Camera 2 - Down the Line</h4>
                <video id="cameraVideoDownLine" playsinline muted></video>
                <canvas id="cameraSampleCanvasDownLine" width="160" height="90"></canvas>
                <div class="swing-meter"><span id="cameraMotionMeterDownLine"></span></div>
              </div>
            </div>
            <div class="camera-hud">
              <span>Camera: <strong id="cameraDeviceState">Off</strong></span>
              <span>Capture: <strong id="cameraCaptureState">Idle</strong></span>
              <span>Clean swings: <strong id="cameraSwingCount">0</strong></span>
            </div>
            <div class="camera-controls">
              <button id="cameraStartBtn">Start Cameras</button>
              <button id="cameraCaptureBtn" class="secondary">Capture Swing</button>
              <button id="cameraAiReviewBtn" class="secondary">AI Review Captured Swings</button>
              <button id="cameraStopBtn" class="secondary">Stop Cameras</button>
            </div>
            <div class="camera-note">
              Use Camera 1 face-on for setup, tempo, pressure shift, and shaft load clues. Use Camera 2 down the line for plane, path, hand path, and delivery clues. Manual fields keep the builder usable when camera permission or hardware is unavailable.
            </div>
            <div id="cameraCaptureList" class="camera-capture-list"></div>
          </div>
          <div class="camera-result">
            <details class="interview-panel" open>
              <summary>Pre-Fit Interview</summary>
              <div class="mini-grid">
                <div><label>Fitting Type</label><select id="interviewClubType"><option selected>driver</option><option>iron</option></select></div>
                <div><label>Handedness</label><select id="interviewHandedness"><option selected>right-hand golfer</option><option>left-hand golfer</option></select></div>
                <div><label>Years Playing</label><input id="interviewYearsPlaying" type="number" value="0" step="1"></div>
                <div><label>Current Handicap</label><input id="interviewHandicap" type="text" value=""></div>
                <div><label>Handicap Trend</label><select id="interviewHandicapTrend"><option selected>unknown</option><option>going up</option><option>going down</option><option>stable</option></select></div>
                <div><label>Average Score</label><input id="interviewAverageScore" type="number" value="0" step="1"></div>
                <div><label>Rounds Per Year</label><input id="interviewRoundsPerYear" type="number" value="0" step="1"></div>
                <div><label>Lessons</label><select id="interviewLessons"><option selected>unknown</option><option>yes</option><option>no</option></select></div>
                <div><label>Practice Before Playing</label><select id="interviewPracticeBefore"><option selected>sometimes</option><option>regularly</option><option>never</option></select></div>
                <div><label>Practice Only Sessions</label><select id="interviewPracticeOnly"><option selected>sometimes</option><option>regularly</option><option>never</option></select></div>
                <div><label>Physical Pain</label><select id="interviewPain"><option selected>unknown</option><option>yes</option><option>no</option></select></div>
                <div><label>Other Limitations</label><select id="interviewLimitations"><option selected>unknown</option><option>yes</option><option>no</option></select></div>
                <div><label>Confidence</label><select id="interviewConfidence"><option selected>some confidence</option><option>very confident</option><option>no confidence</option></select></div>
                <div><label>Current Club Weight Feel</label><select id="interviewWeightFeel"><option selected>weight OK</option><option>too heavy</option><option>too light</option><option>don't know</option></select></div>
                <div><label>Immediate Goal</label><select id="interviewImmediateGoal"><option selected>spend reasonable effort to improve</option><option>improve as rapidly as possible</option><option>little time but wants improvement</option><option>find out if current club is right</option></select></div>
                <div><label>Future Handicap Goal</label><select id="interviewFutureGoal"><option selected>don't know</option><option>scratch handicap</option><option>low handicap</option><option>middle handicap</option><option>average golfer</option></select></div>
              </div>
              <label>Poor Shot Tendencies</label>
              <div class="interview-checks" id="interviewTendencies">
                <label><input type="checkbox" value="top it"> Top it</label>
                <label><input type="checkbox" value="slice it right"> Slice it right</label>
                <label><input type="checkbox" value="pull it left"> Pull it left</label>
                <label><input type="checkbox" value="push it right"> Push it right</label>
                <label><input type="checkbox" value="hit very low"> Hit very low</label>
                <label><input type="checkbox" value="very inconsistent"> Very inconsistent</label>
                <label><input type="checkbox" value="sky it"> Sky it</label>
                <label><input type="checkbox" value="straight but unsolid hit"> Straight but unsolid</label>
                <label><input type="checkbox" value="hook it left"> Hook it left</label>
              </div>
              <label>Personal Wants</label>
              <div class="interview-checks" id="interviewWants">
                <label><input type="checkbox" value="hit the ball higher"> Hit higher</label>
                <label><input type="checkbox" value="hit the ball lower"> Hit lower</label>
                <label><input type="checkbox" value="stop slicing"> Stop slicing</label>
                <label><input type="checkbox" value="stop pushing"> Stop pushing</label>
                <label><input type="checkbox" value="stop hooking"> Stop hooking</label>
                <label><input type="checkbox" value="stop pulling"> Stop pulling</label>
                <label><input type="checkbox" value="hit the ball straighter"> Hit straighter</label>
                <label><input type="checkbox" value="hit the ball longer"> Hit longer</label>
                <label><input type="checkbox" value="more consistent"> More consistent</label>
              </div>
              <div class="mini-grid">
                <div><label>Current Brand</label><input id="interviewCurrentBrand" type="text" value=""></div>
                <div><label>Current Model</label><input id="interviewCurrentModel" type="text" value=""></div>
                <div><label>Driver Loft</label><input id="interviewDriverLoft" type="text" value=""></div>
                <div><label>Playing Length</label><input id="interviewPlayingLength" type="text" value=""></div>
                <div><label>Swingweight</label><input id="interviewSwingweight" type="text" value=""></div>
                <div><label>Face Angle</label><select id="interviewFaceAngle"><option selected>unknown</option><option>open/slice</option><option>square</option><option>closed/hook</option></select></div>
                <div><label>Grip Size</label><select id="interviewGripSize"><option selected>standard</option><option>1/64 undersize</option><option>1/64 oversize</option><option>1/32 oversize</option><option>other</option></select></div>
                <div><label>Iron Head Preference</label><select id="interviewIronPreference"><option selected>unknown</option><option>blade style</option><option>cavity back - some game improvement</option><option>cavity back - all game improvement</option></select></div>
              </div>
              <label>Fitter Notes</label><textarea id="interviewNotes" rows="3" style="width:100%; box-sizing:border-box; margin-top:5px; border:1px solid #b9c8c4; border-radius:6px; padding:10px;"></textarea>
            </details>
            <h3>Swing Inputs</h3>
            <div class="mini-grid">
              <div><label>Club Speed (mph)</label><input id="cameraSpeed" type="number" value="105" step="1"></div>
              <div><label>Tempo Seconds</label><input id="cameraTempoSeconds" type="number" value="1.05" step="0.01"></div>
              <div><label>Transition Load</label><input id="cameraTransitionLoad" type="number" value="55" step="1" min="0" max="100"></div>
              <div><label>Release Score</label><input id="cameraReleaseScore" type="number" value="50" step="1" min="0" max="100"></div>
              <div><label>Face Closure Rate</label><input id="cameraClosureRate" type="number" value="50" step="1" min="0" max="100"></div>
              <div><label>Attack Angle (deg)</label><input id="cameraAttackAngle" type="number" value="0" step="0.1"></div>
              <div><label>Face-to-Path (deg)</label><input id="cameraFacePath" type="number" value="0" step="0.1"></div>
              <div><label>Shaft Load Index</label><input id="cameraShaftLoad" type="number" value="55" step="1" min="0" max="100"></div>
              <div><label>Hand Path</label><select id="cameraHandPath"><option selected>neutral</option><option>in-to-out</option><option>out-to-in</option><option>vertical</option><option>shallow</option></select></div>
              <div><label>Impact Pattern</label><select id="cameraImpactPattern"><option selected>unknown</option><option>heel</option><option>all over</option><option>toe</option><option>ideal</option><option>upper toe</option></select></div>
              <div><label>Vertical Impact</label><select id="cameraVerticalImpact"><option selected>unknown</option><option>low</option><option>center</option><option>upper toe</option><option>high</option></select></div>
              <div><label>Head Weight Feel</label><select id="cameraHeadWeightFeel"><option selected>unknown</option><option>light</option><option>good</option><option>heavy</option></select></div>
              <div><label>Current Driver Length</label><input id="cameraCurrentLength" type="number" value="45.5" step="0.25"></div>
              <div><label>Gripped Down Test</label><input id="cameraGrippedDown" type="number" value="0" step="0.25"></div>
              <div><label>Height (in)</label><input id="cameraHeightIn" type="number" value="69" step="0.5"></div>
              <div><label>Wrist to Floor (in)</label><input id="cameraWristFloor" type="number" value="34" step="0.5"></div>
              <div><label>PW Shaft Weight (g)</label><input id="cameraPwWeight" type="number" value="120" step="1"></div>
              <div><label>Added Head Weight (g)</label><input id="cameraAddedHeadWeight" type="number" value="0" step="0.5"></div>
              <div><label>Tempo Control</label><select id="cameraVisualTempo"><option selected>unknown</option><option>controlled</option><option>inconsistent</option><option>slow/insecure</option></select></div>
              <div><label>Rhythm / Float</label><select id="cameraVisualRhythm"><option selected>unknown</option><option>good float</option><option>no float</option><option>loose</option></select></div>
              <div><label>Transition Look</label><select id="cameraVisualTransition"><option selected>unknown</option><option>clean rotation</option><option>jump start</option><option>hips slide</option><option>struggle</option></select></div>
              <div><label>Player Commitment</label><select id="cameraVisualCommitment"><option selected>unknown</option><option>confident</option><option>weak</option><option>overplay</option><option>kill ball</option></select></div>
              <div><label>One-Arm Shoulder Test</label><select id="cameraVisualShoulder"><option selected>unknown</option><option>stable</option><option>drop</option><option>too heavy</option></select></div>
              <div><label>Power Leaks</label><select id="cameraVisualLeaks"><option selected>unknown</option><option>none</option><option>multiple bursts</option><option>sparks</option><option>leaking</option></select></div>
              <div><label>Launch (deg)</label><input id="cameraLaunch" type="number" value="13.5" step="0.1"></div>
              <div><label>Spin (rpm)</label><input id="cameraSpin" type="number" value="2650" step="10"></div>
              <div><label>Carry (yd)</label><input id="cameraCarry" type="number" value="0" step="1"></div>
              <div><label>Total (yd)</label><input id="cameraTotal" type="number" value="0" step="1"></div>
              <div><label>PW Carry (yd)</label><input id="cameraPwCarry" type="number" value="0" step="1"></div>
              <div><label>Impact Sensation</label><select id="cameraImpactSensation"><option selected>unknown</option><option>solid</option><option>easy</option><option>loaded</option><option>comfortable</option><option>harsh</option><option>dead</option><option>boardy</option><option>loose</option><option>whippy</option><option>unstable</option></select></div>
              <div><label>Shot Miss Direction</label><select id="cameraMissDirection"><option selected>unknown</option><option>left</option><option>right</option><option>straight</option><option>hook</option><option>slice</option><option>push right</option><option>pull left</option></select></div>
              <div><label>Shot Quality (0-7)</label><input id="cameraQualityScore" type="number" value="0" step="0.5" min="0" max="7"></div>
              <div><label>Accuracy (0-7)</label><input id="cameraAccuracyScore" type="number" value="0" step="0.5" min="0" max="7"></div>
              <div><label>Shaft Preference (0-9)</label><input id="cameraPreferenceScore" type="number" value="0" step="0.5" min="0" max="9"></div>
              <div><label>Current Flex</label><select id="cameraCurrentFlex"><option selected>unknown</option><option>R</option><option>S</option><option>X</option><option>A</option><option>L</option></select></div>
              <div><label>Current Shaft Weight (g)</label><input id="cameraCurrentShaftWeight" type="number" value="0" step="1"></div>
              <div><label>Current Torque (deg)</label><input id="cameraCurrentTorque" type="number" value="0" step="0.1"></div>
              <div><label>Target Weight (g)</label><input id="cameraWeight" type="number" value="65" step="1"></div>
            </div>
            <div class="fit-actions">
              <button id="cameraManualBtn">Analyze Manual Swing</button>
              <button id="cameraToFitBtn" class="secondary">Send to Fit Builder</button>
              <button id="cameraToCadBtn" class="secondary">Apply to CAD</button>
            </div>
            <h3>AI Shaft Result</h3>
            <table><tbody id="cameraFitResult"></tbody></table>
            <div class="camera-section-grid">
              <div class="camera-section-card camera-wide-card">
                <h4>Fitter Starting Direction</h4>
                <ul id="cameraInterviewList"><li>No interview direction yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>AI Swing Review</h4>
                <ul id="cameraAiReviewList"><li>No AI swing review yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Why This Shaft</h4>
                <ul id="cameraWhyList"><li>No fit explanation yet.</li></ul>
              </div>
              <div class="camera-section-card">
                <h4>Manufacturing Zones</h4>
                <ul id="cameraZoneList"><li>No build zones yet.</li></ul>
              </div>
              <div class="camera-section-card">
                <h4>Proof Before Trust</h4>
                <ul id="cameraProofList"><li>No proof checklist yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>DIY Driver Tune-Up</h4>
                <ul id="cameraTuneupList"><li>No tune-up plan yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Visual Fitting Read</h4>
                <ul id="cameraVisualList"><li>No visual fitting read yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Launch / Rollout Optimizer</h4>
                <ul id="cameraRolloutList"><li>No launch/rollout read yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Static Length / Lie Start</h4>
                <ul id="cameraStaticFitList"><li>No static fit start yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Shaft Sensation / Quality</h4>
                <ul id="cameraSensationList"><li>No sensation/quality read yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Wishon Profile / Torque Guard</h4>
                <ul id="cameraWishonList"><li>No Wishon guard read yet.</li></ul>
              </div>
              <div class="camera-section-card camera-wide-card">
                <h4>Starter Shaft Database Matches</h4>
                <ul id="cameraDatabaseList"><li>No comparable shafts yet.</li></ul>
              </div>
            </div>
            <h3>Capture Packet</h3>
            <pre id="cameraPacket">No swing packet yet.</pre>
          </div>
        </div>
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
        <div class="fit-builder-brief">
          <h3>AI Shaft Builder Brief</h3>
          <div class="brief-grid">
            <div class="brief-card">
              <span>Build Intent</span>
              <strong id="fitIntentTitle">Generate a shaft target</strong>
              <p id="fitIntentText">Enter swing inputs, then generate the shaft target to get a buildable design brief.</p>
            </div>
            <div class="brief-card">
              <span>CAD Recipe</span>
              <strong id="fitRecipeTitle">Waiting</strong>
              <ul id="fitRecipeList" class="brief-list"><li>No CAD recipe yet.</li></ul>
            </div>
            <div class="brief-card">
              <span>Risk Flags</span>
              <strong id="fitRiskTitle">Not checked</strong>
              <ul id="fitRiskList" class="brief-list risk-list"><li>Run Fit-to-Build first.</li></ul>
            </div>
            <div class="brief-card">
              <span>Prototype Test Plan</span>
              <strong id="fitTestTitle">Next validation</strong>
              <ul id="fitTestList" class="brief-list"><li>Build brief will create the first test plan.</li></ul>
            </div>
          </div>
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
        <div class="cad-workspace">
          <div class="cad-drawing-surface">
            <div class="cad-drawing-head">
              <h3>AE ShaftCAD Drafting</h3>
              <div class="cad-drawing-controls">
                <span class="group-label">DRAW</span>
                <button id="cadDraftSelectBtn" class="cad-tool active">Select</button>
                <button id="cadDraftLineBtn" class="cad-tool">Line</button>
                <button id="cadDraftRectBtn" class="cad-tool">Rect</button>
                <button id="cadDraftCircleBtn" class="cad-tool">Circle</button>
                <button id="cadDraftTriangleBtn" class="cad-tool">Triangle</button>
                <span class="group-label">EDIT</span>
                <button id="cadDraftUndoBtn" class="secondary">Undo</button>
                <button id="cadDraftRedoBtn" class="secondary">Redo</button>
                <button id="cadDraftDeleteBtn" class="secondary">Delete</button>
                <button id="cadDraftClearBtn" class="secondary">Clear</button>
              </div>
            </div>
            <canvas class="cad-drawing-canvas" id="cad3dCanvas" width="1400" height="900"
              onmousedown="cad3dMouseDown(event)" onmousemove="cad3dMouseMove(event)"
              onmouseup="cad3dMouseUp()" onmouseleave="cad3dMouseUp()"></canvas>
            <div class="console-panel" id="cadConsole">CAD console ready.</div>
          </div>

          <div class="cad-right-panel">
            <h3>Draft Settings</h3>
            <label>Snap Draft to Grid <input id="cadDraftSnap" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Draft Grid Step (px) <input id="cadDraftSnapStep" type="number" min="1" step="1" value="10" onchange="drawCad3d()"></label>
            <label>Snap Endpoints <input id="cadSnapEndpoint" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Snap Midpoints <input id="cadSnapMidpoint" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Snap Intersections <input id="cadSnapIntersection" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Dark Mode <input id="cadDarkMode" type="checkbox" onchange="drawCad3d()"></label>
            <label>Show Axis <input id="cadShowAxis" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Show Grid <input id="cadShowGrid" type="checkbox" checked onchange="drawCad3d()"></label>
            <label>Smooth Render <input id="cadSmooth" type="checkbox" onchange="drawCad3d()"></label>
            <label>Zoom To Fit <input id="cadZoomFit" type="checkbox" onchange="drawCad3d()"></label>
            <p id="cadDraftStatus">Tool: select</p>

            <h3>Diagnostics</h3>
            <table><tbody id="cadDraftDiagnostics"></tbody></table>

            <h3>Export</h3>
            <div class="export-row">
              <select id="cadExportType">
                <option>JSCAD script</option>
                <option>STEP recipe</option>
                <option>STL recipe</option>
                <option>Mandrel G-code</option>
              </select>
              <button id="cadExportBtn" onclick="downloadCadScript(this)">Export</button>
            </div>
            <div class="cad-mini-actions">
              <button id="cadRefreshBtn" class="secondary" onclick="drawCad3d()">Refresh View</button>
              <button id="cadPresetInspectBtn" class="secondary" onclick="setCadPreset('inspect', this)">Inspect</button>
            </div>
            <div class="cad-mini-actions">
              <button id="cadPresetDarkBtn" class="secondary" onclick="setCadPreset('dark', this)">Dark</button>
              <button id="cadPresetLightBtn" class="secondary" onclick="setCadPreset('light', this)">Light</button>
            </div>

            <h3>Object Inspector</h3>
            <table><tbody id="cadInspector"></tbody></table>
          </div>
        </div>
        <div class="cad-script-hidden">
          <textarea id="cadScript" spellcheck="false"></textarea>
          <table><tbody id="architectureReadout"></tbody></table>
          <div id="architectureObjects"></div>
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
    let cadDraftCursor = null;
    let cadDraftSnapCursor = null;
    let cadDraftSnapKind = 'none';
    // Safety cache so diagnostics/draw paths never crash on missing local scope.
    let sketchIntersections = [];
    let designHistory = [];
    let designFuture = [];
    let materialLibrary = {};
    let activeDrag = null;
    let selectedFlagIndex = null;
    let selectedFlagEdge = null;
    let sketchLines = [];
    let sketchLineStart = null;
    let sketchLinePreview = null;
    let sketchSnapPoint = null;
    let sketchTool = 'select';
    let latestFitProfile = null;
    let fitCadBridge = null;
    let latestShaftDataProfile = null;
    let cameraStream = null;
    let cameraStreams = {face: null, downLine: null};
    let cameraMotionSamples = [];
    let cameraMotionSamplesByView = {face: [], downLine: []};
    let cameraCaptures = [];
    let latestCameraSwingProfile = null;
    let cameraSampleTimer = null;
    let cameraPreviousBrightness = null;
    let cameraPreviousBrightnessByView = {face: null, downLine: null};
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
    const VIEWER_ALLOWED_BUTTON_IDS = new Set(['simTab', 'shaftDataTab', 'fitTab', 'drawTab', 'flagTab', 'tapeTab', 'stackTab', 'cad3dTab']);
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

    function defaultMaterialLibrary() {
      return {
        'Mitsubishi MR70': { name: 'Mitsubishi MR70', e1_pa: 161e9, e2_pa: 8.7e9, g12_pa: 4.5e9, nu12: 0.32, density_kg_m3: 1600.0, cost_per_kg: 95.0, family: 'Carbon fiber', design_role: 'Smooth load, balanced strength/stiffness shaft body', data_quality: 'Engineering estimate' },
        'Toray T1100G': { name: 'Toray T1100G', e1_pa: 215e9, e2_pa: 8.5e9, g12_pa: 4.2e9, nu12: 0.33, density_kg_m3: 1580.0, cost_per_kg: 125.0, family: 'Carbon fiber', design_role: 'High strength, stable premium driver shaft body', data_quality: 'Engineering estimate' },
        'Hexcel IM7': { name: 'Hexcel IM7', e1_pa: 276e9, e2_pa: 14.0e9, g12_pa: 5.2e9, nu12: 0.31, density_kg_m3: 1620.0, cost_per_kg: 140.0, family: 'Carbon fiber', design_role: 'Firm mid/butt reinforcement and stout feel tuning', data_quality: 'Engineering estimate' },
        'Toray T700S': { name: 'Toray T700S', e1_pa: 230e9, e2_pa: 15.0e9, g12_pa: 5.0e9, nu12: 0.30, density_kg_m3: 1600.0, cost_per_kg: 55.0, family: 'Carbon fiber', design_role: 'Lower-cost standard/intermediate modulus baseline', data_quality: 'Engineering estimate' },
        'Toray T800H': { name: 'Toray T800H', e1_pa: 294e9, e2_pa: 13.0e9, g12_pa: 5.0e9, nu12: 0.31, density_kg_m3: 1590.0, cost_per_kg: 85.0, family: 'Carbon fiber', design_role: 'Lightweight premium mid/high modulus shaft body', data_quality: 'Engineering estimate' },
        'Toray M40J': { name: 'Toray M40J', e1_pa: 377e9, e2_pa: 9.0e9, g12_pa: 4.4e9, nu12: 0.32, density_kg_m3: 1600.0, cost_per_kg: 185.0, family: 'High modulus carbon', design_role: 'Butt/mid stiffness without large mass increase', data_quality: 'Engineering estimate' },
        'Toray M46J': { name: 'Toray M46J', e1_pa: 436e9, e2_pa: 8.0e9, g12_pa: 4.0e9, nu12: 0.32, density_kg_m3: 1600.0, cost_per_kg: 240.0, family: 'Ultra high modulus carbon', design_role: 'Very stiff local reinforcement; use carefully in tip', data_quality: 'Engineering estimate' },
        'Mitsubishi Dialead K13C': { name: 'Mitsubishi Dialead K13C', e1_pa: 640e9, e2_pa: 7.0e9, g12_pa: 3.7e9, nu12: 0.32, density_kg_m3: 1700.0, cost_per_kg: 420.0, family: 'Pitch-based high modulus carbon', design_role: 'Specialty ultra-stiff strips, low-strain zone tuning', data_quality: 'Engineering estimate' },
        'S-Glass Damping Layer': { name: 'S-Glass Damping Layer', e1_pa: 86e9, e2_pa: 86e9, g12_pa: 35.0e9, nu12: 0.22, density_kg_m3: 2000.0, cost_per_kg: 22.0, family: 'Glass fiber', design_role: 'Damping, toughness, hoop support, smoother feel', data_quality: 'Engineering estimate' },
        'E-Glass Hoop Layer': { name: 'E-Glass Hoop Layer', e1_pa: 73e9, e2_pa: 73e9, g12_pa: 30.0e9, nu12: 0.22, density_kg_m3: 1950.0, cost_per_kg: 14.0, family: 'Glass fiber', design_role: 'Budget hoop stability and impact tolerance', data_quality: 'Engineering estimate' },
        'Kevlar 49 Aramid': { name: 'Kevlar 49 Aramid', e1_pa: 130e9, e2_pa: 5.5e9, g12_pa: 2.8e9, nu12: 0.34, density_kg_m3: 1440.0, cost_per_kg: 65.0, family: 'Aramid fiber', design_role: 'Vibration damping and impact-tough bias/veil layer', data_quality: 'Engineering estimate' },
        'Basalt Fiber': { name: 'Basalt Fiber', e1_pa: 89e9, e2_pa: 89e9, g12_pa: 32.0e9, nu12: 0.24, density_kg_m3: 2000.0, cost_per_kg: 18.0, family: 'Basalt fiber', design_role: 'Durable damping layer between glass and carbon behavior', data_quality: 'Engineering estimate' },
        'Boron Fiber Prepreg': { name: 'Boron Fiber Prepreg', e1_pa: 400e9, e2_pa: 30.0e9, g12_pa: 14.0e9, nu12: 0.23, density_kg_m3: 2550.0, cost_per_kg: 520.0, family: 'Boron fiber', design_role: 'Heavy, expensive, very stable local reinforcement', data_quality: 'Engineering estimate' },
      };
    }

    function normalizeMaterial(mat, fallbackName) {
      const name = String(mat?.name || fallbackName || 'Custom Material');
      return {
        name,
        e1_pa: Math.max(1, numberOr(mat?.e1_pa, 150e9)),
        e2_pa: Math.max(1, numberOr(mat?.e2_pa, 8e9)),
        g12_pa: Math.max(1, numberOr(mat?.g12_pa, 4e9)),
        nu12: Math.max(0, Math.min(0.49, numberOr(mat?.nu12, 0.32))),
        density_kg_m3: Math.max(1, numberOr(mat?.density_kg_m3, 1600)),
        cost_per_kg: Math.max(0, numberOr(mat?.cost_per_kg, 100)),
        family: String(mat?.family || 'Custom'),
        design_role: String(mat?.design_role || 'General shaft laminate'),
        data_quality: String(mat?.data_quality || 'User supplied'),
      };
    }

    function loadMaterialLibraryFromObject(obj) {
      const next = {};
      Object.entries(obj || {}).forEach(([key, value]) => {
        const m = normalizeMaterial(value, key);
        next[m.name] = m;
      });
      materialLibrary = Object.keys(next).length ? next : defaultMaterialLibrary();
      renderMaterialLibrary();
    }

    function renderMaterialLibrary() {
      const select = document.getElementById('material');
      const prevSelected = select?.value || '';
      const names = Object.keys(materialLibrary);
      if (select) {
        select.innerHTML = names.map(name => `<option value="${name}">${name}</option>`).join('');
        select.value = names.includes(prevSelected) ? prevSelected : names[0];
      }
      const tbody = document.getElementById('materialRows');
      if (!tbody) return;
      tbody.innerHTML = names.map(name => {
        const m = materialLibrary[name];
        return `<tr>
          <td><input type="text" value="${m.name}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'name', this.value)"></td>
          <td><input type="number" step="0.1" value="${(m.e1_pa / 1e9).toFixed(2)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'e1_pa_gpa', this.value)"></td>
          <td><input type="number" step="0.1" value="${(m.e2_pa / 1e9).toFixed(2)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'e2_pa_gpa', this.value)"></td>
          <td><input type="number" step="0.1" value="${(m.g12_pa / 1e9).toFixed(2)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'g12_pa_gpa', this.value)"></td>
          <td><input type="number" step="0.01" value="${m.nu12.toFixed(3)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'nu12', this.value)"></td>
          <td><input type="number" step="1" value="${m.density_kg_m3.toFixed(0)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'density_kg_m3', this.value)"></td>
          <td><input type="number" step="1" value="${m.cost_per_kg.toFixed(0)}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'cost_per_kg', this.value)"></td>
          <td><input type="text" value="${m.family || ''}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'family', this.value)"></td>
          <td><input type="text" value="${m.design_role || ''}" onchange="updateMaterialField('${name.replace(/'/g, "\\'")}', 'design_role', this.value)"></td>
        </tr>`;
      }).join('');
    }

    function selectedMaterialSpec() {
      const name = document.getElementById('material')?.value;
      return materialLibrary[name] || null;
    }

    function updateMaterialField(key, field, value) {
      const current = materialLibrary[key];
      if (!current) return;
      const next = { ...current };
      if (field === 'name') {
        const newName = String(value || '').trim() || current.name;
        delete materialLibrary[key];
        materialLibrary[newName] = { ...next, name: newName };
        renderMaterialLibrary();
        designHistoryCommit(`material renamed: ${newName}`);
        return;
      }
      if (field === 'e1_pa_gpa') next.e1_pa = Math.max(1, numberOr(value, next.e1_pa / 1e9) * 1e9);
      else if (field === 'e2_pa_gpa') next.e2_pa = Math.max(1, numberOr(value, next.e2_pa / 1e9) * 1e9);
      else if (field === 'g12_pa_gpa') next.g12_pa = Math.max(1, numberOr(value, next.g12_pa / 1e9) * 1e9);
      else if (field === 'nu12') next.nu12 = Math.max(0, Math.min(0.49, numberOr(value, next.nu12)));
      else if (field === 'density_kg_m3') next.density_kg_m3 = Math.max(1, numberOr(value, next.density_kg_m3));
      else if (field === 'cost_per_kg') next.cost_per_kg = Math.max(0, numberOr(value, next.cost_per_kg));
      else if (field === 'family') next.family = String(value || '').trim() || 'Custom';
      else if (field === 'design_role') next.design_role = String(value || '').trim() || 'General shaft laminate';
      materialLibrary[key] = next;
      designHistoryCommit(`material updated: ${next.name}`);
    }

    function addMaterial(button) {
      flashButton(button, 'Added');
      let i = 1;
      let name = `Custom Material ${i}`;
      while (materialLibrary[name]) { i++; name = `Custom Material ${i}`; }
      materialLibrary[name] = normalizeMaterial({ name }, name);
      renderMaterialLibrary();
      const select = document.getElementById('material');
      if (select) select.value = name;
      designHistoryCommit('material added');
    }

    function duplicateSelectedMaterial(button) {
      const spec = selectedMaterialSpec();
      if (!spec) return;
      flashButton(button, 'Duplicated');
      let i = 1;
      let name = `${spec.name} Copy ${i}`;
      while (materialLibrary[name]) { i++; name = `${spec.name} Copy ${i}`; }
      materialLibrary[name] = normalizeMaterial({ ...spec, name }, name);
      renderMaterialLibrary();
      const select = document.getElementById('material');
      if (select) select.value = name;
      designHistoryCommit('material duplicated');
    }

    function deleteSelectedMaterial(button) {
      const select = document.getElementById('material');
      const name = select?.value;
      if (!name || !materialLibrary[name]) return;
      if (Object.keys(materialLibrary).length <= 1) {
        setAppStatus('At least one material must remain.', true);
        return;
      }
      flashButton(button, 'Deleted');
      delete materialLibrary[name];
      renderMaterialLibrary();
      designHistoryCommit('material deleted');
    }

    function exportMaterials(button) {
      flashButton(button, 'Exported');
      const blob = new Blob([JSON.stringify(materialLibrary, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'shaftcad-material-library.json';
      a.click();
      URL.revokeObjectURL(url);
    }

    function loadMaterialsFile(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed = JSON.parse(reader.result);
          loadMaterialLibraryFromObject(parsed);
          designHistoryCommit('materials imported');
          setAppStatus('Material library imported.');
        } catch (error) {
          setAppStatus(`Material import failed: ${error.message || String(error)}`, true);
        }
      };
      reader.readAsText(file);
      event.target.value = '';
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
        const eTopH = flagConstraints.find(c => c.id === `flag_${index}_edge_top_horizontal` && c.enabled);
        const eTopV = flagConstraints.find(c => c.id === `flag_${index}_edge_top_vertical` && c.enabled);
        const eBottomH = flagConstraints.find(c => c.id === `flag_${index}_edge_bottom_horizontal` && c.enabled);
        const eBottomV = flagConstraints.find(c => c.id === `flag_${index}_edge_bottom_vertical` && c.enabled);
        const eLeftH = flagConstraints.find(c => c.id === `flag_${index}_edge_left_horizontal` && c.enabled);
        const eRightH = flagConstraints.find(c => c.id === `flag_${index}_edge_right_horizontal` && c.enabled);
        const eLeftV = flagConstraints.find(c => c.id === `flag_${index}_edge_left_vertical` && c.enabled);
        const eRightV = flagConstraints.find(c => c.id === `flag_${index}_edge_right_vertical` && c.enabled);

        if (h && v) errors.push(`${name}: over-constrained (horizontal + vertical both active).`);
        if (h && a) errors.push(`${name}: over-constrained (horizontal conflicts with explicit angle).`);
        if (l && numberOr(l.value, 0) <= 0) errors.push(`${name}: explicit length must be > 0.`);
        if (eTopH && eTopV) errors.push(`${name}: top edge over-constrained (horizontal + vertical).`);
        if (eBottomH && eBottomV) errors.push(`${name}: bottom edge over-constrained (horizontal + vertical).`);
        if (eLeftH && eLeftV) errors.push(`${name}: left edge over-constrained (horizontal + vertical).`);
        if (eRightH && eRightV) errors.push(`${name}: right edge over-constrained (horizontal + vertical).`);
        if (eTopV || eBottomV) errors.push(`${name}: impossible taper (top/bottom edge cannot be vertical in this flag model).`);
        if (eLeftH || eRightH) errors.push(`${name}: impossible taper (left/right edge cannot be horizontal in this flag model).`);
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
      const edge = Number.isInteger(selectedFlagEdge) ? edgeName(selectedFlagEdge) : null;

      function upsertEdge(kind, rawValue) {
        if (!edge) return;
        const id = `flag_${selectedFlagIndex}_edge_${edge}_${kind}`;
        const scope = `${flag.name} ${edge} edge`;
        const existing = flagConstraints.find(c => c.id === id);
        if (existing) {
          existing.value = numberOr(rawValue, existing.value);
          existing.enabled = true;
          existing.scope = scope;
        } else {
          flagConstraints.push({ id, type: `edge_${kind}`, scope, value: numberOr(rawValue, 0), enabled: true });
        }
      }

      if (type === 'horizontal') {
        if (clearFlagConstraintByType(selectedFlagIndex, 'angle')) {
          conflictNote = 'Angle constraint disabled due to horizontal lock.';
        }
        upsertFlagConstraint(selectedFlagIndex, 'horizontal', 1, true, `${flag.name} horizontal`);
        upsertEdge('horizontal', 1);
      } else if (type === 'vertical') {
        upsertFlagConstraint(selectedFlagIndex, 'vertical', 1, true, `${flag.name} vertical`);
        upsertEdge('vertical', 1);
      } else if (type === 'length') {
        if (value <= 0) {
          setAppStatus('Length constraint must be greater than 0.', true);
          return;
        }
        upsertFlagConstraint(selectedFlagIndex, 'length', value, true, `${flag.name} length`);
        upsertEdge('length', value);
      } else if (type === 'angle') {
        const clamped = Math.max(-89, Math.min(89, value));
        if (clearFlagConstraintByType(selectedFlagIndex, 'horizontal')) {
          conflictNote = 'Horizontal constraint disabled due to explicit angle.';
        }
        upsertFlagConstraint(selectedFlagIndex, 'angle', clamped, true, `${flag.name} angle`);
        upsertEdge('angle', clamped);
      }

      if (conflictNote) writeCadConsole(conflictNote);
      applyFlagConstraints();
      renderConstraintTable();
      drawFlags();
      if (edge) {
        setAppStatus(`Applied ${type} constraint to ${flag.name} (${edge} edge).`);
      }
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
        const edgeHorizontal = flagConstraints.find(c => c.id === `flag_${index}_edge_top_horizontal` && c.enabled);
        if (edgeHorizontal) {
          if (Math.abs(next.tip - next.root) > 0.001) adjustments++;
          next.tip = next.root;
        }
        const edgeBottomHorizontal = flagConstraints.find(c => c.id === `flag_${index}_edge_bottom_horizontal` && c.enabled);
        if (edgeBottomHorizontal) {
          if (Math.abs(next.tip - next.root) > 0.001) adjustments++;
          next.tip = next.root;
        }
        const edgeLeftLength = flagConstraints.find(c => c.id === `flag_${index}_edge_left_length` && c.enabled);
        if (edgeLeftLength) {
          const target = Math.max(8, numberOr(edgeLeftLength.value, next.root));
          if (Math.abs(next.root - target) > 0.001) adjustments++;
          next.root = target;
        }
        const edgeRightLength = flagConstraints.find(c => c.id === `flag_${index}_edge_right_length` && c.enabled);
        if (edgeRightLength) {
          const target = Math.max(4, numberOr(edgeRightLength.value, next.tip));
          if (Math.abs(next.tip - target) > 0.001) adjustments++;
          next.tip = target;
        }
        const edgeTopLength = flagConstraints.find(c => c.id === `flag_${index}_edge_top_length` && c.enabled);
        if (edgeTopLength) {
          const target = Math.max(60, numberOr(edgeTopLength.value, next.length));
          if (Math.abs(next.length - target) > 0.001) adjustments++;
          next.length = target;
        }
        const edgeBottomLength = flagConstraints.find(c => c.id === `flag_${index}_edge_bottom_length` && c.enabled);
        if (edgeBottomLength) {
          const target = Math.max(60, numberOr(edgeBottomLength.value, next.length));
          if (Math.abs(next.length - target) > 0.001) adjustments++;
          next.length = target;
        }
        const edgeTopAngle = flagConstraints.find(c => c.id === `flag_${index}_edge_top_angle` && c.enabled);
        if (edgeTopAngle) {
          const target = Math.max(-89, Math.min(89, numberOr(edgeTopAngle.value, next.angle)));
          if (Math.abs(next.angle - target) > 0.001) adjustments++;
          next.angle = target;
        }
        const edgeBottomAngle = flagConstraints.find(c => c.id === `flag_${index}_edge_bottom_angle` && c.enabled);
        if (edgeBottomAngle) {
          const target = Math.max(-89, Math.min(89, numberOr(edgeBottomAngle.value, next.angle)));
          if (Math.abs(next.angle - target) > 0.001) adjustments++;
          next.angle = target;
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
      if (viewName === 'drawing') viewName = 'cad3d';
      document.body.classList.toggle('camera-focus', viewName === 'camera');
      const simulation = document.getElementById('simulationView');
      const shaftDataView = document.getElementById('shaftDataView');
      const cameraView = document.getElementById('cameraView');
      const fitView = document.getElementById('fitView');
      const drawing = document.getElementById('drawingView');
      const flagView = document.getElementById('flagView');
      const tapeView = document.getElementById('tapeView');
      const stackView = document.getElementById('stackView');
      const cad3dView = document.getElementById('cad3dView');
      const simTab = document.getElementById('simTab');
      const shaftDataTab = document.getElementById('shaftDataTab');
      const cameraTab = document.getElementById('cameraTab');
      const fitTab = document.getElementById('fitTab');
      const drawTab = document.getElementById('drawTab');
      const flagTab = document.getElementById('flagTab');
      const tapeTab = document.getElementById('tapeTab');
      const stackTab = document.getElementById('stackTab');
      const cad3dTab = document.getElementById('cad3dTab');
      simulation.classList.toggle('hidden', viewName !== 'simulation');
      shaftDataView.classList.toggle('hidden', viewName !== 'shaftData');
      cameraView.classList.toggle('hidden', viewName !== 'camera');
      fitView.classList.toggle('hidden', viewName !== 'fit');
      drawing.classList.toggle('hidden', viewName !== 'drawing');
      flagView.classList.toggle('hidden', viewName !== 'flags');
      tapeView.classList.toggle('hidden', viewName !== 'tape');
      stackView.classList.toggle('hidden', viewName !== 'stack');
      cad3dView.classList.toggle('hidden', viewName !== 'cad3d');
      simTab.classList.toggle('active', viewName === 'simulation');
      shaftDataTab.classList.toggle('active', viewName === 'shaftData');
      cameraTab.classList.toggle('active', viewName === 'camera');
      fitTab.classList.toggle('active', viewName === 'fit');
      drawTab.classList.toggle('active', viewName === 'cad3d');
      flagTab.classList.toggle('active', viewName === 'flags');
      tapeTab.classList.toggle('active', viewName === 'tape');
      stackTab.classList.toggle('active', viewName === 'stack');
      cad3dTab.classList.toggle('active', false);
      if (viewName === 'shaftData') renderShaftDataProfile();
      if (viewName === 'camera') renderCameraFitResult();
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
      if (tool !== 'line') {
        sketchLineStart = null;
        sketchLinePreview = null;
        sketchSnapPoint = null;
      } else {
        setAppStatus('LINE mode active: click first point.');
      }
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
        const hits = computeSketchIntersections();
        if (hits.length) {
          writeCadConsole(`Sketch intersections: ${hits.length} hit(s).`);
          setAppStatus(`Sketch analyze: ${hits.length} intersection(s) found.`);
        } else {
          writeCadConsole('Sketch intersections: none.');
          setAppStatus('Sketch analyze: no line intersections found.');
        }
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
        const mat = selectedMaterialSpec();
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
        if (mat) {
          params.set('material_e1_pa', String(mat.e1_pa));
          params.set('material_e2_pa', String(mat.e2_pa));
          params.set('material_g12_pa', String(mat.g12_pa));
          params.set('material_nu12', String(mat.nu12));
          params.set('material_density_kg_m3', String(mat.density_kg_m3));
          params.set('material_cost_per_kg', String(mat.cost_per_kg));
        }
        const res = await fetch('/api/analyze?' + params.toString());
        if (!res.ok) throw new Error(`Analyze API failed: ${res.status}`);
        latest = engineeringWithTape(await res.json());
      } catch (error) {
        writeCadConsole(error.message || String(error));
        setAppStatus(`Analysis failed: ${error.message || String(error)}`, true);
        return;
      }

      document.getElementById('cpm').textContent = latest.overall_cpm.toFixed(1);
      document.getElementById('error').textContent = latest.cpm_error.toFixed(1);
      document.getElementById('mass').textContent = latest.mass_g.toFixed(1) + ' g';
      document.getElementById('torsion').textContent = latest.torsion_deflection_deg_15nm.toFixed(1) + ' deg';
      updateGuidanceCard(latest);
      renderBehaviorIntelligence(latest.behavior_intelligence);

      document.getElementById('zones').innerHTML = latest.zone_profile.map(
        z => `<tr><td>${z.station_in}"</td><td>${zoneCpmDisplay(z)}</td></tr>`
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
        ['TapeCAD Torque Reduction', '-' + latest.tape_engineering.estimated_torque_reduction_deg.toFixed(2) + ' deg'],
        ['Behavior Gradient', (latest.behavior_intelligence?.fingerprint?.profile_gradient ?? 0).toFixed(1) + ' CPM'],
        ['Kickpoint', `${(latest.behavior_intelligence?.fingerprint?.kickpoint_percent ?? 0).toFixed(1)}% ${latest.behavior_intelligence?.fingerprint?.kickpoint_label || ''}`]
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

    function updateGuidanceCard(data) {
      const card = document.getElementById('guidanceCard');
      const title = document.getElementById('guidanceTitle');
      const text = document.getElementById('guidanceText');
      if (!card || !title || !text || !data) return;

      const error = Number(data.cpm_error || 0);
      const absError = Math.abs(error);
      card.classList.remove('warn', 'bad');

      if (absError <= 3) {
        title.textContent = 'Target matched';
        text.textContent = `Overall CPM is within ${absError.toFixed(1)} CPM of target. Move to CAD Workspace or export the build data.`;
        return;
      }

      if (absError <= 8) {
        card.classList.add('warn');
      } else {
        card.classList.add('bad');
      }

      if (error > 0) {
        title.textContent = 'Model is too stiff';
        text.textContent = `The shaft is ${absError.toFixed(1)} CPM over target. Try a lower wrap angle, softer material, or less local reinforcement.`;
      } else {
        title.textContent = 'Model is too soft';
        text.textContent = `The shaft is ${absError.toFixed(1)} CPM under target. Try a higher wrap angle, stiffer material, or added tip/mid reinforcement.`;
      }
    }

    function renderBehaviorIntelligence(behavior) {
      if (!behavior) return;
      const fingerprint = behavior.fingerprint || {};
      const dynamic = behavior.dynamic_bend || {};
      const impact = behavior.impact_deflection || {};
      const flight = behavior.ball_flight_prediction || {};
      const speedGain = behavior.speed_gain_prediction || {};
      const optimizer = behavior.locked_butt_optimizer || {};
      const best = optimizer.best || {};

      const overall = document.getElementById('behaviorOverall');
      const shape = document.getElementById('behaviorShape');
      const bend = document.getElementById('behaviorBend');
      const dynamicText = document.getElementById('behaviorDynamic');
      const flightTitle = document.getElementById('behaviorFlight');
      const impactText = document.getElementById('behaviorImpact');
      const optTitle = document.getElementById('behaviorOptimizer');
      const optText = document.getElementById('behaviorOptimizeText');

      if (overall) overall.textContent = `${Number(fingerprint.overall_behavior_cpm || 0).toFixed(1)} CPM`;
      if (shape) {
        shape.textContent = `${fingerprint.overall_behavior || 'measured behavior'}; ${fingerprint.tip_behavior || 'tip behavior pending'}; ${Number(fingerprint.kickpoint_percent || 0).toFixed(1)}% ${fingerprint.kickpoint_label || 'kickpoint'}.`;
      }
      if (bend) bend.textContent = dynamic.max_bend_station || 'n/a';
      if (dynamicText) {
        dynamicText.textContent = `${dynamic.load_style || 'load style pending'} with ${dynamic.release_behavior || 'release pending'}; max bend proxy ${Number(dynamic.max_deflection_proxy || 0).toFixed(3)}.`;
      }
      if (flightTitle) flightTitle.textContent = flight.flight_window || 'n/a';
      if (impactText) {
        impactText.textContent = `${impact.impact_behavior || 'impact pending'}; forward ${Number(impact.forward_deflection_in || 0).toFixed(2)}", droop ${Number(impact.droop_deflection_in || 0).toFixed(2)}", twist ${Number(impact.twist_deflection_deg || 0).toFixed(2)} deg. Predicted carry ${Number(flight.carry_yards || 0).toFixed(0)} yd.`;
      }
      if (optTitle) optTitle.textContent = best.speed_gain ? `+${Number(best.speed_gain.gain_mph || 0).toFixed(2)} mph` : 'Locked';
      if (optText) {
        optText.textContent = `${optimizer.rule || 'Keep butt CPM fixed.'} ${behavior.cpm_range_rule || ''} Best move: mid ${Number(best.mid_delta_cpm || 0).toFixed(0)} CPM, tip ${Number(best.tip_delta_cpm || 0).toFixed(0)} CPM; timing efficiency ${Number(speedGain.timing_efficiency_pct || 0).toFixed(0)}%.`;
      }
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

    function auditorCpmReading(value) {
      return Math.max(0, Math.min(999, Number(value) || 0));
    }

    const CPM_SECTION_RANGES = {
      Butt: {stations: [41, 36], soft: [140, 155], medium: [155, 175], stiff: [175, 190], fullFlex: 10},
      Mid: {stations: [31, 26, 21], soft: [220, 250], medium: [250, 290], stiff: [290, 320], fullFlex: 25},
      Tip: {stations: [16, 11], soft: [680, 740], medium: [740, 820], stiff: [820, 880], fullFlex: 40}
    };

    function cpmSectionForStation(stationIn) {
      const station = Math.round(Number(stationIn || 0));
      return Object.keys(CPM_SECTION_RANGES).find(section => CPM_SECTION_RANGES[section].stations.includes(station)) || 'Unknown';
    }

    function cpmRangeLabel(section, cpm) {
      const reference = CPM_SECTION_RANGES[section];
      if (!reference) return 'unknown';
      for (const label of ['soft', 'medium', 'stiff']) {
        const [low, high] = reference[label];
        if (cpm >= low && cpm <= high) return label;
      }
      return cpm < reference.soft[0] ? 'below soft' : 'above stiff';
    }

    function zoneCpmDisplay(zone) {
      const cpm = auditorCpmReading(zone.cpm);
      const boost = Number(zone.tape_boost || 0);
      const raw = Number(zone.raw_model_cpm ?? zone.raw_cpm ?? cpm);
      const limited = Boolean(zone.analyzer_limited) || raw > 999 || raw < 0;
      const boostText = boost ? ` <small>+${boost.toFixed(1)}</small>` : '';
      const limitText = limited ? ` <small>analyzer cap; model ${raw.toFixed(1)}</small>` : '';
      const section = zone.section || cpmSectionForStation(zone.station_in);
      const sectionReference = CPM_SECTION_RANGES[section] || {};
      const flexDelta = Number(zone.full_flex_delta_cpm || sectionReference.fullFlex || 0);
      const rangeLabel = `${section} ${zone.cpm_class || cpmRangeLabel(section, cpm)}`;
      const fullFlexText = flexDelta ? `1 flex = ${flexDelta.toFixed(0)} CPM` : '';
      const rangeText = [rangeLabel, fullFlexText].filter(Boolean).join('; ');
      return `${cpm.toFixed(1)}${boostText}${limitText}<br><small>${escapeFitText(rangeText)}</small>`;
    }

    function shaftDataNumber(id, fallback = null) {
      const value = Number(document.getElementById(id)?.value);
      return Number.isFinite(value) ? value : fallback;
    }

    function shaftDataStationRows() {
      return [41, 36, 31, 26, 21, 16, 11].map(station => {
        const rawValue = document.getElementById(`shaftCpm${station}`)?.value;
        const hasValue = rawValue !== '' && rawValue != null;
        const cpm = hasValue ? auditorCpmReading(Number(rawValue)) : null;
        const section = cpmSectionForStation(station);
        const reference = CPM_SECTION_RANGES[section] || {};
        return {
          station_in: station,
          cpm,
          section,
          cpm_class: cpm == null ? 'missing' : cpmRangeLabel(section, cpm),
          full_flex_delta_cpm: Number(reference.fullFlex || 0),
          analyzer_range: '0-999',
          analyzer_limited: hasValue && Number(rawValue) > 999
        };
      });
    }

    function avgPresent(values) {
      const present = values.filter(value => Number.isFinite(value));
      return present.length ? present.reduce((sum, value) => sum + value, 0) / present.length : null;
    }

    function renderShaftDataProfile() {
      const profile = latestShaftDataProfile;
      const findingsEl = document.getElementById('shaftDataFindings');
      const packetEl = document.getElementById('shaftDataPacket');
      const stateEl = document.getElementById('shaftDataState');
      const buttAvgEl = document.getElementById('shaftButtAvg');
      const midAvgEl = document.getElementById('shaftMidAvg');
      const tipAvgEl = document.getElementById('shaftTipAvg');
      [41, 36, 31, 26, 21, 16, 11].forEach(station => {
        const row = profile?.stations?.find(item => item.station_in === station);
        const readEl = document.getElementById(`shaftRead${station}`);
        if (readEl) readEl.textContent = row && row.cpm != null ? `${row.section} ${row.cpm_class} (${row.cpm.toFixed(1)} CPM)` : '-';
      });
      if (!profile) {
        if (findingsEl) findingsEl.innerHTML = '<li>Enter Auditor CPM values, then analyze.</li>';
        if (packetEl) packetEl.textContent = 'No shaft data packet yet.';
        if (stateEl) stateEl.textContent = 'No profile loaded';
        if (buttAvgEl) buttAvgEl.textContent = '-';
        if (midAvgEl) midAvgEl.textContent = '-';
        if (tipAvgEl) tipAvgEl.textContent = '-';
        return;
      }
      if (stateEl) stateEl.textContent = profile.complete ? 'Profile captured' : 'Incomplete profile';
      if (buttAvgEl) buttAvgEl.textContent = profile.section_averages.butt == null ? '-' : `${profile.section_averages.butt.toFixed(1)} CPM`;
      if (midAvgEl) midAvgEl.textContent = profile.section_averages.mid == null ? '-' : `${profile.section_averages.mid.toFixed(1)} CPM`;
      if (tipAvgEl) tipAvgEl.textContent = profile.section_averages.tip == null ? '-' : `${profile.section_averages.tip.toFixed(1)} CPM`;
      if (findingsEl) findingsEl.innerHTML = profile.findings.map(item => `<li>${escapeFitText(item)}</li>`).join('');
      if (packetEl) packetEl.textContent = JSON.stringify(profile, null, 2);
    }

    function analyzeShaftData(button) {
      flashButton(button, 'Analyzed');
      const stations = shaftDataStationRows();
      const missing = stations.filter(row => row.cpm == null).map(row => `${row.station_in}"`);
      const buttAvg = avgPresent(stations.filter(row => row.section === 'Butt').map(row => row.cpm));
      const midAvg = avgPresent(stations.filter(row => row.section === 'Mid').map(row => row.cpm));
      const tipAvg = avgPresent(stations.filter(row => row.section === 'Tip').map(row => row.cpm));
      const first = stations.find(row => row.cpm != null);
      const last = [...stations].reverse().find(row => row.cpm != null);
      const gradient = first && last ? last.cpm - first.cpm : null;
      const findings = [];
      if (missing.length) findings.push(`Missing Auditor readings at ${missing.join(', ')}.`);
      findings.push('Auditor range is 0-999 CPM; values above 999 should be treated as capped instrument readings, not real CPM values.');
      if (buttAvg != null) findings.push(`Butt section average is ${buttAvg.toFixed(1)} CPM; butt flex deltas are roughly 10 CPM per full flex.`);
      if (midAvg != null) findings.push(`Mid section average is ${midAvg.toFixed(1)} CPM; mid flex deltas are roughly 25 CPM per full flex.`);
      if (tipAvg != null) findings.push(`Tip section average is ${tipAvg.toFixed(1)} CPM; tip flex deltas are roughly 40+ CPM per full flex.`);
      if (gradient != null) findings.push(`Measured profile gradient from ${first.station_in}" to ${last.station_in}" is ${gradient.toFixed(1)} CPM.`);
      const capped = stations.filter(row => row.analyzer_limited);
      if (capped.length) findings.push(`Capped stations: ${capped.map(row => `${row.station_in}"`).join(', ')}. Recheck entry because the Auditor should display 0-999 only.`);
      const usable = stations.filter(row => row.cpm != null).length >= 4;
      if (usable && !missing.length) findings.push('Complete 7-station profile is ready for comparison, fitting, and shaft database storage.');
      else if (usable) findings.push('Partial profile is usable for direction, but not enough to lock a design.');
      else findings.push('Not enough measured data yet. Enter at least butt, mid, and tip readings.');

      latestShaftDataProfile = {
        captured_at: new Date().toISOString(),
        source: 'Auditor frequency analyzer',
        identity: {
          manufacturer: document.getElementById('shaftDataMaker')?.value || '',
          model: document.getElementById('shaftDataModel')?.value || '',
          flex_label: document.getElementById('shaftDataFlex')?.value || '',
          raw_length_in: shaftDataNumber('shaftDataRawLength', null),
          weight_g: shaftDataNumber('shaftDataWeight', null),
          torque_deg: shaftDataNumber('shaftDataTorque', null),
          tip_od_in: shaftDataNumber('shaftDataTipOd', null),
          butt_od_in: shaftDataNumber('shaftDataButtOd', null),
          balance_point_in: shaftDataNumber('shaftDataBalance', null),
          trim_state: document.getElementById('shaftDataTrimState')?.value || '',
          notes: document.getElementById('shaftDataNotes')?.value || ''
        },
        stations,
        section_averages: {butt: buttAvg, mid: midAvg, tip: tipAvg},
        profile_gradient_cpm: gradient,
        complete: !missing.length,
        findings
      };
      renderShaftDataProfile();
      setAppStatus('Shaft data profile analyzed.');
      return latestShaftDataProfile;
    }

    async function importCurrentModelToShaftData(button) {
      if (!latest) await run();
      flashButton(button, 'Imported');
      const profile = latest?.zone_profile || [];
      profile.forEach(zone => {
        const station = Math.round(Number(zone.station_in || 0));
        const input = document.getElementById(`shaftCpm${station}`);
        if (input) input.value = auditorCpmReading(Number(zone.cpm || 0)).toFixed(1);
      });
      if (latest?.overall_cpm && document.getElementById('shaftCpm41')) {
        document.getElementById('shaftCpm41').value = auditorCpmReading(latest.overall_cpm).toFixed(1);
      }
      analyzeShaftData();
      setAppStatus('Current simulated CPM profile imported into Shaft Data.');
    }

    function applyShaftDataTarget(button) {
      if (!latestShaftDataProfile) analyzeShaftData();
      const butt = latestShaftDataProfile?.section_averages?.butt;
      if (butt == null) {
        setAppStatus('Enter butt section CPM before applying a target.', true);
        return;
      }
      flashButton(button, 'Applied');
      document.getElementById('target').value = butt.toFixed(1);
      run();
      setAppStatus(`Target CPM set from measured butt average: ${butt.toFixed(1)}.`);
    }

    function fitMultiplier(value, mapping) {
      return mapping[value] || 0;
    }

    function escapeFitText(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[char]));
    }

    function cameraNumber(id, fallback) {
      return Number(document.getElementById(id)?.value || fallback);
    }

    function cameraText(id) {
      return document.getElementById(id)?.value || '';
    }

    function checkedValues(containerId) {
      return Array.from(document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`)).map(input => input.value);
    }

    function fittingInterviewPayload() {
      return {
        club_type: document.getElementById('interviewClubType')?.value || 'driver',
        handedness: document.getElementById('interviewHandedness')?.value || 'right-hand golfer',
        years_playing: cameraNumber('interviewYearsPlaying', 0),
        current_handicap: cameraText('interviewHandicap'),
        handicap_trend: document.getElementById('interviewHandicapTrend')?.value || 'unknown',
        average_score: cameraNumber('interviewAverageScore', 0),
        rounds_per_year: cameraNumber('interviewRoundsPerYear', 0),
        lessons: document.getElementById('interviewLessons')?.value || 'unknown',
        practice_before_playing: document.getElementById('interviewPracticeBefore')?.value || 'sometimes',
        practice_only_sessions: document.getElementById('interviewPracticeOnly')?.value || 'sometimes',
        physical_pain: document.getElementById('interviewPain')?.value || 'unknown',
        physical_limitations: document.getElementById('interviewLimitations')?.value || 'unknown',
        confidence: document.getElementById('interviewConfidence')?.value || 'some confidence',
        club_weight_feel: document.getElementById('interviewWeightFeel')?.value || 'weight OK',
        immediate_goal: document.getElementById('interviewImmediateGoal')?.value || 'spend reasonable effort to improve',
        future_handicap_goal: document.getElementById('interviewFutureGoal')?.value || "don't know",
        poor_shot_tendencies: checkedValues('interviewTendencies'),
        personal_wants: checkedValues('interviewWants'),
        current_brand: cameraText('interviewCurrentBrand'),
        current_model: cameraText('interviewCurrentModel'),
        driver_loft: cameraText('interviewDriverLoft'),
        playing_length: cameraText('interviewPlayingLength'),
        swingweight: cameraText('interviewSwingweight'),
        face_angle: document.getElementById('interviewFaceAngle')?.value || 'unknown',
        grip_size: document.getElementById('interviewGripSize')?.value || 'standard',
        iron_head_preference: document.getElementById('interviewIronPreference')?.value || 'unknown',
        fitter_notes: cameraText('interviewNotes')
      };
    }

    function setCameraState(message, isBad) {
      const state = document.getElementById('cameraFitState');
      if (state) state.textContent = message;
      setAppStatus(`Camera Fit: ${message}`, Boolean(isBad));
    }

    function updateCameraHud(device, capture) {
      const deviceEl = document.getElementById('cameraDeviceState');
      const captureEl = document.getElementById('cameraCaptureState');
      const countEl = document.getElementById('cameraSwingCount');
      if (deviceEl && device) deviceEl.textContent = device;
      if (captureEl && capture) captureEl.textContent = capture;
      if (countEl) countEl.textContent = String(cameraCaptures.length);
    }

    function cameraManualPayload(source, motionScore, motionQuality) {
      return {
        source,
        speed_mph: cameraNumber('cameraSpeed', 105),
        tempo_seconds: cameraNumber('cameraTempoSeconds', 1.05),
        transition_load: cameraNumber('cameraTransitionLoad', 55),
        release_score: cameraNumber('cameraReleaseScore', 50),
        face_closure_rate: cameraNumber('cameraClosureRate', 50),
        attack_angle_deg: cameraNumber('cameraAttackAngle', 0),
        face_to_path_deg: cameraNumber('cameraFacePath', 0),
        shaft_load_index: cameraNumber('cameraShaftLoad', cameraNumber('cameraTransitionLoad', 55)),
        hand_path: document.getElementById('cameraHandPath')?.value || 'neutral',
        impact_pattern: document.getElementById('cameraImpactPattern')?.value || 'unknown',
        vertical_impact: document.getElementById('cameraVerticalImpact')?.value || 'unknown',
        head_weight_feel: document.getElementById('cameraHeadWeightFeel')?.value || 'unknown',
        current_length_in: cameraNumber('cameraCurrentLength', 45.5),
        gripped_down_in: cameraNumber('cameraGrippedDown', 0),
        height_in: cameraNumber('cameraHeightIn', 69),
        wrist_to_floor_in: cameraNumber('cameraWristFloor', 34),
        pw_shaft_weight_g: cameraNumber('cameraPwWeight', 120),
        added_head_weight_g: cameraNumber('cameraAddedHeadWeight', 0),
        visual_tempo_control: document.getElementById('cameraVisualTempo')?.value || 'unknown',
        visual_rhythm_float: document.getElementById('cameraVisualRhythm')?.value || 'unknown',
        visual_transition_move: document.getElementById('cameraVisualTransition')?.value || 'unknown',
        visual_commitment: document.getElementById('cameraVisualCommitment')?.value || 'unknown',
        visual_one_arm_shoulder: document.getElementById('cameraVisualShoulder')?.value || 'unknown',
        visual_power_leaks: document.getElementById('cameraVisualLeaks')?.value || 'unknown',
        launch_deg: cameraNumber('cameraLaunch', 13.5),
        spin_rpm: cameraNumber('cameraSpin', 2650),
        carry_yards: cameraNumber('cameraCarry', 0),
        total_yards: cameraNumber('cameraTotal', 0),
        pw_carry_yards: cameraNumber('cameraPwCarry', 0),
        impact_sensation: document.getElementById('cameraImpactSensation')?.value || 'unknown',
        shot_miss_direction: document.getElementById('cameraMissDirection')?.value || 'unknown',
        shot_quality_score: cameraNumber('cameraQualityScore', 0),
        shot_accuracy_score: cameraNumber('cameraAccuracyScore', 0),
        shaft_preference_score: cameraNumber('cameraPreferenceScore', 0),
        current_flex_label: document.getElementById('cameraCurrentFlex')?.value || 'unknown',
        current_shaft_weight_g: cameraNumber('cameraCurrentShaftWeight', 0),
        current_torque_deg: cameraNumber('cameraCurrentTorque', 0),
        fitting_interview: fittingInterviewPayload(),
        camera_views: {
          face_on: {
            label: 'Camera 1 - Face On',
            role: 'setup, body motion, tempo, pressure shift, release timing, and face-on shaft load clues',
            samples: cameraMotionSamplesByView.face.slice(-40)
          },
          down_the_line: {
            label: 'Camera 2 - Down the Line',
            role: 'swing plane, hand path, shaft plane, delivery path, and down-line club motion clues',
            samples: cameraMotionSamplesByView.downLine.slice(-40)
          }
        },
        weight_g: cameraNumber('cameraWeight', 65),
        motion_score: motionScore ?? 50,
        motion_quality: motionQuality ?? 70
      };
    }

    function deriveCameraPayloadFromSamples() {
      const faceSamples = cameraMotionSamplesByView.face.slice();
      const downLineSamples = cameraMotionSamplesByView.downLine.slice();
      const samples = [...faceSamples, ...downLineSamples];
      cameraMotionSamples = samples.slice();
      const avgMotion = samples.length ? samples.reduce((sum, value) => sum + value, 0) / samples.length : 0;
      const peakMotion = samples.length ? Math.max(...samples) : 0;
      const motionScore = Math.max(0, Math.min(100, Math.round(avgMotion * 2.4 + peakMotion * 1.2)));
      const motionQuality = Math.max(35, Math.min(96, Math.round(88 - Math.abs(samples.length - 30) * 1.4 + Math.min(peakMotion, 18))));
      const payload = cameraManualPayload('browser-camera', motionScore, motionQuality);
      payload.transition_load = Math.max(payload.transition_load, Math.min(100, Math.round(42 + peakMotion * 1.9)));
      payload.shaft_load_index = Math.max(payload.shaft_load_index, Math.min(100, Math.round(45 + peakMotion * 2.1)));
      payload.tempo_seconds = Math.max(0.65, Math.min(1.45, payload.tempo_seconds - Math.min(0.22, avgMotion / 260)));
      payload.camera_review_seed = {
        face_on_samples: faceSamples.length,
        down_line_samples: downLineSamples.length,
        face_on_peak_motion: faceSamples.length ? Math.max(...faceSamples) : 0,
        down_line_peak_motion: downLineSamples.length ? Math.max(...downLineSamples) : 0,
        review_note: 'Use face-on for setup/load/tempo and down-line for path/plane/delivery.'
      };
      return payload;
    }

    function cameraReferenceMatches(payload, inputs) {
      const references = [
        {name: 'Smooth loader mid-launch reference', speed: [88, 102], tempo: 'Smooth', transition: 'Smooth', profile: 'active handle, stable mid, responsive tip'},
        {name: 'Neutral tour-weight reference', speed: [98, 110], tempo: 'Medium', transition: 'Medium', profile: 'balanced butt/mid/tip with neutral launch'},
        {name: 'Hard transition anti-left reference', speed: [106, 118], tempo: 'Aggressive', transition: 'Hard', profile: 'firm handle, reinforced mid, tip/torque control'},
        {name: 'High-speed low-spin reference', speed: [116, 130], tempo: 'Aggressive', transition: 'Hard', profile: 'localized high-modulus support with guarded feel'}
      ];
      return references.map(item => {
        let score = 0;
        if (payload.speed_mph >= item.speed[0] && payload.speed_mph <= item.speed[1]) score += 3;
        if (inputs.tempo === item.tempo) score += 1;
        if (inputs.transition === item.transition) score += 2;
        if (inputs.miss === 'Left' && item.name.includes('anti-left')) score += 2;
        if (inputs.miss === 'High spin' && item.name.includes('low-spin')) score += 2;
        return {...item, match_score: score};
      }).filter(item => item.match_score > 0).sort((a, b) => b.match_score - a.match_score).slice(0, 3);
    }

    function enrichCameraFitProfile(profile, payload, inputs) {
      const diyTuneup = buildDiyDriverTuneup(payload);
      const visualFit = buildVisualFittingRead(payload);
      const rolloutRead = buildLaunchRolloutRead(payload);
      const staticFit = buildStaticLengthLieFit(payload);
      const sensationQuality = buildShaftSensationQuality(payload);
      const wishonGuard = buildWishonProfileGuard(payload);
      const interviewRead = buildFittingInterviewRead(payload);
      const why = [
        `${Number(payload.speed_mph).toFixed(0)} mph speed sets the base stiffness and weight class.`,
        `${inputs.tempo} tempo with ${inputs.transition} transition drives the handle/mid stability target.`,
        `${inputs.release} release timing and ${Number(payload.face_closure_rate).toFixed(0)} face-closure score shape tip recovery.`,
        `${Number(payload.launch_deg).toFixed(1)} deg launch, ${Number(payload.spin_rpm).toFixed(0)} rpm spin, and ${Number(payload.attack_angle_deg).toFixed(1)} deg attack angle set the launch/spin bias.`,
        `${payload.hand_path} hand path and ${Number(payload.face_to_path_deg).toFixed(1)} deg face-to-path are treated as directional fit clues, not final proof.`
      ];
      const zones = [
        {
          zone: 'Butt / handle',
          design_goal: 'Preserve load feel without letting the handle collapse.',
          layup_note: 'Use axial 0 degree stability with light hoop support; increase butt flag width when load index exceeds 72.',
          trigger: `${inputs.transition} transition, load index ${Number(payload.shaft_load_index).toFixed(0)}`
        },
        {
          zone: 'Mid / recovery',
          design_goal: 'Control kick timing and keep face delivery predictable.',
          layup_note: `Bias pair near +/-${profile.wrap_angle_deg.toFixed(0)} degrees; add braid/tape/braid support for hard transitions.`,
          trigger: `${inputs.release} release timing`
        },
        {
          zone: 'Tip / launch',
          design_goal: profile.tip_strategy,
          layup_note: 'Use local tip flag changes first; avoid overbuilding the whole shaft to solve a tip-only problem.',
          trigger: `${profile.launch_bias}, ${inputs.miss} miss`
        },
        {
          zone: 'Torque / feel shell',
          design_goal: `Hold roughly ${profile.torque_target_deg.toFixed(2)} deg torque while protecting feel.`,
          layup_note: 'Use hoop/helix/braid as a shell variable; validate torque before adding stiffer carbon everywhere.',
          trigger: `face closure ${Number(payload.face_closure_rate).toFixed(0)}, tempo ${inputs.tempo}`
        }
      ];
      profile.why_this_fit = why;
      profile.manufacturing_zones = zones;
      profile.proof_requirements = [
        'Capture at least three clean swings before trusting the camera profile.',
        'Capture face impact marks with dry-erase marker or foot spray before changing length or CAD.',
        'Compare the generated 7-zone CPM target against the measured shaft after build.',
        'Validate launch, spin, start line, and face delivery on a launch monitor.',
        'Change one build variable at a time so the database learns what actually moved performance.',
        'Store prototype results in the shaft database before declaring the recipe proven.'
      ];
      profile.shaft_database_matches = cameraReferenceMatches(payload, inputs);
      profile.diy_driver_tuneup = diyTuneup;
      profile.visual_fitting = visualFit;
      profile.launch_rollout_optimizer = rolloutRead;
      profile.static_length_lie = staticFit;
      profile.shaft_sensation_quality = sensationQuality;
      profile.wishon_profile_guard = wishonGuard;
      profile.fitting_interview = interviewRead;
      return profile;
    }

    function buildFittingInterviewRead(payload) {
      const interview = payload.fitting_interview || {};
      const clubType = String(interview.club_type || 'driver').toLowerCase();
      const tendencies = (interview.poor_shot_tendencies || []).map(item => String(item).toLowerCase());
      const wants = (interview.personal_wants || []).map(item => String(item).toLowerCase());
      const pain = String(interview.physical_pain || 'unknown').toLowerCase();
      const limitations = String(interview.physical_limitations || 'unknown').toLowerCase();
      const confidence = String(interview.confidence || 'unknown').toLowerCase();
      const weightFeel = String(interview.club_weight_feel || 'unknown').toLowerCase();
      const goal = String(interview.immediate_goal || 'unknown').toLowerCase();
      const handicapTrend = String(interview.handicap_trend || 'unknown').toLowerCase();
      const startPoints = [];
      const watchItems = [];
      const fitterQuestions = [];
      if (pain === 'yes' || limitations === 'yes') {
        startPoints.push('Start with comfort and repeatability before chasing speed.');
        watchItems.push('Do not force heavy, long, or harsh builds until pain/limitation notes are understood.');
        fitterQuestions.push('Where does the swing hurt, and does it change through the round?');
      }
      if (tendencies.includes('slice it right') || wants.includes('stop slicing') || tendencies.includes('push it right') || wants.includes('stop pushing')) {
        startPoints.push('Begin with face delivery, strike location, playing length, and release feel.');
        watchItems.push('Right-miss pattern: avoid making the shaft so stiff/boardy the player cannot square it.');
      }
      if (tendencies.includes('hook it left') || wants.includes('stop hooking') || tendencies.includes('pull it left') || wants.includes('stop pulling')) {
        startPoints.push('Begin with torque/profile stability, face angle, and left-bias control.');
        watchItems.push('Left-miss pattern: check high-torque/light/soft combinations before adding loft or length.');
      }
      if (tendencies.includes('very inconsistent') || tendencies.includes('straight but unsolid hit') || wants.includes('more consistent') || wants.includes('drive the ball with more consistency')) {
        startPoints.push('Begin with center-contact controls: length, total weight, swingweight, and impact pattern.');
      }
      if (tendencies.includes('hit very low') || wants.includes('hit the ball higher')) {
        startPoints.push('Check launch window, dynamic loft, shaft tip response, and loft before changing flex label.');
      }
      if (tendencies.includes('sky it') || wants.includes('hit the ball lower')) {
        startPoints.push('Check impact height, attack angle, tee/ball position, and spin before stiffening everything.');
      }
      if (wants.includes('hit the ball longer')) {
        startPoints.push('Distance goal: protect contact quality first, then test speed, launch, and spin gains.');
      }
      if (confidence === 'no confidence') watchItems.push('Low confidence: use smaller test changes and show the player clear cause/effect.');
      if (weightFeel === 'too heavy') startPoints.push('Current club feels heavy: test lower total weight or shorter length before adding head weight.');
      if (weightFeel === 'too light') startPoints.push('Current club feels light: test more head/shaft weight and watch face control.');
      if (goal.includes('find out')) fitterQuestions.push('Is the goal validation of the current club, a rebuild, or a new shaft design?');
      if (handicapTrend === 'going up') watchItems.push('Handicap trending up: prioritize misses, confidence, and playable dispersion over max-distance claims.');
      startPoints.push(clubType === 'iron'
        ? 'Iron path: include static length/lie, dynamic lie marks, shaft weight, and contact pattern early.'
        : 'Driver path: include loft, face angle, playing length, strike height, and carry/roll proof early.');
      return {
        club_type: clubType,
        start_points: startPoints.length ? startPoints : ['Start with baseline interview, current specs, impact marks, and three clean swings.'],
        watch_items: watchItems,
        fitter_questions: fitterQuestions,
        source: 'Maltby-style driver/iron personal fitting interview',
        captured: interview
      };
    }

    function buildWishonProfileGuard(payload) {
      const speed = Number(payload.speed_mph || 105);
      const transition = String(payload.transition || payload.visual_transition_move || 'unknown').toLowerCase();
      const tempo = String(payload.tempo || payload.visual_tempo_control || 'unknown').toLowerCase();
      const release = String(payload.release || 'Mid').toLowerCase();
      const miss = String(payload.shot_miss_direction || 'unknown').toLowerCase();
      const sensation = String(payload.impact_sensation || 'unknown').toLowerCase();
      const torque = Number(payload.current_torque_deg || 0);
      const aggressive = transition.includes('hard') || transition.includes('jump') || tempo.includes('aggressive') || speed >= 112;
      const findings = [
        'Use measured 7-point bend profile data before trusting R/S/X flex labels.',
        'Butt, mid, and tip sections should be treated separately because different swing phases load different shaft sections.',
        'Torque is mainly an accuracy/feel guardrail; weight, overall stiffness, and bend profile usually matter more.'
      ];
      const profileRequirements = [
        'Store CPM/frequency at seven stations and classify butt, mid, and tip stiffness independently.',
        'Compare profile shape against known shafts instead of comparing only butt CPM.',
        'When a target shaft is known, search for profile-match candidates by percentage, weight, torque, and availability.'
      ];
      const recommendations = [
        aggressive
          ? 'Strong transition / fast tempo: prioritize profile stability and consider the firmer trim family before chasing a stiffer printed flex.'
          : 'Smooth or moderate move: keep softer/profile-active candidates alive and let impact quality decide.'
      ];
      const torqueNotes = [];
      if (torque >= 5 && aggressive) {
        torqueNotes.push('High torque with aggressive transition can allow the head to over-rotate and produce left/hook bias.');
      } else if (torque > 0 && torque <= 3 && ['harsh', 'dead', 'boardy'].includes(sensation)) {
        torqueNotes.push('Very low torque can feel less solid/comfortable for some players; do not over-tighten torque if feel suffers.');
      } else {
        torqueNotes.push('Treat torque as a fine-tuning variable after length, weight, profile, and strike pattern are under control.');
      }
      if (['left', 'hook', 'pull left'].includes(miss) && aggressive) {
        recommendations.push('Left miss with aggressive transition: add torque/profile stability locally before changing the whole shaft.');
      }
      if (['right', 'slice', 'push right'].includes(miss) && ['harsh', 'dead', 'boardy'].includes(sensation)) {
        recommendations.push('Right miss with harsh/stiff feedback: test more active release feel before reducing loft or adding tip stiffness.');
      }
      const trimmingNotes = [
        'Driver wood trim starts at 0 inch tip trim; butt trim to final length after fitting.',
        'Increasing tip trim by 0.5 inch should mostly feel slightly firmer, not radically change launch/spin.',
        'Increasing tip trim by 1 inch is a stronger stiffness change; launch/spin effects are still modest and show most for later-release players.',
        'Decreasing tip trim softens feel; do not use trimming as a substitute for selecting the correct bend profile.'
      ];
      if (release === 'late') trimmingNotes.push('Late release player: tip-trim changes are more likely to show in launch/spin, so validate carefully.');
      return {
        findings,
        profile_requirements: profileRequirements,
        recommendations,
        torque_notes: torqueNotes,
        trimming_notes: trimmingNotes,
        source_anchor: 'Tom Wishon Shaft Selector / trimming / torque guidance: bend profile beats flex label; torque is secondary to weight, stiffness, and profile.',
        boundary: 'Wishon guardrails are fitting logic, not a manufacturer-specific prescription. Validate with measured profile, impact marks, and player testing.'
      };
    }

    function buildShaftSensationQuality(payload) {
      const sensation = String(payload.impact_sensation || 'unknown').toLowerCase();
      const miss = String(payload.shot_miss_direction || 'unknown').toLowerCase();
      const quality = Number(payload.shot_quality_score || 0);
      const preference = Number(payload.shaft_preference_score || 0);
      const flex = String(payload.current_flex_label || 'unknown').toLowerCase();
      const weight = Number(payload.current_shaft_weight_g || 0);
      const findings = [
        'Do not select shaft flex from club speed alone.',
        'Use 7-zone shaft profile and subjective impact sensation, not only butt frequency or printed flex label.'
      ];
      const recommendations = [];
      const designBias = [];
      if (Number(payload.speed_mph || 0) >= 112) {
        findings.push('High club speed does not automatically mean the stiffest shaft wins.');
        designBias.push('Keep softer/profile-active candidates in the test set even for high-speed players.');
      }
      if (['harsh', 'dead', 'boardy', 'hard'].includes(sensation)) {
        recommendations.push('Test a softer or more active profile before adding stiffness; harsh feedback can make the player fight the shaft.');
        designBias.push('Soften feedback in the butt/tip sections or add damping while maintaining enough weight for control.');
      } else if (['loose', 'whippy', 'unstable'].includes(sensation)) {
        recommendations.push('Test more stability through weight, torque, or mid/tip control before assuming the player needs a stiffer label.');
        designBias.push('Add stability locally; avoid making the entire shaft boardy.');
      } else if (['solid', 'easy', 'loaded', 'comfortable'].includes(sensation)) {
        recommendations.push('Protect this feel while tuning launch, spin, and dispersion.');
        designBias.push('Preserve the current load feedback and adjust only the section causing the measured miss.');
      } else {
        recommendations.push('Capture pairwise preference after two shafts; subjective feel should become data, not a guess.');
      }
      if (['left', 'hook', 'pull left'].includes(miss)) {
        recommendations.push('Left misses with a soft/light feel can indicate the shaft is not stable enough for delivery.');
        designBias.push('Add mid/tip stability or torque control without jumping straight to the stiffest/heaviest build.');
      }
      if (['right', 'slice', 'push right'].includes(miss)) {
        recommendations.push('Right misses with harsh/stiff feel can indicate the player cannot square the face comfortably.');
        designBias.push('Restore load/release feedback before reducing loft or forcing a lower-launch tip.');
      }
      if (preference >= 7 && quality < 5) recommendations.push('Player likes the feel but quality is weak; keep the feel direction and fix the section causing dispersion.');
      if (quality >= 6 && preference < 5) recommendations.push('Objective result is decent but sensation is poor; do not trust repeatability until feel improves.');
      if (quality >= 6 && preference >= 7) recommendations.push('Feel and shot quality agree; use this profile as the comparison anchor.');
      if (['s', 'stiff', 'x'].includes(flex) && ['harsh', 'dead', 'boardy'].includes(sensation)) recommendations.push('Include regular/softer-profile candidates in comparison testing.');
      if (weight >= 78 && ['right', 'slice', 'push right'].includes(miss)) recommendations.push('Heavy/stiff right-miss pattern: test lower total weight or more active release profile.');
      return {
        findings,
        recommendations,
        design_bias: designBias,
        study_anchor: 'Burger/Senner 2014: impact sensation and 7-zone shaft profile belong in shaft fitting; speed alone is insufficient.'
      };
    }

    function buildStaticLengthLieFit(payload) {
      const height = Number(payload.height_in || 69);
      const wrist = Number(payload.wrist_to_floor_in || 34);
      const lengthDelta = Math.max(-1.5, Math.min(2, Math.round(((height - 69) * 0.10 + (wrist - 34) * 0.24) * 4) / 4));
      const lieDelta = Math.max(-2, Math.min(6, Math.round((wrist - 34) * 1.0 - (height - 69) * 0.22)));
      const lieLabel = lieDelta > 0 ? `${lieDelta} deg upright` : lieDelta < 0 ? `${Math.abs(lieDelta)} deg flat` : 'standard';
      const notes = [
        'Use height and wrist-to-floor only as the initial build position.',
        'Confirm lie dynamically with face/sole marks, ball flight, and impact location.',
        'Grip, posture, hand height, toe droop, and swing delivery can override the static chart.',
        'This is a setup baseline before camera, visual fitting, and impact-mark layers take over.'
      ];
      if (Math.abs(lengthDelta) >= 1) notes.push('Large length adjustment: validate posture and strike before applying the full chart value.');
      if (Math.abs(lieDelta) >= 3) notes.push('Large lie adjustment: confirm with dynamic lie testing before bending/building.');
      return {
        height_in: height,
        wrist_to_floor_in: wrist,
        recommended_7i_length_in: 37 + lengthDelta,
        length_delta_in: lengthDelta,
        initial_lie_delta_deg: lieDelta,
        initial_lie_label: lieLabel,
        notes
      };
    }

    function rolloutTargetPercent(speed) {
      const clamped = Math.max(80, Math.min(120, Number(speed || 100)));
      return 13 - ((clamped - 80) / 10);
    }

    function buildLaunchRolloutRead(payload) {
      const speed = Number(payload.speed_mph || 105);
      const target = rolloutTargetPercent(speed);
      const carry = Number(payload.carry_yards || 0);
      const total = Number(payload.total_yards || 0);
      const pwCarry = Number(payload.pw_carry_yards || 0);
      const recommendations = [];
      let actual = null;
      let rolloutRead = 'missing carry/total proof';
      if (carry > 0 && total > carry) {
        actual = ((total - carry) / total) * 100;
        const delta = actual - target;
        if (delta > 1) {
          rolloutRead = 'too much rollout for target carry/roll mix';
          recommendations.push('Spin/launch window may be too low; test more loft, higher launch, or more spin before changing shaft stiffness.');
        } else if (delta < -1) {
          rolloutRead = 'not enough rollout for target carry/roll mix';
          recommendations.push('Spin/launch window may be too high; test lower loft or spin control before blaming shaft weight.');
        } else {
          rolloutRead = 'rollout is inside the target window';
          recommendations.push('Carry/roll mix is near optimized for the measured club speed.');
        }
      } else {
        recommendations.push('Measure carry and total with laser/GPS or launch monitor to judge rollout percentage.');
      }
      const pwTarget = pwCarry > 0 ? pwCarry * 2.03 : null;
      let pwRead = 'PW carry not provided';
      if (pwTarget && carry > 0) {
        const carryDelta = carry - pwTarget;
        if (carryDelta < -10) {
          pwRead = 'driver carry is short versus PW relationship';
          recommendations.push('Driver is underperforming relative to PW; check impact, launch/spin, and playing length.');
        } else if (carryDelta > 10) {
          pwRead = 'driver carry is above PW relationship';
          recommendations.push('Driver carry is strong relative to PW; verify PW is a good working reference.');
        } else {
          pwRead = 'driver carry matches PW relationship';
        }
      } else if (pwTarget) {
        pwRead = 'PW reference target calculated, driver carry missing';
      }
      return {
        target_rollout_pct: target,
        actual_rollout_pct: actual,
        rollout_read: rolloutRead,
        pw_driver_carry_target: pwTarget,
        pw_read: pwRead,
        recommendations,
        proof_steps: [
          'Use same ball and normal conditions when measuring carry and rollout.',
          'Compare rollout percentage to the club-speed target before deciding loft/spin changes.',
          'Use PW carry x 2.03 only when the PW is a good working reference club.',
          'Separate ball-flight tuning from shaft-feel tuning.'
        ]
      };
    }

    function buildVisualFittingRead(payload) {
      const tempo = String(payload.visual_tempo_control || 'unknown').toLowerCase();
      const rhythm = String(payload.visual_rhythm_float || 'unknown').toLowerCase();
      const transition = String(payload.visual_transition_move || 'unknown').toLowerCase();
      const commitment = String(payload.visual_commitment || 'unknown').toLowerCase();
      const shoulder = String(payload.visual_one_arm_shoulder || 'unknown').toLowerCase();
      const leaks = String(payload.visual_power_leaks || 'unknown').toLowerCase();
      const diagnosis = [];
      const fittingMoves = [];
      const shaftBias = [];

      if (tempo === 'inconsistent' || tempo === 'slow/insecure' || rhythm === 'no float' || rhythm === 'loose') {
        diagnosis.push('Tempo/rhythm looks insecure; the player may not trust the club or shaft load.');
        fittingMoves.push('Test more shaft weight or a stronger butt/mid section before assuming the player needs lighter.');
        shaftBias.push('Add handle/mid feedback and resistance without immediately over-stiffening the tip.');
      }
      if (transition === 'jump start' || transition === 'hips slide' || transition === 'struggle') {
        diagnosis.push('Player appears to jump-start transition, often pointing to too much total weight or too stiff a handle/mid profile.');
        fittingMoves.push('Back down total/shaft weight a few grams and retest transition before changing launch profile.');
        shaftBias.push('Reduce total-weight target or soften handle/mid load response while preserving face control.');
      }
      if (shoulder === 'drop' || shoulder === 'too heavy') {
        diagnosis.push('One-arm shoulder drop suggests total weight is above the player useful upper limit.');
        fittingMoves.push('Lower shaft/total weight and retest until the shoulder can control the club through the bottom.');
        shaftBias.push('Cap shaft weight recommendation and avoid adding mass to solve feel.');
      }
      if (commitment === 'kill ball' || commitment === 'overplay' || leaks === 'multiple bursts' || leaks === 'sparks' || leaks === 'leaking') {
        diagnosis.push('Player is overplaying the club and leaking power in stages.');
        fittingMoves.push('Check whether butt/mid/tip are too stiff or feedback is too harsh.');
        shaftBias.push('Use smoother load feedback or damping; do not chase lower launch by making the tip brutally stiff.');
      }
      if (commitment === 'weak') {
        diagnosis.push('Player looks under-committed; this can be a club that is too light/weak, not necessarily a weak player.');
        fittingMoves.push('Test added shaft weight or MOI/resistance to see whether speed and commitment wake up.');
        shaftBias.push('Raise weight/resistance trial before recommending a lighter shaft.');
      }
      if (!diagnosis.length) {
        diagnosis.push('No obvious visual-fit conflict recorded. Use impact marks and launch data as the main proof.');
        fittingMoves.push('Keep the current shaft direction and change one variable at a time.');
        shaftBias.push('Neutral visual fit: preserve feel while validating CPM, torque, launch, and dispersion.');
      }
      return {
        diagnosis,
        fitting_moves: fittingMoves,
        shaft_design_bias: shaftBias,
        warnings: [
          'Shaft labels are not enough; visual motion can contradict high/low launch catalog claims.',
          'Use loft/head/ball to tune ball flight when possible; do not force the shaft to solve every flight problem.',
          'The right shaft is the player dancing partner: trust visible rhythm, balance, and contact proof.'
        ]
      };
    }

    function buildDiyDriverTuneup(payload) {
      const impact = String(payload.impact_pattern || 'unknown').toLowerCase();
      const vertical = String(payload.vertical_impact || 'unknown').toLowerCase();
      const headFeel = String(payload.head_weight_feel || 'unknown').toLowerCase();
      const effectiveLength = Math.max(42, Number(payload.current_length_in || 45.5) - Number(payload.gripped_down_in || 0));
      const driverWeight = Math.max(45, Math.min(85, Number(payload.pw_shaft_weight_g || 120) * 0.5));
      const actions = [];
      const leadTapePlan = [];
      const shaftNotes = [];
      const warnings = [];

      if (impact === 'heel' || impact === 'all over') {
        actions.push('Test shorter playing length before cutting: grip down in 0.5 inch steps and mark the grip with tape.');
        actions.push('Retest impact marks until strike moves toward center-to-slight-toe.');
      } else if (impact === 'toe') {
        actions.push('Toe-side impact may mean too short, but first check whether total/head weight is too high.');
        warnings.push('Toe impact can be a player response to excessive weight, not only a length problem.');
      } else if (impact === 'ideal' || impact === 'upper toe') {
        actions.push('Length is near the maximum useful range. Preserve it unless launch/spin or dispersion proves otherwise.');
      } else {
        actions.push('Start with impact marks. The shaft builder should not guess before strike location is known.');
      }

      if (vertical === 'low') actions.push('Raise tee height after length is stable; low-face contact generally adds spin.');
      if (vertical === 'high') actions.push('Lower tee height slightly if impact is too high; above-center can cut spin, but too high costs ball speed.');
      if (vertical === 'upper toe') actions.push('Target upper-toe / slightly above-center contact for strong ball speed and controlled spin.');

      if (headFeel === 'light') {
        leadTapePlan.push('Add lead tape one stripe at a time, blind-test feel and impact, then dial back from clearly too much.');
      } else if (headFeel === 'heavy') {
        leadTapePlan.push('Reduce added head weight or test a lighter build before blaming shaft flex.');
        warnings.push('Excessive total/head weight can make the player pull the club and move impact opposite the expected direction.');
      } else {
        leadTapePlan.push('Use lead tape only after length/tee are controlled; avoid chasing swing-weight numbers.');
      }
      leadTapePlan.push('Test nine sole positions: front/center/back crossed with heel/center/toe.');
      leadTapePlan.push('Front sole lowers dynamic loft influence; back sole adds MOI/dynamic loft; toe biases fade; heel biases draw.');

      shaftNotes.push(`Effective test length is ${effectiveLength.toFixed(2)} inches.`);
      shaftNotes.push(`PW rule suggests about ${driverWeight.toFixed(0)} g uncut driver shaft if PW shaft is ${Number(payload.pw_shaft_weight_g || 120).toFixed(0)} g.`);
      shaftNotes.push('Simulate higher shaft/total weight by adding tape near the shaft balance point.');
      shaftNotes.push('Do not cut until tape-shorter and lead-tape tests repeat.');
      if (Number(payload.added_head_weight_g || 0) > 0) {
        shaftNotes.push('Added head weight may require manufacturer tip-trim review; graphite tip trim changes launch/tip behavior more than flex.');
      }

      return {effective_test_length_in: effectiveLength, recommended_driver_shaft_weight_g: driverWeight, actions, lead_tape_plan: leadTapePlan, shaft_notes: shaftNotes, warnings};
    }

    function buildSwingFitFromPayload(payload) {
      const tempo = payload.tempo_seconds >= 1.18 ? 'Smooth' : (payload.tempo_seconds <= 0.9 || payload.motion_score >= 72 ? 'Aggressive' : 'Medium');
      const transition = payload.transition_load >= 68 || payload.motion_score >= 78 ? 'Hard' : payload.transition_load <= 38 ? 'Smooth' : 'Medium';
      const release = payload.release_score >= 64 ? 'Late' : payload.release_score <= 36 ? 'Early' : 'Mid';
      const miss = payload.face_closure_rate >= 68 ? 'Left' : payload.face_closure_rate <= 32 ? 'Right' : payload.spin_rpm >= 3100 ? 'High spin' : payload.launch_deg <= 10.5 ? 'Low launch' : 'Neutral';
      const feel = transition === 'Hard' && payload.speed_mph >= 108 ? 'Boardy/stout' : tempo === 'Smooth' && transition !== 'Hard' ? 'Softer load' : 'Stable mid';
      const saved = {
        fitSpeed: payload.speed_mph,
        fitTempo: tempo,
        fitTransition: transition,
        fitRelease: release,
        fitLaunch: payload.launch_deg,
        fitSpin: payload.spin_rpm,
        fitMiss: miss,
        fitFeel: feel,
        fitWeight: payload.weight_g
      };
      Object.entries(saved).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
      });
      runFitToBuild();
      latestFitProfile = enrichCameraFitProfile(latestFitProfile, payload, {tempo, transition, release, miss, feel});
      latestCameraSwingProfile = {
        captured_at: new Date().toISOString(),
        payload,
        derived_inputs: {tempo, transition, release, miss, feel},
        fit_target: latestFitProfile,
        boundary: 'Use this as a shaft design starting point. Validate with measured CPM, launch monitor, and player feedback.'
      };
      cameraCaptures = [latestCameraSwingProfile, ...cameraCaptures].slice(0, 5);
      renderCameraFitResult();
      return latestCameraSwingProfile;
    }

    function renderCameraFitResult() {
      updateCameraHud();
      const result = document.getElementById('cameraFitResult');
      const packet = document.getElementById('cameraPacket');
      const list = document.getElementById('cameraCaptureList');
      const interviewList = document.getElementById('cameraInterviewList');
      const aiReviewList = document.getElementById('cameraAiReviewList');
      const whyList = document.getElementById('cameraWhyList');
      const zoneList = document.getElementById('cameraZoneList');
      const proofList = document.getElementById('cameraProofList');
      const tuneupList = document.getElementById('cameraTuneupList');
      const visualList = document.getElementById('cameraVisualList');
      const rolloutList = document.getElementById('cameraRolloutList');
      const staticFitList = document.getElementById('cameraStaticFitList');
      const sensationList = document.getElementById('cameraSensationList');
      const wishonList = document.getElementById('cameraWishonList');
      const databaseList = document.getElementById('cameraDatabaseList');
      if (!latestCameraSwingProfile) {
        if (result) result.innerHTML = '<tr><td colspan="2">No swing analyzed yet.</td></tr>';
        if (packet) packet.textContent = 'No swing packet yet.';
        if (interviewList) interviewList.innerHTML = '<li>No interview direction yet.</li>';
        if (aiReviewList) aiReviewList.innerHTML = '<li>No AI swing review yet.</li>';
        if (whyList) whyList.innerHTML = '<li>No fit explanation yet.</li>';
        if (zoneList) zoneList.innerHTML = '<li>No build zones yet.</li>';
        if (proofList) proofList.innerHTML = '<li>No proof checklist yet.</li>';
        if (tuneupList) tuneupList.innerHTML = '<li>No tune-up plan yet.</li>';
        if (visualList) visualList.innerHTML = '<li>No visual fitting read yet.</li>';
        if (rolloutList) rolloutList.innerHTML = '<li>No launch/rollout read yet.</li>';
        if (staticFitList) staticFitList.innerHTML = '<li>No static fit start yet.</li>';
        if (sensationList) sensationList.innerHTML = '<li>No sensation/quality read yet.</li>';
        if (wishonList) wishonList.innerHTML = '<li>No Wishon guard read yet.</li>';
        if (databaseList) databaseList.innerHTML = '<li>No comparable shafts yet.</li>';
      } else {
        const fit = latestCameraSwingProfile.fit_target;
        const inputs = latestCameraSwingProfile.derived_inputs;
        if (result) {
          result.innerHTML = [
            ['Target CPM', fit.target_cpm.toFixed(1)],
            ['Wrap Angle', fit.wrap_angle_deg.toFixed(0) + ' deg'],
            ['Torque Target', fit.torque_target_deg.toFixed(2) + ' deg'],
            ['Material', fit.builder_brief.recommended_material],
            ['Architecture', fit.builder_brief.recommended_architecture.replace(/_/g, ' ')],
            ['Derived Tempo', inputs.tempo],
            ['Derived Transition', inputs.transition],
            ['Derived Release', inputs.release],
            ['Miss Bias', inputs.miss],
            ['Confidence', latestCameraSwingProfile.payload.motion_quality + ' / 100']
          ].map(row => `<tr><td>${row[0]}</td><td>${escapeFitText(row[1])}</td></tr>`).join('');
        }
        if (interviewList) {
          const interview = fit.fitting_interview || {};
          const interviewItems = [
            ...(interview.start_points || []),
            ...(interview.watch_items || []).map(item => `Watch: ${item}`),
            ...(interview.fitter_questions || []).map(item => `Ask: ${item}`),
            interview.source ? `Source: ${interview.source}` : ''
          ].filter(Boolean);
          interviewList.innerHTML = interviewItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No interview direction yet.</li>';
        }
        if (aiReviewList) {
          const review = latestCameraSwingProfile.ai_review || cameraCaptures[0]?.ai_review;
          const reviewItems = review ? [
            `Verdict: ${review.verdict}`,
            ...(review.findings || []),
            ...(review.next_actions || []).map(item => `Next: ${item}`),
            review.boundary ? `Boundary: ${review.boundary}` : ''
          ].filter(Boolean) : [];
          aiReviewList.innerHTML = reviewItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No AI swing review yet.</li>';
        }
        if (whyList) {
          whyList.innerHTML = (fit.why_this_fit || []).map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No fit explanation yet.</li>';
        }
        if (zoneList) {
          zoneList.innerHTML = (fit.manufacturing_zones || []).map(item => `<li><strong>${escapeFitText(item.zone)}</strong>: ${escapeFitText(item.design_goal)} ${escapeFitText(item.layup_note)}</li>`).join('') || '<li>No build zones yet.</li>';
        }
        if (proofList) {
          proofList.innerHTML = (fit.proof_requirements || []).map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No proof checklist yet.</li>';
        }
        if (tuneupList) {
          const tuneup = fit.diy_driver_tuneup || {};
          const tuneupItems = [
            ...(tuneup.actions || []),
            ...(tuneup.lead_tape_plan || []),
            ...(tuneup.shaft_notes || []),
            ...(tuneup.warnings || []).map(item => `Warning: ${item}`)
          ];
          tuneupList.innerHTML = tuneupItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No tune-up plan yet.</li>';
        }
        if (visualList) {
          const visual = fit.visual_fitting || {};
          const visualItems = [
            ...(visual.diagnosis || []),
            ...(visual.fitting_moves || []),
            ...(visual.shaft_design_bias || []).map(item => `Design bias: ${item}`),
            ...(visual.warnings || []).map(item => `Rule: ${item}`)
          ];
          visualList.innerHTML = visualItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No visual fitting read yet.</li>';
        }
        if (rolloutList) {
          const rollout = fit.launch_rollout_optimizer || {};
          const rolloutItems = [
            `Target rollout: ${Number(rollout.target_rollout_pct || 0).toFixed(1)}% of total.`,
            rollout.actual_rollout_pct == null ? 'Actual rollout: not measured.' : `Actual rollout: ${Number(rollout.actual_rollout_pct).toFixed(1)}% of total.`,
            `Read: ${rollout.rollout_read || 'No read yet.'}`,
            rollout.pw_driver_carry_target == null ? 'PW target: not provided.' : `PW x 2.03 driver carry target: ${Number(rollout.pw_driver_carry_target).toFixed(0)} yd.`,
            `PW read: ${rollout.pw_read || 'No PW read yet.'}`,
            ...(rollout.recommendations || []),
            ...(rollout.proof_steps || []).map(item => `Proof: ${item}`)
          ];
          rolloutList.innerHTML = rolloutItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No launch/rollout read yet.</li>';
        }
        if (staticFitList) {
          const staticFit = fit.static_length_lie || {};
          const staticItems = [
            `Height/WTF: ${Number(staticFit.height_in || 0).toFixed(1)} in / ${Number(staticFit.wrist_to_floor_in || 0).toFixed(1)} in.`,
            `Initial 7i length: ${Number(staticFit.recommended_7i_length_in || 37).toFixed(2)} in (${Number(staticFit.length_delta_in || 0) >= 0 ? '+' : ''}${Number(staticFit.length_delta_in || 0).toFixed(2)}).`,
            `Initial lie: ${staticFit.initial_lie_label || 'standard'}.`,
            ...(staticFit.notes || []).map(item => `Note: ${item}`)
          ];
          staticFitList.innerHTML = staticItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No static fit start yet.</li>';
        }
        if (sensationList) {
          const sensation = fit.shaft_sensation_quality || {};
          const sensationItems = [
            ...(sensation.findings || []),
            ...(sensation.recommendations || []),
            ...(sensation.design_bias || []).map(item => `Design bias: ${item}`),
            sensation.study_anchor ? `Study anchor: ${sensation.study_anchor}` : ''
          ].filter(Boolean);
          sensationList.innerHTML = sensationItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No sensation/quality read yet.</li>';
        }
        if (wishonList) {
          const wishon = fit.wishon_profile_guard || {};
          const wishonItems = [
            ...(wishon.findings || []),
            ...(wishon.profile_requirements || []).map(item => `Profile: ${item}`),
            ...(wishon.recommendations || []),
            ...(wishon.torque_notes || []).map(item => `Torque: ${item}`),
            ...(wishon.trimming_notes || []).map(item => `Trim: ${item}`),
            wishon.source_anchor ? `Source anchor: ${wishon.source_anchor}` : '',
            wishon.boundary ? `Boundary: ${wishon.boundary}` : ''
          ].filter(Boolean);
          wishonList.innerHTML = wishonItems.map(item => `<li>${escapeFitText(item)}</li>`).join('') || '<li>No Wishon guard read yet.</li>';
        }
        if (databaseList) {
          databaseList.innerHTML = (fit.shaft_database_matches || []).map(item => `<li><strong>${escapeFitText(item.name)}</strong>: ${escapeFitText(item.profile)} (${item.match_score}/8 match)</li>`).join('') || '<li>No comparable shafts yet.</li>';
        }
        if (packet) packet.textContent = JSON.stringify(latestCameraSwingProfile, null, 2);
      }
      if (list) {
        list.innerHTML = cameraCaptures.map((item, index) => {
          const fit = item.fit_target;
          const seed = item.payload.camera_review_seed || {};
          const viewText = seed.down_line_samples ? '2-view capture' : seed.face_on_samples ? 'face-on only' : 'manual capture';
          const reviewed = item.ai_review ? ' | AI review ready' : '';
          return `<div class="camera-capture-pill"><strong>Swing ${index + 1}</strong> - ${fit.target_cpm.toFixed(1)} CPM, ${item.derived_inputs.transition} transition, ${item.payload.motion_quality}/100 quality<br><small>${escapeFitText(viewText + reviewed)}</small></div>`;
        }).join('');
      }
    }

    function buildCapturedSwingAiReview(captures) {
      if (!captures.length) {
        return {
          verdict: 'No captured swings yet.',
          findings: ['Capture at least one face-on and down-line swing before asking for review.'],
          next_actions: ['Start cameras, capture a swing, then run AI review.'],
          boundary: 'AI review needs captured swing context before it can help the fitter.'
        };
      }
      const primary = captures[0];
      const payload = primary.payload || {};
      const seed = payload.camera_review_seed || {};
      const inputs = primary.derived_inputs || {};
      const findings = [];
      const nextActions = [];

      if (seed.face_on_samples) {
        findings.push(`Face-on view captured ${seed.face_on_samples} motion samples for setup, tempo, pressure shift, and shaft load clues.`);
      } else {
        findings.push('Face-on view is missing; setup/load/tempo review is limited.');
        nextActions.push('Capture a face-on view before locking shaft load or tempo conclusions.');
      }

      if (seed.down_line_samples) {
        findings.push(`Down-line view captured ${seed.down_line_samples} motion samples for plane, path, hand path, and delivery clues.`);
      } else {
        findings.push('Down-line view is missing; path/plane/delivery review is limited.');
        nextActions.push('Capture a down-line view before blaming shaft profile for path or face delivery.');
      }

      if (inputs.transition === 'Hard') {
        findings.push('Transition read is hard; check whether the shaft is being overloaded from the top or if the player is rushing sequence.');
        nextActions.push('Validate transition with face-on load timing before adding tip or mid stiffness.');
      }
      if (inputs.release === 'Early') {
        nextActions.push('Review face-on release timing and impact pattern before softening the tip.');
      }
      if (inputs.release === 'Late') {
        nextActions.push('Review down-line delivery and closure rate before adding anti-left stiffness.');
      }
      if (inputs.miss === 'Right') {
        nextActions.push('Use down-line path plus face-on release timing to separate path issue from shaft release issue.');
      }
      if (inputs.miss === 'Left') {
        nextActions.push('Check closure rate and handle load before reducing torque or stiffening tip.');
      }
      if (Number(payload.motion_quality || 0) < 60) {
        findings.push('Motion quality is low; treat this as a direction finder, not a final build decision.');
        nextActions.push('Capture two cleaner swings before sending the result to CAD.');
      }

      if (!nextActions.length) {
        nextActions.push('Use the current shaft target as a prototype starting point and validate with impact pattern, launch, spin, and player feel.');
      }

      return {
        verdict: `${captures.length} captured swing${captures.length === 1 ? '' : 's'} reviewed; ${seed.down_line_samples && seed.face_on_samples ? 'two-view review ready' : 'review limited by missing camera angle'}.`,
        findings,
        next_actions: nextActions,
        boundary: 'AI review is a fitting direction read; validate with actual video, impact marks, launch data, and player feedback.'
      };
    }

    function aiReviewCapturedSwings(button) {
      flashButton(button, 'Reviewed');
      const review = buildCapturedSwingAiReview(cameraCaptures);
      if (latestCameraSwingProfile) latestCameraSwingProfile.ai_review = review;
      cameraCaptures = cameraCaptures.map((item, index) => index === 0 ? {...item, ai_review: review} : item);
      renderCameraFitResult();
      setCameraState(`AI review ready: ${review.verdict}`);
    }

    async function startCameraFit(button) {
      flashButton(button, 'Starting');
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        updateCameraHud('Unavailable', 'Manual mode');
        setCameraState('Browser camera unavailable; manual swing mode is ready.', true);
        return;
      }
      try {
        const devices = navigator.mediaDevices.enumerateDevices ? await navigator.mediaDevices.enumerateDevices() : [];
        const videoInputs = devices.filter(device => device.kind === 'videoinput');
        const faceConstraints = videoInputs[0]?.deviceId ? {deviceId: {exact: videoInputs[0].deviceId}} : {facingMode: 'user'};
        const downLineConstraints = videoInputs[1]?.deviceId ? {deviceId: {exact: videoInputs[1].deviceId}} : {facingMode: 'environment'};
        cameraStreams.face = await navigator.mediaDevices.getUserMedia({ video: faceConstraints, audio: false });
        try {
          cameraStreams.downLine = await navigator.mediaDevices.getUserMedia({ video: downLineConstraints, audio: false });
        } catch (secondError) {
          cameraStreams.downLine = null;
        }
        cameraStream = cameraStreams.face;
        const faceVideo = document.getElementById('cameraVideoFace');
        const downLineVideo = document.getElementById('cameraVideoDownLine');
        if (faceVideo && cameraStreams.face) {
          faceVideo.srcObject = cameraStreams.face;
          await faceVideo.play();
        }
        if (downLineVideo && cameraStreams.downLine) {
          downLineVideo.srcObject = cameraStreams.downLine;
          await downLineVideo.play();
        }
        updateCameraHud(cameraStreams.downLine ? '2 cameras' : '1 camera', 'Ready');
        setCameraState(cameraStreams.downLine ? 'Face-on and down-line cameras live. Capture a swing when ready.' : 'Face-on camera live. Down-line camera unavailable; capture still works with limited review.');
      } catch (error) {
        updateCameraHud('Blocked', 'Manual mode');
        setCameraState(`Camera blocked: ${error.message || String(error)}. Manual swing mode is ready.`, true);
      }
    }

    function stopCameraFit(button) {
      flashButton(button, 'Stopped');
      if (cameraSampleTimer) window.clearInterval(cameraSampleTimer);
      cameraSampleTimer = null;
      Object.values(cameraStreams).filter(Boolean).forEach(stream => stream.getTracks().forEach(track => track.stop()));
      cameraStreams = {face: null, downLine: null};
      cameraStream = null;
      cameraPreviousBrightness = null;
      cameraPreviousBrightnessByView = {face: null, downLine: null};
      ['cameraVideoFace', 'cameraVideoDownLine'].forEach(id => {
        const video = document.getElementById(id);
        if (video) video.srcObject = null;
      });
      updateCameraHud('Off', 'Idle');
      setCameraState('Cameras stopped.');
    }

    function sampleSingleCameraMotion(viewKey, videoId, canvasId, meterId) {
      const video = document.getElementById(videoId);
      const canvas = document.getElementById(canvasId);
      const meter = document.getElementById(meterId);
      if (!video || !canvas || video.readyState < 2) return null;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let brightness = 0;
      for (let i = 0; i < data.length; i += 16) {
        brightness += (data[i] + data[i + 1] + data[i + 2]) / 3;
      }
      brightness = brightness / (data.length / 16);
      const previous = cameraPreviousBrightnessByView[viewKey];
      const motion = previous == null ? 0 : Math.abs(brightness - previous);
      cameraPreviousBrightnessByView[viewKey] = brightness;
      cameraMotionSamplesByView[viewKey].push(motion);
      if (meter) meter.style.width = `${Math.max(4, Math.min(100, motion * 6))}%`;
      return motion;
    }

    function sampleCameraMotion() {
      const faceMotion = sampleSingleCameraMotion('face', 'cameraVideoFace', 'cameraSampleCanvasFace', 'cameraMotionMeterFace');
      const downLineMotion = sampleSingleCameraMotion('downLine', 'cameraVideoDownLine', 'cameraSampleCanvasDownLine', 'cameraMotionMeterDownLine');
      const motions = [faceMotion, downLineMotion].filter(value => value != null);
      if (motions.length) {
        const combinedMotion = Math.max(...motions);
        cameraPreviousBrightness = combinedMotion;
        cameraMotionSamples.push(combinedMotion);
      }
    }

    function startCameraSwingCapture(button) {
      flashButton(button, 'Capturing');
      const hasLiveCamera = Boolean(cameraStreams.face || cameraStreams.downLine);
      cameraMotionSamples = [];
      cameraMotionSamplesByView = {face: [], downLine: []};
      cameraPreviousBrightness = null;
      cameraPreviousBrightnessByView = {face: null, downLine: null};
      updateCameraHud(hasLiveCamera ? (cameraStreams.downLine ? '2 cameras' : '1 camera') : 'Manual', 'Capturing');
      setCameraState('Capturing swing window.');
      if (cameraSampleTimer) window.clearInterval(cameraSampleTimer);
      cameraSampleTimer = window.setInterval(sampleCameraMotion, 180);
      window.setTimeout(() => {
        if (cameraSampleTimer) window.clearInterval(cameraSampleTimer);
        cameraSampleTimer = null;
        const profile = buildSwingFitFromPayload(hasLiveCamera ? deriveCameraPayloadFromSamples() : cameraManualPayload('manual-no-camera', 50, 65));
        updateCameraHud(hasLiveCamera ? (cameraStreams.downLine ? '2 cameras' : '1 camera') : 'Manual', 'Analyzed');
        setCameraState(`Swing analyzed: ${profile.fit_target.target_cpm.toFixed(1)} CPM target generated.`);
      }, 5400);
    }

    function analyzeManualSwing(button) {
      flashButton(button, 'Analyzed');
      const profile = buildSwingFitFromPayload(cameraManualPayload('manual-entry', 50, 72));
      updateCameraHud((cameraStreams.face || cameraStreams.downLine) ? 'Live' : 'Manual', 'Analyzed');
      setCameraState(`Manual swing analyzed: ${profile.fit_target.target_cpm.toFixed(1)} CPM target generated.`);
    }

    function sendCameraToFit(button) {
      if (!latestCameraSwingProfile) analyzeManualSwing();
      flashButton(button, 'Sent');
      showView('fit');
      renderFitBridge('camera->fit');
      setCameraState('Camera swing sent to Fit-to-Build.');
    }

    function applyCameraToCad(button) {
      if (!latestCameraSwingProfile) analyzeManualSwing();
      flashButton(button, 'Applied');
      applyFitToCad();
      showView('cad3d');
      setCameraState('Camera swing applied to CAD.');
    }

    function fitTorqueWindow(torqueTarget) {
      return torqueTarget <= 3.4 ? 'stout' : torqueTarget <= 3.9 ? 'balanced' : 'active';
    }

    function fitBuildBrief(profile) {
      const inputs = profile.inputs || {};
      const torqueWindow = fitTorqueWindow(profile.torque_target_deg);
      let material = 'Mitsubishi MR70';
      if (inputs.speed >= 105) material = 'Toray T800H';
      if (inputs.speed >= 112 || inputs.transition === 'Hard') material = 'Toray M40J';
      if (inputs.speed >= 118 || inputs.feel === 'Boardy/stout') material = 'Toray M46J';
      if (inputs.speed < 98 && inputs.feel === 'Softer load') material = 'Toray T700S';
      if (inputs.feel === 'Boardy/stout' && inputs.speed < 108) material = 'Hexcel IM7';
      let architecture = inputs.transition === 'Hard' ? 'braid_tape_braid' : 'flag_wrap';
      if (profile.launch_bias.includes('lower')) architecture = inputs.transition === 'Hard' ? 'braid_tape_braid' : 'automated_tape';
      if (inputs.feel === 'Softer load') architecture = 'hybrid_flag_helix';

      const rationale = [
        `${inputs.speed.toFixed(0)} mph speed sets the base stiffness target.`,
        `${inputs.tempo} tempo and ${inputs.transition} transition adjust load stability.`,
        `${inputs.release} release timing tunes how much the tip can recover.`,
        `${inputs.miss} miss pattern biases the shaft away from the common miss.`
      ];
      const buildSteps = [
        `Set global target CPM to ${profile.target_cpm.toFixed(1)}.`,
        `Use ${material} as the starting material assumption.`,
        `Set primary bias pair near +/-${profile.wrap_angle_deg.toFixed(0)} degrees.`,
        'Add a 0 degree butt/mid axial stability flag.',
        profile.tip_strategy.charAt(0).toUpperCase() + profile.tip_strategy.slice(1) + '.',
        'Run CPM, torque, EI, and launch checks before freezing the CAD packet.'
      ];
      if (inputs.feel === 'Softer load') {
        buildSteps.splice(4, 0, 'Add a thin S-glass or aramid damping layer before increasing carbon stiffness.');
      }
      if (['Toray M46J', 'Mitsubishi Dialead K13C'].includes(material)) {
        buildSteps.push('Keep ultra-high-modulus material local; avoid making the whole shaft brittle or harsh.');
      }
      const risks = [];
      if (inputs.transition === 'Hard' && inputs.feel === 'Softer load') {
        risks.push('Hard transition conflicts with soft-load feel; prototype both torque and tip response before committing.');
      }
      if (inputs.miss === 'Right' && profile.launch_bias.includes('lower')) {
        risks.push('Right miss plus lower-launch target can feel too tip-stiff if overbuilt.');
      }
      if (profile.torque_target_deg <= 2.8) {
        risks.push('Very low torque target may require extra hoop/braid support and could add harsh feel.');
      }
      if (inputs.speed >= 115) {
        risks.push('High-speed player: validate tip recovery and face closure with real range data.');
      }
      if (!risks.length) {
        risks.push('No major conflict detected; still validate against measured CPM and player feedback.');
      }
      const testPlan = [
        'Build one baseline prototype from the generated CAD packet.',
        'Measure 7-zone CPM and compare each station to the target profile.',
        'Hit-test launch, spin, start line, and miss pattern before changing CAD.',
        'Adjust one variable at a time: wrap angle, tip flag width, or hoop/braid support.'
      ];
      return {
        intent: `Build a ${profile.target_cpm.toFixed(1)} CPM shaft with a ${torqueWindow} torque window, ${profile.launch_bias}, and ${String(inputs.feel).toLowerCase()} feel.`,
        torque_window: torqueWindow,
        recommended_material: material,
        recommended_architecture: architecture,
        rationale,
        build_steps: buildSteps,
        risk_flags: risks,
        test_plan: testPlan
      };
    }

    function renderFitBuilderBrief(profile) {
      const brief = profile?.builder_brief || fitBuildBrief(profile);
      const recipeTitle = `${brief.recommended_material} / ${brief.recommended_architecture.replace(/_/g, ' ')}`;
      const riskTitle = brief.risk_flags.length === 1 && brief.risk_flags[0].startsWith('No major') ? 'Clean first pass' : `${brief.risk_flags.length} warning${brief.risk_flags.length === 1 ? '' : 's'}`;
      document.getElementById('fitIntentTitle').textContent = `${profile.target_cpm.toFixed(1)} CPM / ${brief.torque_window} torque`;
      document.getElementById('fitIntentText').textContent = brief.intent;
      document.getElementById('fitRecipeTitle').textContent = recipeTitle;
      document.getElementById('fitRecipeList').innerHTML = brief.build_steps.map(step => `<li>${escapeFitText(step)}</li>`).join('');
      document.getElementById('fitRiskTitle').textContent = riskTitle;
      document.getElementById('fitRiskList').innerHTML = brief.risk_flags.map(flag => `<li>${escapeFitText(flag)}</li>`).join('');
      document.getElementById('fitTestTitle').textContent = 'One-change-at-a-time plan';
      document.getElementById('fitTestList').innerHTML = brief.test_plan.map(step => `<li>${escapeFitText(step)}</li>`).join('');
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
          tip_strategy: latestFitProfile.tip_strategy,
          recommended_material: latestFitProfile.builder_brief?.recommended_material,
          recommended_architecture: latestFitProfile.builder_brief?.recommended_architecture
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
        ['Transfer Wrap Angle', packet.transfer.set_wrap_angle_deg.toFixed(0) + ' deg'],
        ['Transfer Material', packet.transfer.recommended_material || 'n/a'],
        ['Transfer Architecture', (packet.transfer.recommended_architecture || 'n/a').replace(/_/g, ' ')]
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
        ['Launch Intent', latestFitProfile.launch_bias],
        ['Risk Flags', String(latestFitProfile.builder_brief?.risk_flags?.length || 0)]
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
        target_cpm_window: {low: targetCpm - 3, high: targetCpm + 3},
        target_weight_g: weight,
        torque_target_deg: torqueTarget,
        wrap_angle_deg: wrapAngle,
        launch_bias: launchBias,
        tip_strategy: tipBias,
        zone_profile: profile,
        inputs: {speed, launch, spin, weight, tempo, transition, release, miss, feel}
      };
      latestFitProfile.builder_brief = fitBuildBrief(latestFitProfile);
      latestFitProfile.cad_translation = {
        set_target_cpm: targetCpm,
        set_wrap_angle_deg: wrapAngle,
        bias_pair_deg: [wrapAngle, -wrapAngle],
        tip_strategy: tipBias,
        recommended_material: latestFitProfile.builder_brief.recommended_material,
        recommended_architecture: latestFitProfile.builder_brief.recommended_architecture
      };

      document.getElementById('fitProfile').innerHTML = [
        ['Target Overall CPM', targetCpm.toFixed(1)],
        ['CPM Build Window', `${(targetCpm - 3).toFixed(1)} - ${(targetCpm + 3).toFixed(1)}`],
        ['Target Weight', weight.toFixed(0) + ' g'],
        ['Torque Target', torqueTarget.toFixed(2) + ' deg'],
        ['Wrap Angle', wrapAngle.toFixed(0) + ' deg'],
        ['Material Starting Point', latestFitProfile.builder_brief.recommended_material],
        ['Architecture Starting Point', latestFitProfile.builder_brief.recommended_architecture.replace(/_/g, ' ')],
        ['Launch Bias', launchBias],
        ['Tip Strategy', tipBias]
      ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td></tr>`).join('');

      document.getElementById('fitBuild').textContent = JSON.stringify({
        shaft_target: {
          target_cpm: latestFitProfile.target_cpm,
          target_cpm_window: latestFitProfile.target_cpm_window,
          torque_target_deg: latestFitProfile.torque_target_deg,
          target_weight_g: latestFitProfile.target_weight_g,
          zone_profile: latestFitProfile.zone_profile
        },
        builder_brief: latestFitProfile.builder_brief,
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
      renderFitBuilderBrief(latestFitProfile);
      renderFitBridge('fit-generated');
    }

    function applyFitToCad(button) {
      if (!latestFitProfile) runFitToBuild(button);
      flashButton(button, 'Applied');
      document.getElementById('target').value = latestFitProfile.target_cpm.toFixed(1);
      document.getElementById('angle').value = latestFitProfile.wrap_angle_deg.toFixed(0);
      document.getElementById('speed').value = latestFitProfile.inputs.speed;
      const materialSelect = document.getElementById('material');
      const architectureSelect = document.getElementById('architectureMode');
      const methodSelect = document.getElementById('method');
      const recommendedMaterial = latestFitProfile.builder_brief?.recommended_material;
      const recommendedArchitecture = latestFitProfile.builder_brief?.recommended_architecture;
      if (materialSelect && recommendedMaterial) materialSelect.value = recommendedMaterial;
      if (architectureSelect && recommendedArchitecture) architectureSelect.value = recommendedArchitecture;
      if (methodSelect && recommendedArchitecture && Array.from(methodSelect.options).some(option => option.value === recommendedArchitecture)) {
        methodSelect.value = recommendedArchitecture;
      }
      if (typeof updateArchitecturePanel === 'function') updateArchitecturePanel();
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

    function pointToSegmentDistance(point, a, b) {
      const vx = b[0] - a[0];
      const vy = b[1] - a[1];
      const wx = point.x - a[0];
      const wy = point.y - a[1];
      const c1 = vx * wx + vy * wy;
      if (c1 <= 0) return Math.hypot(point.x - a[0], point.y - a[1]);
      const c2 = vx * vx + vy * vy;
      if (c2 <= c1) return Math.hypot(point.x - b[0], point.y - b[1]);
      const t = c1 / c2;
      const px = a[0] + t * vx;
      const py = a[1] + t * vy;
      return Math.hypot(point.x - px, point.y - py);
    }

    function edgeName(edgeIndex) {
      return ['top', 'right', 'bottom', 'left'][edgeIndex] || 'edge';
    }

    // 2D line-segment intersection kernel (SolveSpace/CAD style math)
    function checkLineIntersection2D(p1, p2, p3, p4, epsilon = 1e-8) {
      const x1 = p1.x, y1 = p1.y;
      const x2 = p2.x, y2 = p2.y;
      const x3 = p3.x, y3 = p3.y;
      const x4 = p4.x, y4 = p4.y;

      const denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
      if (Math.abs(denominator) < epsilon) return null; // parallel/coincident

      const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator;
      const u = ((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator;

      if (t < 0 || t > 1 || u < 0 || u > 1) return null; // outside segment bounds

      return {
        x: x1 + t * (x2 - x1),
        y: y1 + t * (y2 - y1),
        z: 0,
        t,
        u,
      };
    }

    function computeSketchIntersections() {
      const hits = [];
      for (let i = 0; i < sketchLines.length; i++) {
        for (let j = i + 1; j < sketchLines.length; j++) {
          const a = sketchLines[i];
          const b = sketchLines[j];
          const hit = checkLineIntersection2D(a.start, a.end, b.start, b.end);
          if (hit) {
            hits.push({
              x: hit.x,
              y: hit.y,
              z: 0,
              lineA: a.id,
              lineB: b.id,
            });
          }
        }
      }
      return hits;
    }

    function snapToIntersectionForLine(start, cursorPoint, thresholdPx = 14) {
      let best = null;
      sketchLines.forEach(line => {
        const hit = checkLineIntersection2D(start, cursorPoint, line.start, line.end);
        if (!hit) return;
        const d = Math.hypot(cursorPoint.x - hit.x, cursorPoint.y - hit.y);
        if (d <= thresholdPx && (!best || d < best.distance)) {
          best = { x: hit.x, y: hit.y, z: 0, distance: d, lineId: line.id };
        }
      });
      return best;
    }

    function snapValue(value) {
      const snap = document.getElementById('snapGrid');
      return snap && snap.checked ? Math.round(value / 5) * 5 : value;
    }

    function flagMouseDown(event) {
      if (isViewerMode()) return;
      const point = canvasPoint(event);
      if (sketchTool === 'line') {
        if (!sketchLineStart) {
          sketchLineStart = { x: point.x, y: point.y };
          sketchLinePreview = { start: { ...sketchLineStart }, end: { x: point.x, y: point.y } };
          sketchSnapPoint = null;
          setAppStatus('LINE: pick second point.');
          drawFlags();
          return;
        }
        const endPoint = sketchSnapPoint
          ? { x: sketchSnapPoint.x, y: sketchSnapPoint.y }
          : { x: point.x, y: point.y };
        sketchLines.push({
          id: `ln_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
          start: { ...sketchLineStart },
          end: endPoint
        });
        sketchLineStart = null;
        sketchLinePreview = null;
        sketchSnapPoint = null;
        designHistoryCommit('sketch line added');
        setAppStatus('LINE committed.');
        drawFlags();
        return;
      }
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
        selectedFlagEdge = null;
        activeDrag = { kind: 'corner', ...best };
        drawFlags();
        return;
      }
      let bestEdge = null;
      flagGeometry.forEach((geometry, flagIndex) => {
        const pts = geometry.points;
        for (let edgeIndex = 0; edgeIndex < 4; edgeIndex++) {
          const a = pts[edgeIndex];
          const b = pts[(edgeIndex + 1) % 4];
          const d = pointToSegmentDistance(point, a, b);
          if (d < 10 && (!bestEdge || d < bestEdge.distance)) {
            bestEdge = { flagIndex, edgeIndex, distance: d };
          }
        }
      });
      if (bestEdge) {
        selectedFlagIndex = bestEdge.flagIndex;
        selectedFlagEdge = bestEdge.edgeIndex;
        activeDrag = null;
        drawFlags();
        return;
      }
      selectedFlagIndex = null;
      selectedFlagEdge = null;
      activeDrag = null;
      drawFlags();
    }

    function flagMouseMove(event) {
      if (isViewerMode()) return;
      if (sketchTool === 'line' && sketchLineStart) {
        const point = canvasPoint(event);
        const snap = snapToIntersectionForLine(sketchLineStart, point);
        if (snap) {
          sketchSnapPoint = { x: snap.x, y: snap.y, z: 0 };
          sketchLinePreview = { start: { ...sketchLineStart }, end: { x: snap.x, y: snap.y } };
          setAppStatus('LINE: snapped to intersection.');
        } else {
          sketchSnapPoint = null;
          sketchLinePreview = { start: { ...sketchLineStart }, end: { x: point.x, y: point.y } };
        }
        drawFlags();
        return;
      }
      if (!activeDrag) return;
      const point = canvasPoint(event);
      const geometry = flagGeometry[activeDrag.flagIndex];
      if (!geometry) return;
      const flag = flags[activeDrag.flagIndex];
      if (document.getElementById('lockDimensions').checked || flag.locked) return;
      if (activeDrag.kind === 'dimension') {
        selectedFlagEdge = null;
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
      selectedFlagEdge = null;
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
      sketchIntersections = computeSketchIntersections();
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
        if (selectedFlagIndex === index && Number.isInteger(selectedFlagEdge)) {
          const a = points[selectedFlagEdge];
          const b = points[(selectedFlagEdge + 1) % 4];
          ctx.strokeStyle = '#ff2d20';
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(a[0], a[1]);
          ctx.lineTo(b[0], b[1]);
          ctx.stroke();
          ctx.fillStyle = '#ffdbd8';
          ctx.font = '700 12px Arial';
          ctx.fillText(`edge: ${edgeName(selectedFlagEdge)}`, (a[0] + b[0]) / 2 - 24, (a[1] + b[1]) / 2 - 10);
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

      // SolveSpace-style sketch entities (2D line command) on top of flag workspace
      if (sketchLines.length) {
        ctx.save();
        ctx.strokeStyle = '#78e3ff';
        ctx.lineWidth = 2;
        sketchLines.forEach(line => {
          ctx.beginPath();
          ctx.moveTo(line.start.x, line.start.y);
          ctx.lineTo(line.end.x, line.end.y);
          ctx.stroke();
        });
        ctx.restore();
      }
      if (sketchIntersections.length) {
        ctx.save();
        ctx.fillStyle = '#ffd84d';
        ctx.strokeStyle = '#8a6a00';
        ctx.lineWidth = 1.5;
        sketchIntersections.forEach((pt, idx) => {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 4.2, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          if (idx < 8) {
            ctx.fillStyle = '#ffeaa0';
            ctx.font = '700 10px Arial';
            ctx.fillText(`I${idx + 1}`, pt.x + 6, pt.y - 6);
            ctx.fillStyle = '#ffd84d';
          }
        });
        ctx.restore();
      }
      if (sketchLinePreview) {
        ctx.save();
        ctx.setLineDash([6, 6]);
        ctx.strokeStyle = '#ff4fa8';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(sketchLinePreview.start.x, sketchLinePreview.start.y);
        ctx.lineTo(sketchLinePreview.end.x, sketchLinePreview.end.y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
      if (sketchSnapPoint) {
        ctx.save();
        ctx.strokeStyle = '#30ff7a';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sketchSnapPoint.x, sketchSnapPoint.y, 5.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(sketchSnapPoint.x - 8, sketchSnapPoint.y);
        ctx.lineTo(sketchSnapPoint.x + 8, sketchSnapPoint.y);
        ctx.moveTo(sketchSnapPoint.x, sketchSnapPoint.y - 8);
        ctx.lineTo(sketchSnapPoint.x, sketchSnapPoint.y + 8);
        ctx.stroke();
        ctx.restore();
      }

      const totalArea = flags.reduce((sum, f) => sum + ((f.root + f.tip) / 2) * f.length, 0);
      const longest = Math.max(...flags.map(f => f.length), 0);
      document.getElementById('flagCount').textContent = String(flags.length);
      document.getElementById('flagArea').textContent = Math.round(totalArea).toLocaleString() + ' mm2';
      document.getElementById('flagLongest').textContent = longest + ' mm';
      document.getElementById('selectedFlagLabel').textContent =
        selectedFlagIndex === null
          ? `Tool: ${sketchTool}${sketchTool === 'line' && sketchLineStart ? ' | LINE: pick second point' : ''} | No flag selected`
          : `Tool: ${sketchTool}${sketchTool === 'line' && sketchLineStart ? ' | LINE: pick second point' : ''} | Selected: ${flags[selectedFlagIndex].name}`;
      const hCount = flags.length;
      const vCount = flags.length * 2;
      const dimCount = flags.length * 3;
      const intersectionCount =
        (typeof computeSketchIntersections === 'function')
          ? computeSketchIntersections().length
          : 0;
      const constraintReadout = document.getElementById('constraintReadout');
      const sideSelection = document.getElementById('sideSelection');
      if (constraintReadout) constraintReadout.textContent = `H: ${hCount} | V: ${vCount} | DIM: ${dimCount} | INT: ${intersectionCount}`;
      if (sideSelection) {
        sideSelection.textContent = selectedFlagIndex === null
          ? `Tool: ${sketchTool}`
          : `${flags[selectedFlagIndex].name} | L ${flags[selectedFlagIndex].length} | root ${flags[selectedFlagIndex].root} | tip ${flags[selectedFlagIndex].tip}${Number.isInteger(selectedFlagEdge) ? ` | edge ${edgeName(selectedFlagEdge)}` : ''}`;
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
        const baseReading = auditorCpmReading(Number(zone.cpm));
        const unclampedAdjusted = baseReading + localBoost;
        const adjustedReading = auditorCpmReading(unclampedAdjusted);
        const section = zone.section || cpmSectionForStation(zone.station_in);
        return {
          ...zone,
          base_cpm: zone.cpm,
          raw_model_cpm: unclampedAdjusted,
          tape_boost: localBoost,
          section,
          cpm_class: cpmRangeLabel(section, adjustedReading),
          cpm: adjustedReading,
          analyzer_limited: Boolean(zone.analyzer_limited) || unclampedAdjusted > 999 || unclampedAdjusted < 0
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
        z => `<tr><td>${z.station_in}"</td><td>${zoneCpmDisplay(z)}</td></tr>`
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
        material_library: materialLibrary,
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
        if (project.material_library && typeof project.material_library === 'object') {
          loadMaterialLibraryFromObject(project.material_library);
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
      const sx = canvas.width / Math.max(1, rect.width);
      const sy = canvas.height / Math.max(1, rect.height);
      return {
        x: (event.clientX - rect.left) * sx,
        y: (event.clientY - rect.top) * sy
      };
    }

    function cadDraftSnapStep() {
      const input = document.getElementById('cadDraftSnapStep');
      const value = Number(input?.value || 10);
      return Number.isFinite(value) && value > 0 ? value : 10;
    }

    function cadDraftSnapEnabled() {
      const input = document.getElementById('cadDraftSnap');
      return Boolean(input && input.checked);
    }

    function cadDraftObjectSnapEnabled() {
      const ep = document.getElementById('cadSnapEndpoint')?.checked;
      const mp = document.getElementById('cadSnapMidpoint')?.checked;
      const ip = document.getElementById('cadSnapIntersection')?.checked;
      return Boolean(ep || mp || ip);
    }

    function cadLineIntersection(a, b, c, d) {
      const x1 = a.x, y1 = a.y;
      const x2 = b.x, y2 = b.y;
      const x3 = c.x, y3 = c.y;
      const x4 = d.x, y4 = d.y;
      const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
      if (Math.abs(denom) < 1e-8) return null;
      const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
      const u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom;
      if (t < 0 || t > 1 || u < 0 || u > 1) return null;
      return { x: x1 + t * (x2 - x1), y: y1 + t * (y2 - y1) };
    }

    function cadDraftSnapCandidates() {
      const candidates = [];
      const snapEndpoint = Boolean(document.getElementById('cadSnapEndpoint')?.checked);
      const snapMidpoint = Boolean(document.getElementById('cadSnapMidpoint')?.checked);
      const snapIntersection = Boolean(document.getElementById('cadSnapIntersection')?.checked);

      cadDraftEntities.forEach(entity => {
        if (entity.type === 'line' || entity.type === 'rect' || entity.type === 'triangle') {
          const p1 = { x: entity.x1, y: entity.y1 };
          const p2 = { x: entity.x2, y: entity.y2 };
          if (snapEndpoint) {
            candidates.push({ x: p1.x, y: p1.y, kind: 'endpoint' }, { x: p2.x, y: p2.y, kind: 'endpoint' });
          }
          if (snapMidpoint) {
            candidates.push({ x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2, kind: 'midpoint' });
          }
        } else if (entity.type === 'circle') {
          if (snapEndpoint || snapMidpoint) {
            candidates.push({ x: entity.x, y: entity.y, kind: 'center' });
          }
        }
      });

      if (snapIntersection) {
        const lines = cadDraftEntities.filter(e => e.type === 'line');
        for (let i = 0; i < lines.length; i++) {
          for (let j = i + 1; j < lines.length; j++) {
            const a = { x: lines[i].x1, y: lines[i].y1 };
            const b = { x: lines[i].x2, y: lines[i].y2 };
            const c = { x: lines[j].x1, y: lines[j].y1 };
            const d = { x: lines[j].x2, y: lines[j].y2 };
            const hit = cadLineIntersection(a, b, c, d);
            if (hit) candidates.push({ x: hit.x, y: hit.y, kind: 'intersection' });
          }
        }
      }

      return candidates;
    }

    function cadDraftResolveSnapPoint(rawPoint) {
      let point = cadDraftSnapPoint(rawPoint);
      let kind = cadDraftSnapEnabled() ? 'grid' : 'none';

      if (!cadDraftObjectSnapEnabled()) return { point, kind };
      const candidates = cadDraftSnapCandidates();
      if (!candidates.length) return { point, kind };

      const threshold = 14;
      let best = null;
      let bestDistance = Infinity;
      candidates.forEach(candidate => {
        const d = Math.hypot(candidate.x - rawPoint.x, candidate.y - rawPoint.y);
        if (d < bestDistance && d <= threshold) {
          bestDistance = d;
          best = candidate;
        }
      });
      if (best) return { point: { x: best.x, y: best.y }, kind: best.kind };
      return { point, kind };
    }

    function cadDraftSnapPoint(p) {
      if (!cadDraftSnapEnabled()) return { x: p.x, y: p.y };
      const step = cadDraftSnapStep();
      return {
        x: Math.round(p.x / step) * step,
        y: Math.round(p.y / step) * step
      };
    }

    function cadDraftApplyOrtho(start, p, shiftKey) {
      if (!shiftKey) return { x: p.x, y: p.y };
      const dx = p.x - start.x;
      const dy = p.y - start.y;
      if (Math.abs(dx) >= Math.abs(dy)) {
        return { x: p.x, y: start.y };
      }
      return { x: start.x, y: p.y };
    }

    function normalizeCadDraftTool(tool) {
      const allowed = new Set(['select', 'line', 'rect', 'circle', 'triangle']);
      if (allowed.has(tool)) return tool;
      return 'line';
    }

    function setCadDraftTool(tool, button) {
      if (isViewerMode()) return;
      cadDraftTool = normalizeCadDraftTool(tool);
      document.querySelectorAll('#cad3dView #cadDraftSelectBtn, #cad3dView #cadDraftLineBtn, #cad3dView #cadDraftRectBtn, #cad3dView #cadDraftCircleBtn, #cad3dView #cadDraftTriangleBtn')
        .forEach(item => item.classList.remove('active'));
      if (button) button.classList.add('active');
      if (!button) {
        const fallbackBtn = document.getElementById(
          cadDraftTool === 'select' ? 'cadDraftSelectBtn' :
          cadDraftTool === 'line' ? 'cadDraftLineBtn' :
          cadDraftTool === 'rect' ? 'cadDraftRectBtn' :
          cadDraftTool === 'circle' ? 'cadDraftCircleBtn' : 'cadDraftTriangleBtn'
        );
        if (fallbackBtn) fallbackBtn.classList.add('active');
      }
      const status = document.getElementById('cadDraftStatus');
      if (status) status.textContent = `Tool: ${cadDraftTool}`;
      drawCad3d();
    }

    function hardBindCadLineTool() {
      const lineBtn = document.getElementById('cadDraftLineBtn');
      if (!lineBtn) return false;
      lineBtn.onclick = null;
      lineBtn.addEventListener('click', event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        safeInvoke('cadDraftLineBtn', () => setCadDraftTool('line', lineBtn));
      }, true);
      return true;
    }

    function bindCadLineHotkeys() {
      document.removeEventListener('keydown', cadLineHotkeyHandler, true);
      document.addEventListener('keydown', cadLineHotkeyHandler, true);
    }

    function cadLineHotkeyHandler(event) {
      const key = String(event.key || '').toLowerCase();
      if (key !== 'l') return;
      const active = document.activeElement;
      const tag = String(active?.tagName || '').toLowerCase();
      const isTyping = tag === 'input' || tag === 'textarea' || active?.isContentEditable;
      if (isTyping) return;
      const cadVisible = !document.getElementById('cad3dView')?.classList.contains('hidden');
      if (!cadVisible) return;
      event.preventDefault();
      setCadDraftTool('line');
      setAppStatus('Line tool locked in (hotkey L).');
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
      if (entity.type === 'line') {
        const x1 = entity.x1;
        const y1 = entity.y1;
        const x2 = entity.x2;
        const y2 = entity.y2;
        const vx = x2 - x1;
        const vy = y2 - y1;
        const wx = p.x - x1;
        const wy = p.y - y1;
        const c1 = vx * wx + vy * wy;
        const c2 = vx * vx + vy * vy;
        const t = c2 > 0 ? Math.max(0, Math.min(1, c1 / c2)) : 0;
        const px = x1 + t * vx;
        const py = y1 + t * vy;
        return Math.hypot(p.x - px, p.y - py) <= 7;
      }
      const x1 = Math.min(entity.x1, entity.x2);
      const x2 = Math.max(entity.x1, entity.x2);
      const y1 = Math.min(entity.y1, entity.y2);
      const y2 = Math.max(entity.y1, entity.y2);
      return p.x >= x1 - 8 && p.x <= x2 + 8 && p.y >= y1 - 8 && p.y <= y2 + 8;
    }

    function cad3dMouseDown(event) {
      if (isViewerMode()) return;
      cadDraftTool = normalizeCadDraftTool(cadDraftTool);
      const raw = cadCanvasPoint(event);
      const snap = cadDraftResolveSnapPoint(raw);
      const p = cadDraftTool === 'select' ? raw : snap.point;
      cadDraftCursor = raw;
      cadDraftSnapCursor = snap.point;
      cadDraftSnapKind = cadDraftTool === 'select' ? 'none' : snap.kind;
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
      cadDraftTool = normalizeCadDraftTool(cadDraftTool);
      const raw = cadCanvasPoint(event);
      const snap = cadDraftResolveSnapPoint(raw);
      const p = snap.point;
      cadDraftCursor = raw;
      cadDraftSnapCursor = p;
      cadDraftSnapKind = snap.kind;
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
      const endpoint = cadDraftPreview.type === 'line'
        ? cadDraftApplyOrtho(cadDraftStart || { x: cadDraftPreview.x1, y: cadDraftPreview.y1 }, p, Boolean(event.shiftKey))
        : p;
      cadDraftPreview.x2 = endpoint.x;
      cadDraftPreview.y2 = endpoint.y;
      drawCad3d();
    }

    function cad3dMouseUp() {
      cadDraftTool = normalizeCadDraftTool(cadDraftTool);
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
      cadDraftSnapCursor = null;
      cadDraftSnapKind = 'none';
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
      cadDraftCursor = null;
      cadDraftSnapCursor = null;
      cadDraftSnapKind = 'none';
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
      if ((cadDraftSnapEnabled() || cadDraftObjectSnapEnabled()) && cadDraftSnapCursor) {
        ctx.save();
        const color = cadDraftSnapKind === 'intersection' ? '#ffd84d'
          : cadDraftSnapKind === 'midpoint' ? '#8fd3ff'
          : cadDraftSnapKind === 'endpoint' ? '#56f2b0'
          : '#56f2b0';
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(cadDraftSnapCursor.x, cadDraftSnapCursor.y, 5.5, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(cadDraftSnapCursor.x - 8, cadDraftSnapCursor.y);
        ctx.lineTo(cadDraftSnapCursor.x + 8, cadDraftSnapCursor.y);
        ctx.moveTo(cadDraftSnapCursor.x, cadDraftSnapCursor.y - 8);
        ctx.lineTo(cadDraftSnapCursor.x, cadDraftSnapCursor.y + 8);
        ctx.stroke();
        ctx.restore();
      }
      const status = document.getElementById('cadDraftStatus');
      if (status) {
        const step = cadDraftSnapStep();
        const snapState = cadDraftSnapEnabled() ? `snap ${step}px` : 'snap off';
        const snapMode = cadDraftSnapKind && cadDraftSnapKind !== 'none' ? ` (${cadDraftSnapKind})` : '';
        const cursorState = cadDraftCursor ? ` | XY ${Math.round(cadDraftCursor.x)},${Math.round(cadDraftCursor.y)}` : '';
        status.textContent = cadDraftSelectedIndex === null
          ? `Tool: ${cadDraftTool} | ${snapState}${snapMode} | Entities: ${cadDraftEntities.length}${cursorState}`
          : `Tool: ${cadDraftTool} | ${snapState}${snapMode} | Selected: #${cadDraftSelectedIndex + 1}${cursorState}`;
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
      if (showGrid) {
        const gridStep = Math.max(4, cadDraftSnapStep());
        const majorEvery = 5;
        for (let x = 0, i = 0; x <= canvas.width; x += gridStep, i++) {
          const major = i % majorEvery === 0;
          ctx.strokeStyle = major ? (dark ? '#2a4f49' : '#bcc5de') : (dark ? '#1a2f2b' : '#dde3f3');
          ctx.lineWidth = major ? 1 : 0.7;
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, canvas.height);
          ctx.stroke();
        }
        for (let y = 0, i = 0; y <= canvas.height; y += gridStep, i++) {
          const major = i % majorEvery === 0;
          ctx.strokeStyle = major ? (dark ? '#2a4f49' : '#bcc5de') : (dark ? '#1a2f2b' : '#dde3f3');
          ctx.lineWidth = major ? 1 : 0.7;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(canvas.width, y);
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

    function downloadManufacturerPack(button) {
      if (!ensureExportReady('Manufacturer handoff export', true)) return;
      flashButton(button, 'Exported');
      const pack = latest?.manufacturer_handoff || {};
      const blob = new Blob([JSON.stringify(pack, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ae-shaftcad-manufacturer-handoff.json';
      a.click();
      URL.revokeObjectURL(url);
      writeCadConsole('Exported manufacturer handoff package.');
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
        shaftDataTab: () => showView('shaftData'),
        cameraTab: () => showView('camera'),
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
        exportMfgPackBtn: button => downloadManufacturerPack(button),
        materialAddBtn: button => addMaterial(button),
        materialDuplicateBtn: button => duplicateSelectedMaterial(button),
        materialDeleteBtn: button => deleteSelectedMaterial(button),
        materialExportBtn: button => exportMaterials(button),
        materialImportBtn: () => document.getElementById('materialFile')?.click(),
        shaftDataAnalyzeBtn: button => analyzeShaftData(button),
        shaftDataImportBtn: button => importCurrentModelToShaftData(button),
        shaftDataApplyBtn: button => applyShaftDataTarget(button),
        cameraStartBtn: button => startCameraFit(button),
        cameraCaptureBtn: button => startCameraSwingCapture(button),
        cameraAiReviewBtn: button => aiReviewCapturedSwings(button),
        cameraStopBtn: button => stopCameraFit(button),
        cameraManualBtn: button => analyzeManualSwing(button),
        cameraToFitBtn: button => sendCameraToFit(button),
        cameraToCadBtn: button => applyCameraToCad(button),
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
      const lineLocked = hardBindCadLineTool();
      bindCadLineHotkeys();
      if (typeof document.removeEventListener === 'function') {
        document.removeEventListener('click', emergencyClickRouter, true);
      }
      if (typeof document.addEventListener === 'function') {
        document.addEventListener('click', emergencyClickRouter, true);
      }
      setAppStatus(`AE boot OK: JavaScript loaded, buttons bound, emergency click router active.${lineLocked ? ' Line tool hard-locked.' : ''}`);
      writeCadConsole(`Button safety bootstrap active: id bindings loaded. Emergency click router active.${lineLocked ? ' CAD line tool hard-bind active.' : ' CAD line button missing.'}`);
      const strictToggle = document.getElementById('strictModeToggle');
      if (strictToggle) strictToggle.checked = debugState.strictMode;
      runButtonAudit();
    }

    window.showView = showView;
    window.setSketchTool = setSketchTool;
    window.handleSketchMenu = handleSketchMenu;
    window.run = run;
    window.analyzeShaftData = analyzeShaftData;
    window.importCurrentModelToShaftData = importCurrentModelToShaftData;
    window.applyShaftDataTarget = applyShaftDataTarget;
    window.startCameraFit = startCameraFit;
    window.startCameraSwingCapture = startCameraSwingCapture;
    window.aiReviewCapturedSwings = aiReviewCapturedSwings;
    window.stopCameraFit = stopCameraFit;
    window.analyzeManualSwing = analyzeManualSwing;
    window.sendCameraToFit = sendCameraToFit;
    window.applyCameraToCad = applyCameraToCad;
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
    window.updateMaterialField = updateMaterialField;
    window.loadMaterialsFile = loadMaterialsFile;
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
    window.downloadManufacturerPack = downloadManufacturerPack;
    window.undoDesignHistory = undoDesignHistory;
    window.redoDesignHistory = redoDesignHistory;
    window.setStrictMode = setStrictMode;
    window.runButtonAudit = runButtonAudit;
    window.bootstrapButtons = bootstrapButtons;

    function bootApp() {
      setAppStatus('AE boot starting: wiring controls and running first analysis...');
      if (!Object.keys(materialLibrary).length) {
        loadMaterialLibraryFromObject(defaultMaterialLibrary());
      }
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
    material_e1_pa: float | None = None,
    material_e2_pa: float | None = None,
    material_g12_pa: float | None = None,
    material_nu12: float | None = None,
    material_density_kg_m3: float | None = None,
    material_cost_per_kg: float | None = None,
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
        material_e1_pa=material_e1_pa,
        material_e2_pa=material_e2_pa,
        material_g12_pa=material_g12_pa,
        material_nu12=material_nu12,
        material_density_kg_m3=material_density_kg_m3,
        material_cost_per_kg=material_cost_per_kg,
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


@app.get("/api/manufacturing-handoff")
def api_manufacturing_handoff(
    target_cpm: float = 255.0,
    head_weight_g: float = 205.0,
    material_name: str = "Mitsubishi MR70",
    method_key: str = "roll_wrapped",
    wrap_angle_deg: float = 45.0,
    architecture_mode: str = "flag_wrap",
    head_speed_mph: float = 105.0,
) -> dict[str, Any]:
    analysis = analyze_shaft(
        target_cpm=target_cpm,
        head_weight_g=head_weight_g,
        material_name=material_name,
        method_key=method_key,
        wrap_angle_deg=wrap_angle_deg,
        architecture_mode=architecture_mode,
        head_speed_mph=head_speed_mph,
    )
    return analysis["manufacturer_handoff"]


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


@app.post("/api/swing-to-shaft")
def api_swing_to_shaft(payload: dict[str, Any]) -> dict[str, Any]:
    return swing_capture_to_fit(payload)


@app.post("/api/diy-driver-tuneup")
def api_diy_driver_tuneup(payload: dict[str, Any]) -> dict[str, Any]:
    return diy_driver_tuneup(payload)


@app.post("/api/visual-fitting")
def api_visual_fitting(payload: dict[str, Any]) -> dict[str, Any]:
    return visual_fitting_read(payload)


@app.post("/api/launch-rollout")
def api_launch_rollout(payload: dict[str, Any]) -> dict[str, Any]:
    return driver_launch_rollout_optimizer(payload)


@app.post("/api/static-length-lie")
def api_static_length_lie(payload: dict[str, Any]) -> dict[str, Any]:
    return static_length_lie_fit(payload)


@app.post("/api/shaft-sensation-quality")
def api_shaft_sensation_quality(payload: dict[str, Any]) -> dict[str, Any]:
    return shaft_sensation_quality_read(payload)


@app.post("/api/wishon-profile-guard")
def api_wishon_profile_guard(payload: dict[str, Any]) -> dict[str, Any]:
    return wishon_profile_guard(payload)


@app.post("/api/fitting-interview")
def api_fitting_interview(payload: dict[str, Any]) -> dict[str, Any]:
    return fitting_interview_read(payload)


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
