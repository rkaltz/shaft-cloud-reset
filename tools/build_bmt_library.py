"""Build ShaftCAD's provenance-preserving BMT profile library.

The source export remains read-only. Exact duplicate profiles are collapsed while
their workbook/row provenance and occurrence counts are retained.
"""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\rkalt\Documents\New project\Shaft Research Analysis 2026-10-11\BMT-profile-occurrences.csv")
DESTINATION = ROOT / "data" / "bmt_shaft_profiles.csv"
STATIONS = ("41in", "36in", "31in", "26in", "21in", "16in", "11in")


def profile_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(field, "").strip() for field in ("company", "model", "flex", *STATIONS))


def numeric_values(rows: list[dict[str, str]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row.get(field, "").strip()))
        except (AttributeError, TypeError, ValueError):
            continue
    return values


def main() -> None:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    with SOURCE.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            grouped[profile_key(row)].append(row)

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "profile_id", "company", "model", "flex", *STATIONS, "weight_g",
        "raw_frequency_205g", "length_in", "shaft_type", "occurrences", "sources",
    ]
    with DESTINATION.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for index, (key, rows) in enumerate(sorted(grouped.items()), start=1):
            weights = numeric_values(rows, "weight_g")
            raw_frequencies = numeric_values(rows, "raw_frequency_205g")
            lengths = numeric_values(rows, "length")
            shaft_types = sorted({row["shaft_type"].strip() for row in rows if row.get("shaft_type", "").strip()})
            sources = sorted({f'{row["workbook_id"]}:{row["sheet"]}:{row["row"]}' for row in rows})
            company, model, flex, *stations = key
            writer.writerow({
                "profile_id": f"BMT-{index:04d}",
                "company": company,
                "model": model,
                "flex": flex,
                **dict(zip(STATIONS, stations)),
                "weight_g": f"{statistics.median(weights):.2f}" if weights else "",
                "raw_frequency_205g": f"{statistics.median(raw_frequencies):.1f}" if raw_frequencies else "",
                "length_in": f"{statistics.median(lengths):.2f}" if lengths else "",
                "shaft_type": "/".join(shaft_types),
                "occurrences": len(rows),
                "sources": ";".join(sources),
            })

    print(f"Wrote {len(grouped)} distinct BMT profiles to {DESTINATION}")


if __name__ == "__main__":
    main()
