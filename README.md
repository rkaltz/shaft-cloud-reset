# Golf Shaft Design Studio Cloud

This is the clean reset version.

It has only the files needed for Render:

- `main.py`
- `requirements.txt`
- `Dockerfile`
- `render.yaml`

## What To Upload To GitHub

Upload the contents of this folder only:

```text
START_OVER_CLOUD
```

Do not upload old folders, zips, or duplicate repos.

## Render

Create a new Render Web Service from this repo.

Settings:

```text
Environment: Docker
Branch: main
Health Check Path: /health
```

Open the Render URL without `/docs`.

## Manufacturer Handoff

AE ShaftCAD now exports a prototype manufacturer handoff pack from the AI shaft designer. The pack includes:

- shaft ID-based mandrel geometry stations
- finished shaft OD envelope
- prototype ply schedule
- tapered flag template schedule
- mandrel G-code
- CadQuery STEP recipe
- tolerances, QC checklist, revision loop, and manufacturer questions

Use `/api/manufacturing-handoff` or the `Export MFG Pack` button in the app.

This is a prototype quote and first-article package, not a final production traveler. A shaft manufacturer still needs to validate prepreg, resin system, cure cycle, sanding/paint allowance, and first-article QC data.

## Smoke Check

Run `python tools/shaftcad_smoke.py` to verify the AI Shaft Builder Brief, Fit/CAD handoff, CPM analyzer caps, behavior profile, ID-based mandrel export, and manufacturer handoff still work after changes.

