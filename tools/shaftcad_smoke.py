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

    direct_handoff = main.api_manufacturing_handoff()
    require(direct_handoff["package"] == "AE ShaftCAD Manufacturer Handoff Pack", "handoff endpoint payload failed")

    print("AE ShaftCAD smoke checks passed")


if __name__ == "__main__":
    main_check()
