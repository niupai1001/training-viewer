# TVLP 2.0 and desktop development

The desktop edition is isolated from the legacy application. Its data directory is
`%LOCALAPPDATA%/TrainingViewerNext`. It reads TVLP 2.0 only. No legacy migration is performed.

## Training protocol

Each run directory contains `run.json`, append-only `metrics.jsonl`, and `events.jsonl`.
The metadata schema is in `tvlp-2.0.schema.json`. Identity is independent of display names.
Experiment identifies the research question; variant identifies a baseline, ablation, or
modification. Changed variants require a description. Optional `baseline_id` refers to a
variant in the same experiment. Seeds may be stored in config, but are never promoted to UI labels.

Metrics declare label, unit, optimization direction (`min`, `max`, `none`), and role
(`loss`, `score`, `other`). No metric names are inferred. A view declares 1–4 chart keys,
0–4 number keys, and a primary metric key. `ratio` values render as percentages; other
units retain their original numeric scale.

Metric record example:

```json
{"seq":2,"session_id":"session-a","step":10,"epoch":1,"time":"2026-11-09T15:00:00Z","values":{"train/objective":0.02}}
```

Sequences are positive integers increasing across the run. Steps are nonnegative integers
and cannot decrease within a session. Epoch is optional, finite and nonnegative. Values
must be declared finite numbers. For duplicate session/step/key records, the greatest
sequence wins. Every timestamp includes a timezone.

Events contain sequence, session, time and `kind`: `started`, `resumed`, `heartbeat`,
`completed`, `failed`. The portable writer emits heartbeats every ten seconds. Missing
activity after thirty seconds is interrupted, never implicitly completed.

Resume uses `RunWriter(directory, resume=True)` with the same run ID and a new session.
An OS file lock prevents concurrent writers and releases after crashes. A trailing partial
line is removed on explicit resume; readers otherwise wait for its terminating newline.
Damaged middle lines are skipped with file offsets reported in diagnostics.

## Desktop usage

Install and open Training Viewer. Choose **添加实验** to preview an existing output directory
or generate integration code for a new training. Save `tvlp_writer.py` beside the training
script. Replace the demonstration log call with calls in the real training loop.
Logging does not contact the desktop service. Closing the desktop does not stop training.

Monitoring a parent directory discovers future runs automatically. Adding a directory
opens its experiments. Use the current-folder selector to switch between monitored
folders. Unmonitoring hides the folder and preserves its original logs and cached index.
The run summary shows the latest loss and accuracy (or the named evaluation metric)
when recorded. Training time adds each session from its start to its finish or latest
recorded activity, excluding time between sessions. Indexed history depends on the original
files; an independent historical snapshot library is not included in this release.

Loss charts default to the latest 20% of the current session. The thumbnail shows the
complete selected session; select all sessions for full run history. Manual interaction
pauses following until **返回实时**. Statistics use original data, never sampled curves.

## Build and verification

Development uses Python 3.13 on Windows x64 and the versions in `requirements-next.txt`.
Install those requirements, run `npm ci` inside frontend, and build with
`npx vite build --config vite.next.config.ts`. Set `PYTHONPATH=src` and run
`python desktop_entry.py`. This development command is not required by installed users.

Run backend checks with `python -m pytest tests/test_next.py` and frontend checks with
`npx tsc --noEmit --jsx react-jsx --module esnext --moduleResolution bundler --target es2022 --esModuleInterop --skipLibCheck next/main.tsx`.
`tools/next_examples.py` generates classification, segmentation and custom-objective examples.
`tools/next_smoke_server.py` plus `frontend/e2e/next-smoke.mjs` exercise browser flows.
`tools/next_benchmark.py` records cold import, million-point range query and 100-run listing.

Build the Windows installer with `tools/build_next.ps1 -Compiler <ISCC.exe>`.
Place Microsoft's x64 Evergreen standalone WebView2 installer at
`packaging/vendor/WebView2.exe` first and verify its Authenticode signature. The build
includes that offline prerequisite and detects it during installation.

Dependencies and their licenses are distributed in the installed application. The
installer is unsigned until a publisher certificate is supplied. The optional legacy
CLI remains in the repository; the new desktop has its own entry point and API.
