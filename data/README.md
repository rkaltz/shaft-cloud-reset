# BMT profile library

`bmt_shaft_profiles.csv` is a provenance-preserving import derived from the
recovered BMT/JerryClubDoc workbook export. It contains 1,330 distinct measured
seven-station profiles. Exact duplicate profiles are collapsed, while source
workbook/sheet/row references and occurrence counts are retained.

The runtime keeps suspect records in the library but quarantines them from fit
ranking when station values are missing, non-positive, non-monotonic,
analyzer-limited/sentinel (`>=999 CPM`), or implausibly large.

The BMT match score is reproduced for comparison only. It is an unverified
legacy heuristic, not a validated ShaftCAD recommendation. Its measurement
protocol is recorded as a 5-inch clamp, silk screen at 12 o'clock, and 454 g
profile tip weight. The raw butt-frequency field in the source export is a
separate 205 g observation.

Regenerate the file with:

```text
python tools/build_bmt_library.py
```

The source export is intentionally read-only and remains outside this
repository.
