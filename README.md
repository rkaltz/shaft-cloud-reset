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

## Smoke Check

Run `python tools/shaftcad_smoke.py` to verify the AI Shaft Builder Brief, Fit/CAD handoff, CPM analyzer caps, and behavior profile still work after changes.

