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
    require("Shaft Data" in html, "Shaft data tab is missing")
    require("Auditor Frequency Analyzer" in html, "Auditor shaft data page is missing")
    require("Standalone Butt Frequency" in html, "Standalone butt frequency input is missing")
    require("shaftButtFrequency" in html, "Butt frequency field is missing")
    require("auditorCaptureInput" in html, "Auditor quick capture input is missing")
    require("captureAuditorReading" in html, "Auditor Enter-to-capture logic is missing")
    require("shaftCpm41" in html, "41-inch Auditor CPM input is missing")
    require("shaftCpm11" in html, "11-inch Auditor CPM input is missing")
    require("analyzeShaftData" in html, "Shaft data analyzer logic is missing")
    require("butt_frequency_cpm" in html, "Standalone butt frequency is not saved in profile packet")
    require("Use Butt CPM as Target" in html, "Measured shaft target transfer is missing")
    require("Camera Fit" in html, "Camera fitting tab is missing")
    require("Pre-Fit Interview" in html, "Pre-fit interview form is missing")
    require("Camera 1 - Face On" in html, "Face-on camera lane is missing")
    require("cameraVideoFace" in html, "Face-on camera video element is missing")
    require("Camera 2 - Down the Line" in html, "Down-line camera lane is missing")
    require("cameraVideoDownLine" in html, "Down-line camera video element is missing")
    require("cameraAiReviewBtn" in html, "AI swing review button is missing")
    require("camera-focus" in html, "Camera focus layout is missing")
    require("buildCapturedSwingAiReview" in html, "AI swing review logic is missing")
    require("interviewClubType" in html, "Interview fitting type input is missing")
    require("interviewTendencies" in html, "Interview tendencies checklist is missing")
    require("Fitter Starting Direction" in html, "Fitter starting direction panel is missing")
    require("startCameraFit" in html, "Camera fitting controls are not wired")
    require("cameraAttackAngle" in html, "Camera fitting attack-angle input is missing")
    require("cameraShaftLoad" in html, "Camera fitting shaft-load input is missing")
    require("Why This Shaft" in html, "Camera fitting explanation panel is missing")
    require("Manufacturing Zones" in html, "Camera fitting manufacturing zones panel is missing")
    require("DIY Driver Tune-Up" in html, "DIY driver tune-up panel is missing")
    require("cameraImpactPattern" in html, "DIY impact-pattern input is missing")
    require("Visual Fitting Read" in html, "Visual fitting panel is missing")
    require("cameraVisualTransition" in html, "Visual fitting transition input is missing")
    require("Launch / Rollout Optimizer" in html, "Launch rollout optimizer panel is missing")
    require("cameraPwCarry" in html, "PW carry input is missing")
    require("Static Length / Lie Start" in html, "Static length/lie panel is missing")
    require("cameraWristFloor" in html, "Wrist-to-floor input is missing")
    require("Shaft Sensation / Quality" in html, "Shaft sensation/quality panel is missing")
    require("cameraImpactSensation" in html, "Impact sensation input is missing")
    require("Wishon Profile / Torque Guard" in html, "Wishon profile guard panel is missing")
    require("cameraCurrentTorque" in html, "Current torque input is missing")
    require("Starter Shaft Database Matches" in html, "Camera fitting database panel is missing")
    require("analyzer cap; model" in html, "Auditor cap wording is missing")
    require("1 flex =" in html, "CPM section flex-delta display is missing")
    require("Prepreg Cut Flag Layout" in html, "Cut-ready flag layout title is missing")
    require("drawFlagCutFace" in html, "Cut-ready flag renderer is missing")
    require("ROOT CUT" in html, "Root cut edge labels are missing")
    require("flagAngleLabel" in html, "Fiber direction labels are missing")

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
    require(design["zone_profile"][0]["section"] == "Butt", "41-inch station should classify as butt section")
    require(design["zone_profile"][2]["section"] == "Mid", "31-inch station should classify as mid section")
    require(design["zone_profile"][-1]["section"] == "Tip", "11-inch station should classify as tip section")
    require(design["zone_profile"][0]["full_flex_delta_cpm"] == 10.0, "Butt full-flex CPM delta drifted")
    require(design["zone_profile"][2]["full_flex_delta_cpm"] == 25.0, "Mid full-flex CPM delta drifted")
    require(design["zone_profile"][-1]["full_flex_delta_cpm"] == 40.0, "Tip full-flex CPM delta drifted")
    require(
        design["zone_profile"][-1]["raw_model_cpm"] > design["zone_profile"][-1]["cpm"],
        "raw model CPM should preserve unclamped simulation value",
    )
    require(len(design["behavior_intelligence"]["cpm_values"]) == 8, "behavior profile should include butt plus 7 stations")
    require(
        "butt about 10 CPM" in design["behavior_intelligence"]["cpm_range_rule"],
        "Behavior intelligence lost CPM section flex rule",
    )
    require(
        design["behavior_intelligence"]["cpm_section_ranges"][2]["full_flex_delta_cpm"] == 40.0,
        "Tip section reference range drifted",
    )
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
            "height_in": 72.0,
            "wrist_to_floor_in": 36.0,
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
            "carry_yards": 250.0,
            "total_yards": 280.0,
            "pw_carry_yards": 123.0,
            "impact_sensation": "harsh",
            "shot_miss_direction": "right",
            "shot_quality_score": 4.0,
            "shot_accuracy_score": 4.0,
            "shaft_preference_score": 3.0,
            "current_flex_label": "S",
            "current_shaft_weight_g": 82.0,
            "current_torque_deg": 5.2,
            "fitting_interview": {
                "club_type": "driver",
                "physical_pain": "yes",
                "physical_limitations": "no",
                "poor_shot_tendencies": ["slice it right", "very inconsistent"],
                "personal_wants": ["hit the ball longer", "more consistent"],
                "confidence": "no confidence",
                "club_weight_feel": "too heavy",
                "immediate_goal": "find out if current club is right",
                "handicap_trend": "going up",
            },
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
    require(swing_fit["launch_rollout_optimizer"]["target_rollout_pct"] == 9.8, "Launch rollout speed target drifted")
    require(
        swing_fit["launch_rollout_optimizer"]["rollout_read"] == "rollout is inside the target window",
        "Launch rollout optimizer did not classify measured carry/roll correctly",
    )
    require(swing_fit["static_length_lie"]["recommended_7i_length_in"] == 37.75, "Static length recommendation drifted")
    require(swing_fit["static_length_lie"]["initial_lie_delta_deg"] == 1, "Static lie recommendation drifted")
    require(swing_fit["shaft_sensation_quality"]["recommendations"], "Shaft sensation recommendations are missing")
    require(
        any("softer" in item for item in swing_fit["shaft_sensation_quality"]["recommendations"]),
        "Shaft sensation read missed harsh/stiff softer-profile recommendation",
    )
    require(swing_fit["wishon_profile_guard"]["torque_notes"], "Wishon torque notes are missing")
    require(
        any("7-point" in item for item in swing_fit["wishon_profile_guard"]["findings"]),
        "Wishon profile finding is missing",
    )
    require(
        any("comfort and repeatability" in item for item in swing_fit["fitting_interview"]["start_points"]),
        "Fitting interview did not react to pain/limitations",
    )
    require(
        any("Driver path" in item for item in swing_fit["fitting_interview"]["start_points"]),
        "Fitting interview did not add driver starting path",
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

    rollout = main.driver_launch_rollout_optimizer(
        {
            "speed_mph": 100.0,
            "carry_yards": 230.0,
            "total_yards": 260.0,
            "pw_carry_yards": 115.0,
        }
    )
    require(rollout["target_rollout_pct"] == 11.0, "100 mph rollout target should be 11%")
    require(rollout["actual_rollout_pct"] is not None, "rollout optimizer did not calculate actual rollout")
    require(rollout["pw_driver_carry_target"] == 233.45, "PW carry relationship drifted")

    static_fit = main.static_length_lie_fit({"height_in": 69.0, "wrist_to_floor_in": 34.0})
    require(static_fit["recommended_7i_length_in"] == 37.0, "Standard static 7i length drifted")
    require(static_fit["initial_lie_delta_deg"] == 0, "Standard static lie drifted")

    tall_fit = main.static_length_lie_fit({"height_in": 76.0, "wrist_to_floor_in": 38.0})
    require(tall_fit["recommended_7i_length_in"] == 38.75, "Tall/static 7i length drifted")
    require(tall_fit["initial_lie_delta_deg"] == 2, "Tall/static lie recommendation drifted")

    sensation = main.shaft_sensation_quality_read(
        {
            "speed_mph": 118.0,
            "impact_sensation": "harsh",
            "shot_miss_direction": "right",
            "shot_quality_score": 4.0,
            "shaft_preference_score": 3.0,
            "current_flex_label": "X",
            "current_shaft_weight_g": 82.0,
        }
    )
    require(any("speed alone" in item for item in sensation["findings"]), "Sensation study finding is missing")
    require(any("regular/softer" in item for item in sensation["recommendations"]), "Sensation read missed softer-profile candidate")

    wishon = main.wishon_profile_guard(
        {
            "speed_mph": 116.0,
            "visual_transition_move": "jump start",
            "visual_tempo_control": "aggressive",
            "shot_miss_direction": "left",
            "impact_sensation": "harsh",
            "current_torque_deg": 5.2,
            "release": "Late",
        }
    )
    require(
        any("High torque" in item for item in wishon["torque_notes"]),
        "Wishon torque guard missed high-torque aggressive case",
    )
    require(
        any("0.5 inch" in item for item in wishon["trimming_notes"]),
        "Wishon trimming guidance is missing",
    )

    interview = main.fitting_interview_read(
        {
            "fitting_interview": {
                "club_type": "iron",
                "physical_pain": "no",
                "physical_limitations": "yes",
                "poor_shot_tendencies": ["hook it left"],
                "personal_wants": ["stop pulling"],
                "club_weight_feel": "too light",
            }
        }
    )
    require(interview["club_type"] == "iron", "Fitting interview club type drifted")
    require(any("Iron path" in item for item in interview["start_points"]), "Iron fitting interview path is missing")
    require(any("left-bias control" in item for item in interview["start_points"]), "Interview missed left-miss starting direction")

    direct_handoff = main.api_manufacturing_handoff()
    require(direct_handoff["package"] == "AE ShaftCAD Manufacturer Handoff Pack", "handoff endpoint payload failed")

    print("AE ShaftCAD smoke checks passed")


if __name__ == "__main__":
    main_check()
