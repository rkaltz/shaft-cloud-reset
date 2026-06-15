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
    require(0.0 <= design["zone_profile"][-1]["cpm"] <= 999.0, "11-inch CPM exceeds Auditor range")
    require(design["zone_profile"][-1]["analyzer_limited"], "11-inch overflow is not flagged")
    require(
        design["zone_profile"][-1]["raw_model_cpm"] > design["zone_profile"][-1]["cpm"],
        "raw model CPM should preserve unclamped simulation value",
    )
    require(len(design["behavior_intelligence"]["cpm_values"]) == 8, "behavior profile should include butt plus 7 stations")

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

    print("AE ShaftCAD smoke checks passed")


if __name__ == "__main__":
    main_check()
