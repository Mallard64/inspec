# Orchestration log

One line per task: id | delegated or self-done | result | retries

- 01-download-loco | delegated (Muse, 20 steps) | merged; bash -n, dry-run, bad-category, skip checks pass | 0 retries
- 02-sam-client | delegated (Muse, 40 steps) | merged; 16 tests pass | 0 retries
- 03-segments | delegated (Muse, 40 steps) | merged; 7 tests pass | 0 retries
- 04-executor | delegated (Muse, 40 steps) | merged; 21 tests pass; Claude rounded message values, then replaced dedupe rules with object merging after real-image evidence | 0 retries
- 05-calibration-eval | self-done (Claude) | calibrate.py, evaluate.py, scripts/e2e.py, executor hole metric + carve-out + first-match; 88 tests pass. Calibration and eval are Claude-owned per CLAUDE.md; executor changes were cross-module debugging driven by real-image data | n/a
- 06-streamlit-ui | delegated (Muse, 60 steps) | merged; Claude fixed per-image colour shifts, contradictory PASS/FAIL banners, deprecated use_column_width, tiny labels; AppTest smoke run on cached data passes; 96 tests pass | 0 retries
- 07-ui-per-kit | self-done (Claude) | app.py picks dataset, packing list and recompile kit name from the run's kit_name; warns when a run has no damage_calibration.json. ~15 lines, smaller than a brief; AppTest smoke on run3 and bb4 passes | n/a
- 08-ui-story | self-done (Claude) | app.py rewritten as one page in story order (packing list chips, checks as sentences via new inspec/explain.py, self-repair before/after, ✅/❌ verdicts, results table), URL preselection for the video; 107 tests pass; AppTest + headless-Chrome screenshots checked. Self-done: the hard part was deciding what to show | n/a
- 09-live-calls | self-done (Claude) | inspec/live.py call log + SamClient.api_calls; app 'Run it live' (compile, concept repair, self-repair) and 'Live model calls' toggle, both verified against the real API (152 s / ~30 s); dataset credit footer; video script rewritten to the hackathon video rules | n/a
- 10-triage | self-done (Claude) | error analysis of final runs (damage model = 15/19 false rejects, 33/38 misses); inspec/triage.py PASS/REVIEW/FAIL with 3% margin chosen on validation; frozen 429343c, test scored once: hard false rejects 7->1 (SB), 4->0 (BB) | n/a
