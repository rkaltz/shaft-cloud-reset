"""Dependency-light smoke checks for AE ShaftCAD Studio."""

from __future__ import annotations

import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main_check() -> None:
    html = main.home()
    require("AI Shaft Builder Brief" in html, "Fit-to-build UI is missing")
    require("Camera Fit" in html, "Camera fitting tab is missing")
    require("startCameraFit" in html, "Camera fitting controls are not wired")
    require("cameraAttackAngle" in html, "Camera fitting attack-angle input is missing")
    require("cameraShaftLoad" in html, "Camera fitting shaft-load input is missing")
    require("Why This Shaft" in html, "Camera fitting explanation panel is missing")
    require("Manufacturing Zones" in html, "Camera fitting manufacturing zones panel is missing")
    require("DIY Driver Tune-Up" in html, "DIY driver tune-up panel is missing")
    require("cameraImpactPattern" in html, "DIY impact-pattern input is missing")
    require("Visual Fitting Read" in html, "Visual fitting panel is missing")
    require("cameraVisualTransition" in html, "Visual fitting transition input is missing")
    require("Starter Shaft Database Matches" in html, "Camera fitting database panel is missing")
    require("analyzer cap; model" in html, "Auditor cap wording is missing")

    design = main.analyze_shaft()
    require(math.isfinite(design["overall_cpm"]), "overall CPM is not finite")
    spec = design["driver_shaft_spec_check"]
    require(spec["fit_for_driver_baseline"], f"default driver shaft spec drifted: {spec['flags']}")
    require(abs(spec["raw_length_in"] - 46.0) < 0.05, "default raw driver shaft length should be 46 inches")
    require(abs(spec["tip_od_in"] - 0.335) < 0.003, "default driver tip OD should be 0.335 inch")
    require(0.590 <= spec["butt_od_in"] <= 0.600, "default driver butt OD should be 0.590-0.600 inch")
    require(45.0 <= spec["mass_g"] <= 85.0, "default driver shaft mass should be in the common 45-85g range")
    require(0.0 <= design["zone_profile"][-1]["cpm"] <= 999.0, "11-inch CPM exceeds Auditor range")
    require(design["zone_profile"][-1]["analyzer_limited"], "11-inch overflow is not flagged")
    require(
        design["zone_profile"][-1]["raw_model_cpm"] > design["zone_profile"][-1]["cpm"],
        "raw model CPM should preserve unclamped simulation value",
    )
    require(len(design["behavior_intelligence"]["cpm_values"]) == 8, "behavior profile should include butt plus 7 stations")
    require("shaft inner diameter stations" in design["gcode"], "mandrel G-code should be based on shaft ID")
    require("segment[\"id_mm\"]" in design["cadquery_step_recipe"], "STEP recipe should generate mandrel from ID stations")

    handoff = design["manufacturer_handoff"]
    require(handoff["readiness_level"] == "prototype_quote_and_first_article", "handoff readiness level drifted")
    require(handoff["driver_shaft_spec_check"]["fit_for_driver_baseline"], "handoff lost driver shaft spec validation")
    require(handoff["mandrel_geometry"]["basis"] == "shaft inner diameter stations", "handoff mandrel basis is wrong")
    require(len(handoff["ply_schedule"]) >= 16, "handoff ply schedule is too thin")
    require(len(handoff["flag_templates"]) >= 16, "handoff flag template schedule is missing")
    require("finished_cpm" in handoff["tolerances"], "handoff CPM tolerance is missing")
    require(len(handoff["qc_checklist"]) >= 8, "handoff QC checklist is incomplete")

    fit = main.fit_target_from_swing(
        speed_mph=112.0,
        launch_deg=16.0,
        spin_rpm=3200.0,
        transition="Hard",
        feel="Stable mid",
    )
    require(fit["builder_brief"]["recommended_material"] == "Toray M40J", "hard-transition material recommendation drifted")
    require(fit["builder_brief"]["recommended_architecture"] == "braid_tape_braid", "hard-transition architecture drifted")
    require(fit["cad_translation"]["bias_pair_deg"][0] == fit["wrap_angle_deg"], "Fit/CAD wrap transfer mismatch")

    swing_fit = main.swing_capture_to_fit(
        {
            "source": "smoke-camera",
            "speed_mph": 112.0,
            "tempo_seconds": 0.88,
            "transition_load": 74.0,
            "release_score": 68.0,
            "face_closure_rate": 42.0,
            "attack_angle_deg": -1.2,
            "face_to_path_deg": 0.4,
            "shaft_load_index": 80.0,
            "hand_path": "shallow",
            "impact_pattern": "heel",
            "vertical_impact": "low",
            "head_weight_feel": "light",
            "current_length_in": 45.5,
            "gripped_down_in": 0.5,
            "pw_shaft_weight_g": 120.0,
            "added_head_weight_g": 2.5,
            "visual_tempo_control": "slow/insecure",
            "visual_rhythm_float": "no float",
            "visual_transition_move": "jump start",
            "visual_commitment": "overplay",
            "visual_one_arm_shoulder": "drop",
            "visual_power_leaks": "sparks",
            "launch_deg": 13.2,
            "spin_rpm": 2500.0,
            "motion_quality": 82.0,
            "motion_score": 78.0,
        }
    )
    require(swing_fit["inputs"]["transition"] == "Hard", "camera swing transition derivation drifted")
    require(swing_fit["swing_capture"]["confidence"] == "usable", "camera swing confidence drifted")
    require(swing_fit["swing_capture"]["shaft_load_index"] == 80.0, "camera swing load index was not preserved")
    require(len(swing_fit["why_this_fit"]) >= 5, "camera swing explanation is incomplete")
    require(len(swing_fit["manufacturing_zones"]) >= 4, "camera swing manufacturing zones are incomplete")
    require(len(swing_fit["proof_requirements"]) >= 5, "camera swing proof checklist is incomplete")
    require(swing_fit["shaft_database_matches"], "camera swing database matches are missing")
    require(swing_fit["diy_driver_tuneup"]["effective_test_length_in"] == 45.0, "DIY driver test length drifted")
    require(
        any("shorter playing length" in item for item in swing_fit["diy_driver_tuneup"]["actions"]),
        "DIY driver tune-up did not react to heel impact",
    )
    require(swing_fit["visual_fitting"]["diagnosis"], "Visual fitting diagnosis is missing")
    require(
        any("jump-start" in item for item in swing_fit["visual_fitting"]["diagnosis"]),
        "Visual fitting did not react to jump-start transition",
    )
    require(swing_fit["cad_translation"]["recommended_architecture"] == "braid_tape_braid", "camera swing CAD translation drifted")

    tuneup = main.diy_driver_tuneup(
        {
            "impact_pattern": "toe",
            "vertical_impact": "high",
            "head_weight_feel": "heavy",
            "current_length_in": 45.75,
            "gripped_down_in": 0.25,
            "pw_shaft_weight_g": 130.0,
        }
    )
    require(tuneup["recommended_driver_shaft_weight_g"] == 65.0, "PW-to-driver shaft weight rule drifted")
    require(tuneup["warnings"], "DIY tune-up should warn on toe/heavy combination")

    visual = main.visual_fitting_read(
        {
            "visual_tempo_control": "slow/insecure",
            "visual_rhythm_float": "no float",
            "visual_transition_move": "jump start",
            "visual_commitment": "weak",
            "visual_one_arm_shoulder": "drop",
            "visual_power_leaks": "multiple bursts",
        }
    )
    require(len(visual["fitting_moves"]) >= 3, "Visual fitting moves are incomplete")
    require(any("more shaft weight" in item for item in visual["fitting_moves"]), "Visual fitting missed too-light/weak read")
    require(any("Lower shaft/total weight" in item for item in visual["fitting_moves"]), "Visual fitting missed total-weight upper limit")

    direct_handoff = main.api_manufacturing_handoff()
    require(direct_handoff["package"] == "AE ShaftCAD Manufacturer Handoff Pack", "handoff endpoint payload failed")

    print("AE ShaftCAD smoke checks passed")


if __name__ == "__main__":
    main_check()
