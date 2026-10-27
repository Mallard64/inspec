# Inspec

**Type a packing list, show Inspec a photo of the kit, and it tells you what's wrong, with a mask on
every part it counted.**

Built solo for the **Meta Global AI Developer Hackathon**, Indie Developer track, theme **Push the
Frontier** (Meta models on a hard manufacturing problem). Build window Oct 26 – Nov 4, 2026. All code
in this repo was written during the event; the commit history is the record.

> **Status (Oct 27):** the SAM 3.1 layer (dataset download, API client with a disk cache, and mask
> parser) is built and tested. The check compiler, executor, calibration loop, evaluation and UI
> are designed but **not built yet**. The [Status](#status) table is the source of truth. No
> results are claimed until they're measured.

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
- **Proof plan.** Evaluate on MVTec LOCO AD (Screw Bag) against a vision-only Muse Spark baseline,
  reporting recall, false-alarm rate and AUROC.

## Why this is hard (and a real example)

On the first real image we ran, a **good** Screw Bag, SAM 3.1 returned 2 screws, 2 washers and
**3 nuts**. One "nut" mask overlaps a washer mask at IoU 0.98: it's the same washer under two labels.
A naive "count nuts = 2" rule would reject this correct kit.

This is the failure the calibration loop is built for: the rule is wrong, the good kit proves it,
and the evidence (two masks on one object) says how to fix it. This is one image, an observation and
not a result; the eval will show whether it generalises.

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
using structured output. Draft of the shape, **not final**:

```json
{
  "parts": [
    {"id": "long_screw",  "sam_concept": "screw",  "select": {"area_rank": "largest", "n": 1}},
    {"id": "short_screw", "sam_concept": "screw",  "select": {"area_rank": "smallest", "n": 1}},
    {"id": "nut",         "sam_concept": "nut"},
    {"id": "washer",      "sam_concept": "washer"}
  ],
  "checks": [
    {"id": "nut_count",    "type": "count", "part": "nut",    "expect": 2},
    {"id": "washer_count", "type": "count", "part": "washer", "expect": 2},
    {"id": "screw_count",  "type": "count", "part": "screw",  "expect": 2},
    {"id": "short_screw_size", "type": "area_ratio", "part": "short_screw",
     "relative_to": "long_screw", "range": [0.4, 0.8]}
  ],
  "dedupe": [{"keep": "washer", "drop": "nut", "iou_above": 0.8}]
}
```

Design rules, taken from what SAM 3.1 actually does well:
- **One short noun phrase per SAM call** ("nut", not "nuts and washers"). Verified behaviour.
- **No spatial words or negation in SAM prompts.** Size, position, "missing" and "extra" are all
  computed in Python from masks, where they're exact and testable.
- **Check types are a small fixed set** (count, present, area or area ratio, relative position), so
  every check is executable and explainable.

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

1. Run the program on a handful of known-good training images.
2. Any check that fails on a good image is a wrong rule. Send Muse Spark the check, the measured
   values and a summary of the masks involved (e.g. "nut mask 3 overlaps washer mask 2 at
   IoU 0.98").
3. Muse Spark returns a repaired check (a new dedupe rule, a widened range, a different concept
   phrase), constrained to the same schema.
4. Re-run. Stop when all good images pass or after a fixed number of rounds. Every repair is logged
   and shown in the UI.

Repairs are only judged on good images, never on anomalies, so calibration can't learn the test
set.

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

Metrics, image-level, per split:
- **Recall** on logical anomalies (bad kits caught)
- **False-alarm rate** on good kits (good kits rejected)
- **AUROC**, using the number of failed checks (or the margin) as the anomaly score
- **Calibration before vs after:** false-alarm rate on `validation/good` with the raw compiled
  program vs the repaired one

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
| Check-program schema (`inspec/schema.py`) | Next |
| Packing-list compiler (`inspec/compiler.py`) | Planned |
| Check executor (`inspec/executor.py`) | Planned |
| Calibration loop (`inspec/calibrate.py`) | Planned |
| Vision-only baseline (`inspec/baseline.py`) | Planned |
| Evaluation on MVTec LOCO AD (`eval/run_eval.py`) | Planned |
| Streamlit app (`app.py`) | Planned |

Unit tests: 23 passing (SAM client and parser). No evaluation results yet.

## Roadmap

| Date | Goal |
|---|---|
| Oct 26 | ✅ Setup, SAM API research, SAM client and parser |
| Oct 27–28 | Check schema, compiler, executor |
| Oct 29 | **First end-to-end run:** packing list → checks → verdict with masks on Screw Bag |
| Oct 30–31 | Calibration loop with before/after numbers |
| Nov 1 | Vision-only baseline and full Screw Bag eval |
| Nov 2 | Streamlit UI that shows the compile → check → repair loop live |
| Nov 3 | README results (measured numbers only) and the 3-minute video |
| Nov 4 | Buffer; submit by 9:00 PM ET |

If time runs short, cut from the bottom: end-to-end on Screw Bag → calibration → eval vs baseline →
UI polish → stretch goals (Breakfast Box, voice input).

## Tech stack

- **Muse Spark** (Meta Model API): compiler, check repair, vision-only baseline
- **SAM 3.1** (Meta Model API): instance segmentation by text concept
- Python 3.11, OpenAI Python SDK (the Meta Model API is OpenAI-compatible), `meta-sam-parser`
  (Meta's mask decoder), NumPy, Pillow, pytest
- Streamlit for the UI (planned)

## Run locally

App and eval commands will be added as they're built.

```bash
git clone https://github.com/Mallard64/inspec.git && cd inspec
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env        # then put your Meta Model API key in .env
scripts/download_loco.sh    # Screw Bag, about 1 GB, into data/
.venv/bin/python -m pytest -q
```

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

## Project structure

```
inspec/
  sam_client.py   # ✅ SAM 3.1 calls, disk cache keyed by (image hash, concept)
  segments.py     # ✅ parse SAM output into boxes and boolean masks
  schema.py       # check-program schema (pydantic)
  compiler.py     # packing list + good images -> check program (Muse Spark)
  executor.py     # run a check program on one image -> verdicts with evidence
  calibrate.py    # run on good images, repair failing checks, re-run
  baseline.py     # Muse Spark vision-only pass/fail baseline
eval/run_eval.py  # recall, false-alarm rate, AUROC
app.py            # Streamlit single page
scripts/          # ✅ dataset download
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
  labels as a nut (see [above](#why-this-is-hard-and-a-real-example)).

## Limits

- Only the SAM layer works so far. See Status.
- Built for kits photographed from a fixed overhead camera, like MVTec LOCO. It hasn't been tested
  on other setups.
- Inspec targets logical errors (wrong counts and wrong parts). Surface defects like scratches or
  contamination are mostly out of scope.
- Parts SAM can't name reliably with a short noun phrase will be hard to check.

## Future improvements

To be filled in honestly at the end of the build.
