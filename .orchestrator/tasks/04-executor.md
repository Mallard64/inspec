# Task 04: Check executor

## Goal
Write `inspec/executor.py`, which runs a `CheckProgram` on one image's SAM segments and returns
per-check verdicts with evidence.

## Context
- `inspec/schema.py` (read it; do NOT modify it) defines `CheckProgram`, `Part`, `Dedupe` and
  `Check`. Key points:
  - `program.parts`: each has `id`, `concept`, and optional `min_length`, `max_length`,
    `min_area`, `max_area`.
  - `program.dedupe`: each rule has `keep` and `drop` (concepts) and `min_iou`.
  - `program.checks`: each has `id`, `type` (`"count"` or `"measure"`), `part`, `metric`
    (`"area"`, `"length"` or None), `min`, `max` (inclusive, either may be None) and `reason`.
  - `program.concepts()` returns the distinct lowercased concepts.
- `inspec/segments.py` (do NOT modify) defines `Segment` with `object_id`, `box` (x1, y1, x2, y2,
  inclusive), `image_size` (w, h), `mask` (bool array cropped to the box), `area` (property) and
  `full_mask()`, plus `parse_sam_output(text) -> list[Segment]`.
- `inspec/sam_client.py` (do NOT modify) has `SamClient.segment_text(image_path, concept) -> str`.

## Interface (implement exactly)

```python
from dataclasses import dataclass, field
from pathlib import Path
from inspec.schema import CheckProgram
from inspec.segments import Segment

@dataclass(frozen=True)
class SegmentRef:
    concept: str      # lowercased
    index: int        # position in segments_by_concept[concept]

@dataclass
class CheckResult:
    check_id: str
    passed: bool
    value: float | list[float]          # count -> number of instances; measure -> metric per instance
    expected: tuple[float | None, float | None]   # (min, max)
    evidence: list[SegmentRef]          # instances of the part the check looked at
    message: str                        # e.g. "nut_count: found 3, expected 2..2"

@dataclass
class ProgramResult:
    passed: bool                         # all checks passed
    checks: list[CheckResult]
    dropped: list[tuple[SegmentRef, SegmentRef, float]]  # (dropped, kept, iou)
    unassigned: list[SegmentRef]         # segments that match no part
    metrics: dict[SegmentRef, dict[str, float]]   # {"area": ..., "length": ...} for every kept segment

    def failed(self) -> list[CheckResult]: ...
    def to_dict(self) -> dict: ...      # JSON-safe (refs as "concept#index"), no arrays

def mask_length(segment: Segment) -> float: ...
def mask_iou(a: Segment, b: Segment) -> float: ...
def run_program(program: CheckProgram,
                segments_by_concept: dict[str, list[Segment]]) -> ProgramResult: ...
def fetch_segments(program: CheckProgram, image_path: str | Path,
                   client: "SamClient") -> dict[str, list[Segment]]: ...
```

## Semantics
1. **Keys.** `segments_by_concept` is keyed by lowercased concept. If any concept in
   `program.concepts()` is missing, raise `ValueError` naming it. An empty list is valid (zero
   found).
2. **Dedupe first.** For each rule in order: drop every segment of `drop` whose IoU with any
   segment of `keep` is `>= min_iou`. Record `(dropped_ref, best_kept_ref, iou)`. Dropped segments
   are excluded from everything after.
3. **Metrics.** For each kept segment, `area = segment.area` and `length = mask_length(segment)`.
   - `mask_length`: take the (x, y) coordinates of the mask's True pixels, find the principal
     axis (eigenvector of the coordinate covariance with the largest eigenvalue), project the
     coordinates onto it, and return `max - min + 1`. A mask with 0 pixels has length 0, and
     1 pixel has length 1.
   - `mask_iou`: compute on full-image masks (`full_mask()`), or equivalently on the box
     intersection. Return 0.0 when the union is empty.
4. **Assign to parts.** A kept segment of concept `c` belongs to every part with
   `part.concept.lower() == c` whose non-None limits it satisfies (inclusive). Segments that
   belong to no part go in `unassigned`.
5. **Checks.**
   - `count`: `value` = number of instances of the part; passes if `min <= value <= max`, where a
     None bound is open.
   - `measure`: `value` = list of the metric for each instance, in order. Passes if every value is
     within the bounds. With zero instances it passes (count checks catch missing parts).
   - `evidence` = refs of the part's instances. `message` is one plain line, stating the measured
     value(s) and the expected range.
6. `fetch_segments`: for each concept in `program.concepts()`, call
   `parse_sam_output(client.segment_text(image_path, concept))`. Return the dict.

## Requirements
- Pure functions except `fetch_segments`. Only `numpy` and the stdlib.
- Create `inspec/executor.py` and `tests/test_executor.py`. Do not touch any other file.

## Tests (`tests/test_executor.py`)
Build synthetic `Segment`s directly with numpy masks (no SAM calls, no fixtures needed), plus one
test that uses `tests/fixtures/sam/rect_one_bit.txt` via `parse_sam_output`. Cover:
- `mask_length`: a horizontal 160×40 rectangle → 160 (±1); the same rectangle vertical → 160
  (±1); a 1-pixel-wide diagonal line from (0,0) to (99,99) → about 141 (±2); a filled disk of
  radius 20 → about 41 (±2). Use the rect fixture for the first case.
- `mask_iou`: identical → 1.0, disjoint → 0.0, half overlap → about 1/3.
- Dedupe: a "nut" identical to a "washer" is dropped, recorded with iou 1.0 and excluded from
  counts. A "nut" elsewhere is kept.
- Count pass and fail, including open bounds (`min` only).
- Length split: two "screw" segments of length ~400 and ~250, with parts
  `long_screw (min_length 300)` and `short_screw (max_length 300)`. Each part gets exactly one
  instance. A screw of length 500 with a `measure` check `max 420` on `long_screw` fails, and its
  message contains the measured value.
- A segment matching no part appears in `unassigned`.
- A missing concept key raises `ValueError`. An empty list for a concept gives count 0.
- `measure` with zero instances passes.
- `to_dict()` is `json.dumps`-able.
- `fetch_segments` with a fake client that returns fixture text calls it once per distinct concept.

## Done when
- `/Users/bigdum/inspec/.venv/bin/python -m pytest tests/test_executor.py -q` passes, run from the
  worktree root, and the full suite (`-m pytest -q`) still passes.

## Constraints
- Python 3.11, type hints. No new dependencies. Follow AGENTS.md.
