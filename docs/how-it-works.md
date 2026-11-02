# How it works

Why kit checking is hard for a segmentation model, the pipeline, the check-program schema and the calibration loop. Back to the [README](../README.md).

## Why this is hard (and a real example)

The freshly compiled program rejects **every** good Screw Bag (60/60 on validation):

- SAM ignores size words, so "long screw" and "short screw" both match both screws.
- SAM labels hex nuts **and** washers as both "nut" and "washer", and calls the solid screw heads
  "nuts" too. One good kit came back with 6 "nuts" and 4 "washers".
- Nut and washer **areas overlap** (washers up to 6,907 px², nuts from 6,725 px² on 100 good
  images), so size alone can't tell them apart. The share of the outline that is hole does: nuts
  0.18–0.30, flat washers 0.38–0.44.
- About 3% of good kits have a nut or washer touching a screw, and SAM's screw mask swallows it.
  That adds ~110 px to the screw's length.

So the compiled checks are right about *what* to count, but the program doesn't yet know how to
tell the parts apart. The calibration loop learns that from known-good kits.

## How it works

```
                 ┌──────────────────────────────┐
packing list ──► │ 1. Compile (Muse Spark)      │ ──► check program (JSON)
                 └──────────────────────────────┘            │
                                                             ▼
kit image ─────► 2. Segment (SAM 3.1, one call per part, cached)
                                                             │
                                                             ▼
                 3. Execute (plain Python) ──► per-check verdict + masks as evidence
                                                             ▲
known-good kits ► 4. Calibrate: run checks on good kits;     │
                     failing check → Muse Spark repairs it ──┘  → re-run until clean
```

### 1. Compile: packing list → check program (Muse Spark)

Muse Spark reads the packing list (plus a few good example images) and emits a typed check program
using structured output, validated by [`inspec/schema.py`](../inspec/schema.py). Example for Screw
Bag after calibration (run 3; null fields and `reason` strings omitted). The compiler wrote the
parts and count checks. Calibration added every number except the counts:

```json
{
  "kit_name": "screw bag",
  "parts": [
    {"id": "long_screw",  "concept": "screw", "min_length": 355},
    {"id": "short_screw", "concept": "screw"},
    {"id": "nut",         "concept": "nut",   "min_hole": 0.1, "max_hole": 0.33},
    {"id": "washer",      "concept": "washer"}
  ],
  "checks": [
    {"id": "long_screw_count",   "type": "count",   "part": "long_screw",  "min": 1, "max": 1},
    {"id": "short_screw_count",  "type": "count",   "part": "short_screw", "min": 1, "max": 1},
    {"id": "nut_count",          "type": "count",   "part": "nut",    "min": 2, "max": 2},
    {"id": "washer_count",       "type": "count",   "part": "washer", "min": 2, "max": 2},
    {"id": "long_screw_length",  "type": "measure", "part": "long_screw",  "metric": "length",
     "min": 396, "max": 441},
    {"id": "short_screw_length", "type": "measure", "part": "short_screw", "metric": "length",
     "min": 276, "max": 308}
  ]
}
```

- **Parts** map a name to one SAM concept, plus optional limits on `length`, `area` and `hole`
  (the fraction of the filled outline that is hole). "Long screw" and "short screw" share the
  concept `screw` and are split by length, because SAM ignores size words.
- **Parts are tried in order.** Each object goes to the first part whose concept is among its labels
  and whose limits it meets. A part with no limits at the end catches the rest. Above, anything
  labelled washer that isn't nut-shaped is a washer.
- **Merging** happens before any check. A detection mostly inside a larger one (default 80%) is the
  same object with an extra label, so an object can carry {nut, washer}, or {screw, nut} for a screw
  plus its head. One exception: a detection with a hole of its own, under half the container's
  size, is a separate part touching it (a washer against a screw). It's carved out of the
  container. Screw heads are solid; on 100 good images every head had hole 0.0 and every touching
  nut or washer had at least 0.24.
- **Checks** are `count` (how many instances of a part) or `measure` (bounds on a metric for every
  instance). The schema is kept flat so Muse Spark's structured output fills it reliably.

Design rules, taken from what SAM 3.1 actually does well:
- **One short noun phrase per SAM call** ("nut", not "nuts and washers"). Verified behaviour.
- **No spatial words or negation in SAM prompts.** Size, position, "missing" and "extra" are all
  computed in Python from masks, where they're exact and testable.
- **Check types are a small fixed set** (count and measure for now; relative position comes later if
  Breakfast Box needs it), so every check is executable and explainable.

### 2. Segment (SAM 3.1)

One Responses API call per (image, concept), with results cached on disk keyed by image hash and
concept. Rerunning or repairing rules never re-calls SAM. Output is parsed into boxes and boolean
masks. The wire format is undocumented in places, so it was verified against the live API:
[docs/sam-output-format.md](sam-output-format.md).

### 3. Execute (Python)

Each check runs on the masks and returns pass/fail, the measured value, and the masks that
produced it. A kit fails if any check fails. The UI shows the failing check with its masks drawn on
the image, so a human can see *why*.

### 4. Calibrate (the agent loop)

[`inspec/calibrate.py`](../inspec/calibrate.py)

1. Run the program on known-good training kits (60 by default).
2. If any fail, send Muse Spark two things. First, every object's measurements grouped by the part
   it went to and sorted, so gaps and ranges are exact rather than eyeballed. Second, for each
   failing kit, its failed checks and objects.
3. Muse Spark returns a repaired program: part order, limits, and `measure` checks for parts whose
   size defines them. **Code rejects any repair that changes a part or a count check.** The
   quantities come from the packing list, so the only way to pass a good kit is to describe the
   parts better. A rejected repair goes back to the model with the reason.
4. Re-run. Keep the best program so far. A repair that scores lower is discarded, and the model is
   told so on the next try. Stop when every kit passes, when a repair changes nothing, or after 4
   rounds.

In practice one repair takes the program from 0/60 to 56–58/60. The model names the kits it
leaves failing as segmentation failures (e.g. "204.png merged screws 510 px, area 47,935") instead
of bending limits to fit them. Every round, rejected attempt and note is saved in
`runs/<name>/calibration.json`.

Repairs only ever see good training images, never anomalies or validation/test images.

## Project structure

```
inspec/
  sam_client.py   # ✅ SAM 3.1 calls, disk cache keyed by (image hash, concept)
  segments.py     # ✅ parse SAM output into boxes and boolean masks
  schema.py       # ✅ check-program schema (pydantic)
  llm.py          # ✅ Muse Spark / Baseten client with validate-and-retry
  compiler.py     # ✅ packing list (+ good images) -> check program (Muse Spark)
  executor.py     # ✅ merge detections into objects, run checks -> verdicts with evidence
  concepts.py     # ✅ swap concepts SAM misses on good kits for ones it finds (Muse Spark + SAM)
  calibrate.py    # ✅ run on good kits, Muse Spark repairs failing checks, re-run
  evaluate.py     # ✅ false-alarm rate and recall per LOCO split and defect type
  damage.py       # ✅ Muse Spark vision check for torn bag, broken/painted part, foreign object
  baseline.py     # ✅ Muse Spark vision-only baseline: counts + damage from the photo
  overlay.py      # ✅ draw part masks and labels on a kit photo
app.py            # ✅ Streamlit page: packing list -> checks -> self-repair -> inspect -> results
scripts/          # ✅ dataset download, e2e runner, baseline runner, Baseten check
docs/             # ✅ verified API notes
tests/            # ✅ unit tests and captured SAM responses
.orchestrator/    # ✅ task briefs and log for delegated coding tasks
```
