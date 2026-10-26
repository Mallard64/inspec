# Inspec

Type a packing list, show Inspec a photo of the kit, and it tells you what's missing, with a mask on
every part it counted.

Built solo for the **Meta Global AI Developer Hackathon** (Indie Developer track, "Push the Frontier"),
Oct 26 – Nov 4, 2026. All code in this repo was written during the event; the commit history is the
record.

> **Status: day 1 (Oct 26).** Setup, API research and the SAM layer are done. The check compiler,
> executor and calibration loop are not built yet.
> The table below is the source of truth for what works.

- Demo: _not yet_
- Video: _not yet_ (3-minute demo due with submission)

<!-- Screenshot / GIF: packing list → compiled checks → verdict with masks -->

## The problem

Kitting stations pack bags of parts (screws, nuts, washers) by hand. A bag that's missing one washer
looks almost identical to a good one. Classic visual anomaly detection needs many example images per
product and can't tell you *which* rule was broken. Asking a vision model "is this kit OK?" gives a
yes/no with no evidence.

## How it works

```
packing list ──► Muse Spark compiler ──► check program (JSON)
                                            │
kit image ──► SAM 3.1 (one call per part) ──┤
                                            ▼
                                   executor ──► verdict per check + masks as evidence
                                            ▲
known-good kits ──► calibration loop ───────┘  (repairs checks that fail on good kits)
```

1. **Compile.** Muse Spark turns "2 long screws, 2 short screws, 2 nuts, 2 washers" into a typed
   check program: which parts to look for and what counts, sizes, or positions to expect.
2. **Segment.** SAM 3.1 finds every instance of each part (one short noun phrase per request) and
   returns a box and pixel mask for each.
3. **Execute.** Plain Python runs the checks on the masks, so every verdict points at evidence.
   Counting, size comparisons and spatial logic happen here, not in the model prompt.
4. **Calibrate.** Checks are run on kits known to be good. Any check that fails on a good kit is
   wrong, so it's sent back to Muse Spark with the evidence and repaired, then re-run.

The calibration loop is the core idea: the agent tests its own rules against ground truth and fixes
them, and the before/after is measurable.

## Status

| Part | State |
|---|---|
| Repo setup, secrets handling, dataset license handling | Done |
| SAM 3.1 API probed; output format verified ([notes](docs/sam-output-format.md)) | Done |
| Dataset download script (`scripts/download_loco.sh`) | Done (tested) |
| SAM client with disk cache (`inspec/sam_client.py`) | Done (tested) |
| SAM output parser (`inspec/segments.py`) | Done (tested) |
| Check-program schema (`inspec/schema.py`) | Planned |
| Packing-list compiler (`inspec/compiler.py`) | Planned |
| Check executor (`inspec/executor.py`) | Planned |
| Calibration loop (`inspec/calibrate.py`) | Planned |
| Vision-only baseline (`inspec/baseline.py`) | Planned |
| Evaluation on MVTec LOCO AD (`eval/run_eval.py`) | Planned |
| Streamlit app (`app.py`) | Planned |

Results will be added here only after they're measured. No numbers are claimed yet.

## Tech stack

- **Muse Spark** (Meta Model API): packing-list compiler, check repair, vision-only baseline
- **SAM 3.1** (Meta Model API): instance segmentation by text concept
- Python 3.11, OpenAI Python SDK (Meta Model API is OpenAI-compatible), `meta-sam-parser`, NumPy,
  Pillow, pytest
- Streamlit for the UI (planned)

## Dataset

Evaluation uses [MVTec LOCO AD](https://www.mvtec.com/company/research/datasets/mvtec-loco), which
contains "logical" anomalies like missing or extra parts. It's licensed CC BY-NC-SA 4.0, so it is
**not** in this repo. `scripts/download_loco.sh` fetches it into `data/` (gitignored). Primary
category: Screw Bag. Stretch: Breakfast Box.

## Run locally

> App and eval commands will be added as they're built.

```bash
git clone https://github.com/Mallard64/inspec.git && cd inspec
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # then put your Meta Model API key in .env
scripts/download_loco.sh   # Screw Bag, about 1 GB, into data/
.venv/bin/python -m pytest -q
```

### Environment variables

| Name | Purpose |
|---|---|
| `META_API_KEY` | Meta Model API key (Muse Spark and SAM 3.1). Read from `.env`, never committed. |

## Project structure

Planned layout. Files appear as they're built.

```
inspec/
  sam_client.py   # SAM 3.1 calls, disk cache keyed by (image, concept)
  segments.py     # parse SAM output into boxes and masks
  schema.py       # check-program schema (pydantic)
  compiler.py     # packing list + good images -> check program
  executor.py     # run a check program on one image -> verdicts with evidence
  calibrate.py    # run on good images, repair failing checks, re-run
  baseline.py     # Muse Spark vision-only pass/fail baseline
eval/run_eval.py  # recall, false-alarm rate, AUROC per category
app.py            # Streamlit single page
scripts/          # dataset download
docs/             # design notes and verified API facts
tests/
```

## How this was built

Solo project. I designed the system and own every decision in it. I use two AI coding tools, and
that's disclosed here so the contribution is clear:

- **Claude Code** for architecture, the compiler prompt and schema, the calibration and eval logic,
  and reviewing all code.
- **Muse Code** (Meta's coding agent) for well-specified implementation tasks. Each task has a written
  brief in `.orchestrator/tasks/` and an entry in `.orchestrator/log.md`, and every diff is reviewed
  and tested before merge.

Agent instructions are in [`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md).

## Build log

- **Oct 26.** Repo, secrets handling and dataset license handling set up. Probed SAM 3.1 on the
  Meta Model API with synthetic images and verified its output format: box coordinates, mask
  orientation, both mask encodings, and empty results
  ([notes](docs/sam-output-format.md)). Chose `one_bit` masks: identical output on test shapes,
  roughly 5× smaller.
  Built the dataset script, the SAM client with a disk cache, and the SAM parser (23 unit tests).
  First real run on one good Screw Bag image: SAM returned 2 screws, 3 nuts and 2 washers. One
  "nut" mask overlaps a washer mask at IoU 0.98, so it's the same washer under a second label.
  A naive "count nuts" rule would fail this *good* kit. That's the kind of check the calibration
  loop is meant to catch and repair.

## Limits

- Only the SAM layer works so far. See Status.
- Designed for kits photographed from a fixed overhead camera, like MVTec LOCO. It hasn't been
  tested on other setups.
- SAM is unreliable with spatial words and negation, so those checks are done in code. Parts SAM
  can't name well will be hard to check.

## Future improvements

To be filled in honestly at the end of the build.
