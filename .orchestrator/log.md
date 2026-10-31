# Orchestration log

One line per task: id | delegated or self-done | result | retries

- 01-download-loco | delegated (Muse, 20 steps) | merged; bash -n, dry-run, bad-category, skip checks pass | 0 retries
- 02-sam-client | delegated (Muse, 40 steps) | merged; 16 tests pass | 0 retries
- 03-segments | delegated (Muse, 40 steps) | merged; 7 tests pass | 0 retries
- 04-executor | delegated (Muse, 40 steps) | merged; 21 tests pass; Claude rounded message values, then replaced dedupe rules with object merging after real-image evidence | 0 retries
- 05-calibration-eval | self-done (Claude) | calibrate.py, evaluate.py, scripts/e2e.py, executor hole metric + carve-out + first-match; 88 tests pass. Calibration and eval are Claude-owned per CLAUDE.md; executor changes were cross-module debugging driven by real-image data | n/a
- 06-streamlit-ui | delegated (Muse, 60 steps) | merged; Claude fixed per-image colour shifts, contradictory PASS/FAIL banners, deprecated use_column_width, tiny labels; AppTest smoke run on cached data passes; 96 tests pass | 0 retries
- 07-ui-per-kit | self-done (Claude) | app.py picks dataset, packing list and recompile kit name from the run's kit_name; warns when a run has no damage_calibration.json. ~15 lines, smaller than a brief; AppTest smoke on run3 and bb4 passes | n/a
