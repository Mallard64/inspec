# Task 06: Streamlit demo page and mask overlay

## Goal
A single Streamlit page (`app.py`) that shows the Inspec loop for a saved run: packing list ->
compiled program -> calibration rounds -> inspect one kit image with part masks drawn on it, plus a
pure overlay renderer in `inspec/overlay.py` with tests.

## Context
Python 3.11, venv at `.venv` (streamlit 1.66.1, numpy, pillow, pydantic already installed).
Read these files before writing code: `inspec/executor.py`, `inspec/schema.py`,
`inspec/segments.py`, `inspec/calibrate.py`, `inspec/damage.py`, `inspec/baseline.py`,
`inspec/evaluate.py`, `scripts/e2e.py`.

Interfaces you call (do not change them):
- `CheckProgram.model_validate_json(text)`; `program.concepts()`; `program.parts` (each has `id`,
  `concept`, limits); `program.checks` (each has `id`, `type` "count"|"measure", `part`).
- `fetch_segments(program, image_path, sam) -> dict[concept, list[Segment]]` (SAM, disk-cached).
- `run_program(program, segments) -> ProgramResult` with:
  - `passed: bool`, `checks: list[CheckResult]` (`check_id`, `part_id`, `passed`, `message`,
    `evidence: list[SegmentRef]`),
  - `objects: dict[SegmentRef, Segment]` (final mask per object after merging),
  - `unassigned: list[SegmentRef]`, `metrics: dict[SegmentRef, dict[str, float]]`,
    `labels: dict[SegmentRef, set[str]]`.
  - An object's part = the `part_id` of the `count` check whose `evidence` contains its ref.
- `Segment.full_mask() -> bool ndarray (H, W)`, `Segment.box = (x1, y1, x2, y2)`.
- `SamClient(cache_dir)` from `inspec.sam_client`; use `SamClient(ROOT / ".cache" / "sam")`.
- `DamageChecker(packing_list, cache_dir=ROOT/".cache"/"damage").inspect(path) -> DamageReport`;
  `damaged(report, enabled) -> list[str]`; `QUESTIONS`.
- `VisionBaseline(packing_list, cache_dir=ROOT/".cache"/"baseline").inspect(path)
  -> BaselineVerdict` with `.counts`, `.failures()`, `.reason`.
- `compile_program(packing_list, kit_name=...) -> Generation` (`.value`, `.attempts`, `.errors`).

Saved run directory layout (`runs/<name>/`, any file may be missing):
- `compiled.json`, `final.json`: CheckProgram JSON.
- `calibration.json`: `{"images": [...], "converged": bool, "rounds": [{"round": 1, "passed": 0,
  "total": 60, "failures": {"000.png": ["long_screw_count: found 2, expected 1..1", ...]},
  "program": {...}, "repair": {"attempts": 1, "rejected": [], "notes": "..."}}], "program": {...}}`
- `damage_calibration.json`: `{"enabled": ["bag_torn", ...], "false_alarms": {...}, "images": 30}`
- `report.json`: `{"splits": {"test/good": {"kind": "good", "images": 122, "programs":
  {"calibrated": {"flagged": 2, "rate": 0.016, "by_defect": {...}, "failed_checks": {...}}}}}}`

Dataset images: `data/screw_bag/{validation/good,test/good,test/logical_anomalies,
test/structural_anomalies}/*.png` (may be absent; then only upload works).

## Requirements
1. `inspec/overlay.py`:
   - `object_parts(result: ProgramResult) -> dict[SegmentRef, str]`: part id per object from count
     check evidence; objects in `result.unassigned` map to `"unassigned"`.
   - `render(image: PIL.Image.Image, result: ProgramResult) -> PIL.Image.Image`: RGB copy of the
     image with each object's mask alpha-blended (alpha ~0.45) in a fixed colour per part id
     (stable palette, assigned in sorted part-id order), unassigned objects in grey, and a short
     text label (part id) at the top-left of each object's box. Numpy + Pillow only. Must not
     modify the input image.
   - `legend(result) -> list[tuple[str, tuple[int, int, int], int]]`: (part id, colour, count).
2. `tests/test_overlay.py`: synthetic Segments (small bool masks) and a hand-built program with
   two parts; run `run_program` and assert `object_parts`, that `render` returns the same size,
   colours a masked pixel differently from an unmasked one, and leaves the input untouched.
3. `app.py` at repo root, one page, in this order:
   - Sidebar: run picker (subdirectories of `runs/` that contain `final.json`, default `run3` if
     present), packing list text input (default "1 long screw, 1 short screw, 2 nuts, 2
     washers"), checkboxes "Muse Spark damage check" (default on) and "Compare vision-only
     baseline" (default off).
   - Section "1. Compile": show `compiled.json` with `st.json` (collapsed). A button "Recompile
     live" calls `compile_program` with the sidebar packing list and shows the result, attempts and
     rejected attempts (wrap API errors in `st.error`, never crash).
   - Section "2. Calibrate on good kits": a table of rounds (round, passed/total), then one
     expander per round with its repair notes, rejected attempts, and failures (first 10 images).
     Below, a table comparing each part's limits in compiled vs final program (only fields that
     differ), and the measure checks added by calibration.
   - Section "3. Inspect a kit": choose split + image from the dataset (selectbox) or upload a PNG
     /JPG (save uploads to `.cache/uploads/<sha256>.<ext>` and use that path). Run the final
     program, show the overlay (`render`) beside the original, a large PASS/FAIL, a legend, and a
     table of checks (id, passed, message). If damage is on: run `DamageChecker`, using `enabled`
     from `damage_calibration.json` (all `QUESTIONS` if missing); show flags and evidence; the
     kit fails if either check fails. If baseline is on: show the baseline's counts table and
     verdict next to Inspec's. Wrap every API call in try/except with `st.error`.
   - Section "4. Evaluation": if `report.json` exists, a table with rows (split, program) and
     columns flagged, images, rate; good splits labelled "false alarms", others "recall".
   - Use `st.cache_resource` for SamClient/checkers and `st.cache_data` for file loads.
   - Never print or log API keys.
4. Do not modify any other file. Do not touch `inspec/schema.py`, `inspec/compiler.py`,
   `inspec/executor.py`, `inspec/calibrate.py`, `inspec/damage.py`, `inspec/baseline.py`.

## Done when
- `.venv/bin/python -m pytest tests/test_overlay.py -q` passes, and the full
  `.venv/bin/python -m pytest -q` still passes.
- `.venv/bin/python -c "import ast;ast.parse(open('app.py').read())"` succeeds and
  `.venv/bin/python -c "import inspec.overlay"` succeeds.

## Constraints
- Python 3.11, no new dependencies beyond streamlit (installed).
- Follow AGENTS.md.
