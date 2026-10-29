# Inspec

**Type a packing list, show Inspec a photo of the kit, and it tells you what's wrong, with a mask on
every part it counted.**

Built solo for the **Meta Global AI Developer Hackathon**, Indie Developer track, theme **Push the
Frontier** (Meta models on a hard manufacturing problem). Build window Oct 26 – Nov 4, 2026. All code
in this repo was written during the event; the commit history is the record.

> **Status (Oct 28):** the full pipeline works end to end on Screw Bag: packing list → Muse Spark
> compiler → SAM 3.1 → checks → Muse Spark calibration loop → evaluation. [Results](#results) are
> measured on the held-out test set. The vision-only baseline and the UI are **not built yet**. The
> [Status](#status) table is the source of truth.

- Demo: _not yet_
- Video: _not yet_ (3-minute demo due with submission)

<!-- Screenshot / GIF: packing list → compiled checks → verdict with masks -->

## In 60 seconds

- **Problem.** At a kitting station, a bag missing one washer looks almost identical to a good one.
  Standard visual anomaly detection needs hundreds of example images per product and can't say
  *which* rule broke. Asking a vision model "is this OK?" gives a yes/no with no evidence.
- **Idea.** Treat the packing list as a spec. An agent compiles it into explicit checks ("exactly 2
  nuts"), SAM 3.1 finds every part, and plain code runs the checks. Every verdict points at masks.
- **The agent part.** The compiled checks are tested on kits known to be good. Any check that fails
  on a good kit is wrong by definition, so the agent repairs it from the evidence and re-tests. It's
  a self-correcting loop with a measurable before and after.
- **Result so far.** On MVTec LOCO Screw Bag's held-out test set, the calibrated program catches
  all 137 kits with wrong parts or counts, and rejects 1–2 of 122 good kits. Before
  calibration it rejected every good kit. A vision-only baseline is still to come.

## Results

Screw Bag, packing list "1 long screw, 1 short screw, 2 nuts, 2 washers". Each run compiles the
list, calibrates on 60 evenly spaced `train/good` images and evaluates once on held-out images
(`scripts/e2e.py --calib 60 --test`). Nothing was tuned on the test set. A kit is flagged when any
check fails.

| | Compiled only | Run 1 | Run 2 | Run 3 | Baseten |
|---|---|---|---|---|---|
| False alarms, `validation/good` (60) | 60 (100%) | 1 (1.7%) | 1 (1.7%) | 2 (3.3%) | 2 (3.3%) |
| False alarms, `test/good` (122) | 122 (100%) | 1 (0.8%) | 2 (1.6%) | 2 (1.6%) | 3 (2.5%) |
| Caught, `test/logical_anomalies` (137) | 137* | 137 (100%) | 137 (100%) | 137 (100%) | 137 (100%) |
| Caught, `test/structural_anomalies` (82) | 82* | 33 (40%) | 34 (41%) | 35 (43%) | 38 (46%) |
| Calibration kits passing, after / before | 0 / 60 | 57 / 60 | 58 / 60 | 56 / 60 | 56 / 60 |

Runs 1–3 use `muse-spark-1.3` on the Meta Model API. The Baseten run uses Muse Spark Open
(`meta-models/muse-spark-open-1026`) for both compile and calibration. It needed two repairs: the
second fixed side-on washers (hole 0) being counted as nuts.

\* The compiled-only program flags everything, so its "recall" means nothing. That's the point of
calibration.

- **All 16 logical defect types are caught in every run**: missing and extra parts, very short
  screws, and screws that are too long or too short. Each kit is flagged by the check you'd
  expect. For example, a missing nut fails `nut_count`, and a very short screw fails
  `short_screw_length`. One exception: an extra nut or washer is sometimes counted as the other
  type, so both counts fail. The verdict is still right.
- **Damage (structural anomalies): see [Damage check](#damage-check-muse-spark-vision).** The
  part checks alone don't look at colour or the bag, so those are 0/16 each. Contamination (19/25 in every run) and broken parts (14–16/25) are partly caught, because
  they change a part's shape or count.
- **Runs differ** because Muse Spark proposes a different repair each time (run 2 split screws by
  area instead of length). Runs 1–2 used an earlier repair prompt. Run 3 added the rule "a lone
  outlier is a measurement failure, not a reason to widen a range".
- **The remaining false alarms are segmentation failures**, not rule errors. Examples: two screws
  lying end to end that SAM returns as one 713 px object, or a tilted screw that measures 313 px
  against a 276–308 range.
- **Not done yet:** the vision-only Muse Spark baseline, AUROC (verdicts are binary for now), and
  other LOCO categories.

### Damage check (Muse Spark vision)

Part checks count and measure; they can't see a torn bag or paint. So
[`inspec/damage.py`](inspec/damage.py) asks Muse Spark four yes/no questions about each photo:
torn bag, broken part, discoloured part, foreign object. Calibration uses the part checks' rule: a
question that fires on more than 2 of the good calibration kits is switched off. On 30 good kits
none fired, so all four stayed on. A kit is rejected if a part check fails or the damage check
finds something. Evaluated with run 3's program (`scripts/e2e.py --program runs/run3/final.json
--damage --test`):

| | Part checks only | Damage check only | Both |
|---|---|---|---|
| False alarms, `validation/good` (60) | 2 (3.3%) | 0 | 2 (3.3%) |
| False alarms, `test/good` (122) | 2 (1.6%) | 3 (2.5%) | 5 (4.1%) |
| Caught, `test/logical_anomalies` (137) | 137 | 4 | 137 |
| Caught, `test/structural_anomalies` (82) | 35 (43%) | 56 (68%) | **71 (87%)** |
| … bag broken / colour / contamination / part broken | 0/16, 0/16, 19/25, 16/25 | 16/16, 15/16, 14/25, 11/25 | 16/16, 15/16, 23/25, 17/25 |

The two halves of the result come from different methods. Part checks find wrong counts and some
broken parts. Muse Spark finds bag damage and paint. Each is poor at the other's job.
"Damage check only" also works as a first vision-only baseline: on logical defects it catches 4 of
137, against the part checks' 137.

How honest is this? I wrote the `part_broken` wording after looking at the even-numbered
structural images (my first wording flagged 5 of 8 good kits as having "split washers"). The
odd-numbered half was never looked at, and it scores as well: 38/41 caught with both checks,
against 33/41 on the dev half. The cost is false alarms: 3 more good test kits rejected, 2 for a
"torn bag" and 1 for a "broken part".

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
using structured output, validated by [`inspec/schema.py`](inspec/schema.py). Example for Screw
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
[docs/sam-output-format.md](docs/sam-output-format.md).

### 3. Execute (Python)

Each check runs on the masks and returns pass/fail, the measured value, and the masks that
produced it. A kit fails if any check fails. The UI shows the failing check with its masks drawn on
the image, so a human can see *why*.

### 4. Calibrate (the agent loop)

[`inspec/calibrate.py`](inspec/calibrate.py)

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

## Evaluation plan

Dataset: [MVTec LOCO AD](https://www.mvtec.com/company/research/datasets/mvtec-loco), Screw Bag.
A correct bag holds 1 long screw, 1 short screw, 2 nuts and 2 washers (implied by the dataset's
defect list: missing, additional, too long or too short screws, nuts and washers).

| Split | Images | Used for |
|---|---|---|
| `train/good` | 360 | Compiler examples and calibration (a small subset) |
| `validation/good` | 60 | Held-out false-alarm check after calibration |
| `test/good` | 122 | False-alarm rate |
| `test/logical_anomalies` | 137 | **Main target**: wrong counts and wrong screw lengths |
| `test/structural_anomalies` | 82 | Reported separately: broken bag, colour, contamination. Mostly out of scope. |

Metrics, image-level, per split ([`inspec/evaluate.py`](inspec/evaluate.py)):
- **Recall** on anomalies (bad kits caught), overall and per defect type. Defect types are read
  from LOCO's ground-truth masks.
- **False-alarm rate** on good kits (good kits rejected)
- **Calibration before vs after:** the raw compiled program vs the repaired one, on the same images
- Planned: **AUROC**, using the number of failed checks (or the margin) as the anomaly score

Baseline: **Muse Spark vision-only**. Same packing list and image, asked to return pass/fail directly,
with no SAM and no checks. It runs on the same images with the same metrics.

## Status

| Part | State |
|---|---|
| Repo setup, secrets handling, dataset license handling | Done |
| SAM 3.1 API probed; output format verified ([notes](docs/sam-output-format.md)) | Done |
| Dataset download script (`scripts/download_loco.sh`) | Done (tested) |
| SAM client with disk cache (`inspec/sam_client.py`) | Done (tested) |
| SAM output parser (`inspec/segments.py`) | Done (tested) |
| Check-program schema (`inspec/schema.py`) | Done (tested) |
| LLM client: Meta default, optional Baseten (`inspec/llm.py`) | Done (tested); Baseten verified live |
| Packing-list compiler (`inspec/compiler.py`) | Done (tested) |
| Check executor: merging, carve-out, metrics (`inspec/executor.py`) | Done (tested) |
| Calibration loop (`inspec/calibrate.py`) | Done (tested), 3 live runs |
| Evaluation on Screw Bag (`inspec/evaluate.py`, `scripts/e2e.py`) | Done; [results](#results) |
| Damage check, Muse Spark vision (`inspec/damage.py`) | Done (tested); [results](#damage-check-muse-spark-vision) |
| Vision-only baseline (`inspec/baseline.py`) | Partial: damage-only column; a full pass/fail baseline is next |
| Streamlit app (`app.py`) | Planned |

Unit tests: 90 passing (SAM client, parser, schema, LLM client, compiler, executor, calibration, damage).

## Roadmap

| Date | Goal |
|---|---|
| Oct 26 | ✅ Setup, SAM API research, SAM client and parser |
| Oct 27–28 | Check schema, compiler, executor |
| Oct 28 | ✅ First end-to-end run, calibration loop, Screw Bag eval |
| Oct 29–30 | Vision-only baseline; AUROC |
| Oct 31–Nov 1 | Streamlit UI; second LOCO category if time allows |
| Nov 2 | UI polish: show the compile → check → repair loop live |
| Nov 3 | README results (measured numbers only) and the 3-minute video |
| Nov 4 | Buffer; submit by 9:00 PM ET |

If time runs short, cut from the bottom: end-to-end on Screw Bag → calibration → eval vs baseline →
UI polish → stretch goals (Breakfast Box, voice input).

## Tech stack

- **Muse Spark** (Meta Model API): compiler, check repair, vision-only baseline
- **SAM 3.1** (Meta Model API): instance segmentation by text concept
- Python 3.11, OpenAI Python SDK (the Meta Model API is OpenAI-compatible), `meta-sam-parser`
  (Meta's mask decoder), NumPy, Pillow, pytest
- **Baseten** (optional): set `INSPEC_LLM_PROVIDER=baseten` to run the compiler on a Baseten-hosted
  model such as Muse Spark Open. It has no structured output, so the client asks for JSON, validates
  it against the schema and retries with the error.
- Streamlit for the UI (planned)

## Run locally

```bash
git clone https://github.com/Mallard64/inspec.git && cd inspec
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env        # then put your Meta Model API key in .env
scripts/download_loco.sh    # Screw Bag, about 1 GB, into data/
.venv/bin/python -m pytest -q

# compile -> calibrate -> evaluate (writes runs/<name>/)
.venv/bin/python scripts/e2e.py --calib 60 --test
# add the Muse Spark damage check (about 1 vision call per image, cached in .cache/damage)
.venv/bin/python scripts/e2e.py --program runs/<name>/final.json --damage --test
# re-evaluate a saved program without calling Muse Spark
.venv/bin/python scripts/e2e.py --program runs/<name>/final.json --test
```

The first full run makes about 1,400 SAM calls (3 per image), taking a few minutes with 8 threads.
After that, every SAM result comes from `.cache/sam`.

Try the SAM layer on a real image:

```python
from inspec.sam_client import SamClient
from inspec.segments import parse_sam_output

segs = parse_sam_output(SamClient().segment_text("data/screw_bag/train/good/000.png", "washer"))
print([(s.box, s.area) for s in segs])
```

### Environment variables

| Name | Purpose |
|---|---|
| `META_API_KEY` | Meta Model API key (Muse Spark and SAM 3.1). Read from `.env`, never committed. |
| `INSPEC_LLM_PROVIDER` | `meta` (default) or `baseten`: which provider runs the compiler |
| `META_LLM_MODEL` | Override the Muse Spark model (default `muse-spark-1.3`) |
| `BASETEN_API_KEY` | Baseten key, only for `INSPEC_LLM_PROVIDER=baseten` |
| `BASETEN_MODEL` | Baseten model slug. Hackathon keys only work with `meta-models/muse-spark-open-1026` |

Baseten status: verified live. `scripts/e2e.py --provider baseten` runs compile and calibration on
Muse Spark Open (`meta-models/muse-spark-open-1026`). Baseten documents no structured output for
it, so the client asks for plain JSON, validates it and retries with the error. See the Baseten
column in [Results](#results).

## Project structure

```
inspec/
  sam_client.py   # ✅ SAM 3.1 calls, disk cache keyed by (image hash, concept)
  segments.py     # ✅ parse SAM output into boxes and boolean masks
  schema.py       # ✅ check-program schema (pydantic)
  llm.py          # ✅ Muse Spark / Baseten client with validate-and-retry
  compiler.py     # ✅ packing list (+ good images) -> check program (Muse Spark)
  executor.py     # ✅ merge detections into objects, run checks -> verdicts with evidence
  calibrate.py    # ✅ run on good kits, Muse Spark repairs failing checks, re-run
  evaluate.py     # ✅ false-alarm rate and recall per LOCO split and defect type
  damage.py       # ✅ Muse Spark vision check for torn bag, broken/painted part, foreign object
  baseline.py     # Muse Spark vision-only pass/fail baseline (next)
app.py            # Streamlit single page (planned)
scripts/          # ✅ dataset download, e2e runner, Baseten check
docs/             # ✅ verified API notes
tests/            # ✅ unit tests and captured SAM responses
.orchestrator/    # ✅ task briefs and log for delegated coding tasks
```

## Dataset and licensing

MVTec LOCO AD is licensed CC BY-NC-SA 4.0 (non-commercial). It is **not** in this repo:
`scripts/download_loco.sh` fetches it into `data/`, which is gitignored. This project is a
non-commercial hackathon entry.

## How this was built

Solo project. I designed the system and own every decision in it. AI coding tools are used and
disclosed so the contribution is clear:

- **Claude Code**: architecture, the check schema and compiler prompt, the calibration and eval
  design, and review of all code.
- **Muse Code** (Meta's coding agent): well-specified implementation tasks. Each has a written brief
  in [`.orchestrator/tasks/`](.orchestrator/tasks/) and a line in
  [`.orchestrator/log.md`](.orchestrator/log.md). Each task lands as its own branch merge, and every
  diff was reviewed and tested before merge.

Agent instructions are in [`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md).

## Build log

- **Oct 26.** Set up the repo, secrets handling and dataset license handling. Probed SAM 3.1 with
  synthetic images and verified its output format: box coordinates, mask orientation (height first,
  cropped to the box), both mask encodings, and empty results. Chose `one_bit` masks: identical on
  test shapes, 5–170× smaller. Built the dataset script, the SAM client with a disk cache, and the
  parser (23 unit tests). First real run on a good Screw Bag image found the washer that SAM also
  labels as a nut.
- **Oct 28.** Wrote the check-program schema (26 tests). Confirmed that `muse-spark-1.3` structured
  output fills the schema and passes validation from a plain packing list. Found that **SAM ignores
  size words**: on a good Screw Bag image, "screw", "long screw" and "short screw" each return the
  same 2 screws. Muse Spark's first-try program used "long screw" as a SAM concept, which would
  wrongly fail a good kit. So the compiler prompt must use shared concepts split by measured
  length, and this is a second concrete case for the calibration loop.
  Later the same day: built the compiler (`muse-spark-1.3`, valid on the first attempt in 3 of 3
  runs, both screws correctly given concept "screw") and the executor (Muse Code, task 04). Set up
  an optional Baseten provider for Muse Spark Open (not yet tested live). **First end-to-end run:**
  the compiled program, with no size limits yet, rejected 5 of 5 good kits (see
  [above](#why-this-is-hard-and-a-real-example)). Replaced dedupe rules with automatic object
  merging, because SAM calls screw heads "nuts" and labels nuts and washers both ways.
  Feasibility check, **not a result**: with size limits I set by hand from 5 training images, 19 of
  the next 20 good training images pass. The one failure is a washer at 6,715 px² against a
  6,700 px² cut-off, which is the kind of boundary calibration should learn from data.
  Evening: on 100 good training images, nut and washer areas turned out to overlap, so I added a
  `hole` metric (it separates them cleanly) and first-match part order. A touching washer or nut
  hidden inside a screw mask is now carved out, which took good images with 6 objects from 97/100
  to 100/100. Built the calibration loop and the evaluator. First calibration runs went wrong in
  instructive ways. The model kept raising `merge_overlap` and made things worse. It added a tight
  check on hole fraction that rejected good kits. It widened a range to fit one mismeasured screw.
  Fixes: keep-best with regressions reported back to the model, code-computed sorted measurements
  per part, and prompt rules for size-only measure checks and outliers. Then ran the full eval
  three times ([results](#results)). Baseten first returned 401, which turned out to be my own bug: an
  append to `.env` had glued `BASETEN_MODEL=` onto the key line. After the fix, a full run on Muse Spark
  Open (`muse-spark-open-1026`) works end to end.

## Limits

- Evaluated on one LOCO category (Screw Bag) so far. No vision-only baseline yet, so there's no
  comparison number.
- About 1–2% of good kits fail because SAM merges two touching screws into one mask. The program
  can't fix that, and calibration correctly leaves those kits failing.
- The repair is an LLM output, so runs differ (see Results). Each run's program is saved and can
  be re-evaluated without the model.
- Built for kits photographed from a fixed overhead camera, like MVTec LOCO. It hasn't been tested
  on other setups.
- Inspec targets logical errors (wrong counts and wrong parts). Surface defects like scratches or
  contamination are mostly out of scope.
- Parts SAM can't name reliably with a short noun phrase will be hard to check.

## Future improvements

To be filled in honestly at the end of the build.
