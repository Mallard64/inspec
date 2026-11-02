# Inspec

**Type a packing list, show Inspec a photo of the kit, and it tells you what's wrong, with a mask on
every part it counted.**

Built solo for the **Meta Global AI Developer Hackathon** (Indie Developer track, Oct 26 – Nov 4,
2026), on **Muse Spark** and **SAM 3.1**. All code in this repo was written during the event; the
commit history is the record.

- **Demo video:** _coming before submission_ ([shot list](docs/video-script.md))
- **Run it yourself:** [quick start](#quick-start), about 5 minutes plus the dataset download

![The Inspec app: a packing list compiled into checks, then fixed on known-good kits (60/60 good kits rejected before, 2/60 after)](docs/screenshot.png)

## The problem

At a kitting station, a bag with two short screws instead of one long and one short looks almost
like a good one. Visual anomaly detection needs hundreds of example images per product and can't
say *which* rule broke. Asking a vision model "is this kit OK?" gives a yes or no with no evidence,
and it's weak at the thing that matters most here: measuring.

## The idea

Treat the packing list as the spec.

1. **Compile.** Muse Spark turns "1 long screw, 1 short screw, 2 nuts, 2 washers" into explicit
   checks: exactly 1 long screw, exactly 2 nuts, and so on.
2. **Find.** SAM 3.1 segments every part in the photo. Plain code counts and measures the masks
   and runs the checks.
3. **Self-repair.** The checks are run on photos of known-good kits. A check that fails on a good
   kit is wrong by definition, so Muse Spark rewrites it from the evidence and code validates the
   fix. On Screw Bag the first program rejected 60 of 60 good kits; after self-repair, 2 of 60.
   It learned, for example, that a nut's hole is a smaller share of its outline than a washer's.
4. **Look.** A mask can't see a bruise or a torn bag, so Muse Spark answers one damage question
   per packing-list item. Questions that fire on good kits are switched off.

Every verdict names the check that failed and shows the masks it measured.

## Performance

MVTec LOCO AD, held-out test kits, each final configuration evaluated once after the code was
frozen. "Muse Spark alone" is the strongest vision-only baseline I built: the photo, the packing
list and 3 photos of good kits (plus a measured size guide on Screw Bag).

| | Screw Bag: Inspec | Screw Bag: Muse Spark alone | Breakfast Box: Inspec | Breakfast Box: Muse Spark alone |
|---|---|---|---|---|
| Wrong parts, sizes or amounts caught | **137 / 137** | 130 / 137 | **78 / 83** | 68 / 83 |
| Damaged or contaminated caught | 71 / 82 | 69 / 82 | 68 / 90 | 70 / 90 |
| Good kits wrongly rejected | 7 / 122 | 9 / 122 | 4 / 102 | 6 / 102 |
| … of those, hard rejects (FAIL, not REVIEW) | **1 / 122** | n/a | **0 / 102** | n/a |

- **Inspec wins on what can be measured**: wrong screw length, wrong amount of cereal, swapped
  compartments. The gap is significant on both kits (exact paired tests, p = 0.016 and p = 0.002).
- **On damage it ties the vision model** (not significant either way), because that part *is* a
  vision-model call.
- **False alarms are comparable**, and most of Inspec's go to a person rather than being rejected.
  Kits flagged only by the model's damage judgement, or by a measurement within 3% of its limit,
  get **REVIEW** instead of **FAIL**: hard rejects of good kits fall from 7 to 1 (Screw Bag) and
  4 to 0 (Breakfast Box), with nothing that was caught lost. The 3% was chosen on validation kits.
  [Error analysis.](docs/benchmarks.md#error-analysis-and-pass--review--fail)

Inspec's three-way verdicts on the same test kits:

| | Screw Bag: FAIL | REVIEW | PASS | Breakfast Box: FAIL | REVIEW | PASS |
|---|---|---|---|---|---|---|
| Good kits | 1 | 6 | 115 | 0 | 4 | 98 |
| Wrong parts, sizes or amounts | 137 | 0 | 0 | 78 | 0 | 5 |
| Damaged or contaminated | 34 | 37 | 11 | 11 | 57 | 22 |

Every measurable defect Inspec catches is a hard FAIL; damage mostly arrives as REVIEW, since
that verdict rests on the model's judgement rather than a measurement.

### Learning from reviewers

A REVIEW kit goes to a person, who passes or rejects it in the app (with an optional note). Those
decisions come back as **labelled example photos**: with every damage check, Muse Spark first sees
up to 6 reviewed kits ("a reviewer passed this one although almond damage was flagged"), then the
kit to inspect. No model is retrained and no question is switched off.

To measure it without real reviewers, a simulated reviewer passes the known-good *training* kits
that a damage question wrongly flagged (6 photos on Breakfast Box, 2 on Screw Bag; no test
images). Same test kits, code frozen (`39e93ce`) before the held-out half was scored:

| | Screw Bag: without | Screw Bag: with examples | Breakfast Box: without | Breakfast Box: with examples |
|---|---|---|---|---|
| Good kits flagged (REVIEW or FAIL) | 7 / 122 | **2 / 122** | 4 / 102 | **1 / 102** |
| Damaged or contaminated caught | 71 / 82 | **76 / 82** | 68 / 90 | **75 / 90** |
| … held-out (odd) half | 38 / 41 | 39 / 41 | 33 / 45 | 37 / 45 |
| Wrong parts, sizes or amounts caught | 137 / 137 | 137 / 137 | 78 / 83 | 78 / 83 |
| Damage questions that pass calibration | 7 of 7 | 7 of 7 | 6 of 8 | **8 of 8** |

- Fewer false alarms *and* more catches. On Breakfast Box the examples bring back the box-damage
  and almond questions that calibration had switched off: box damage caught goes from 1 to 3 of 4.
- Only one gain is statistically significant: Breakfast Box damage, 7 kits gained and none lost
  (exact paired test, p = 0.016). The others all point the same way but are small (Screw Bag good
  kits 5 better, 0 worse, p = 0.06; Screw Bag damage 6 better, 1 worse, p = 0.13).
- The simulated reviewer is never wrong; real ones will be, and a wrongly passed kit teaches the
  model to miss that damage. The even-numbered anomalies were seen while building this (nothing
  was tuned on them). Details: [benchmarks](docs/benchmarks.md#learning-from-reviewers).

Full tables, per-defect results, how the test set was used, the Muse Spark Open (Baseten) run
and every limit: **[docs/benchmarks.md](docs/benchmarks.md)**.

## Tech stack

- **Muse Spark** (`muse-spark-1.3`, Meta Model API): compiles the packing list, proposes words
  SAM understands, repairs failing checks, answers the damage questions, and is the baseline
- **SAM 3.1** (Meta Model API): segments each part from a short noun phrase
- **Muse Spark Open** on **Baseten** (optional): the same compile and self-repair loop on the open
  model
- Python 3.11, Pydantic (check-program schema, structured output), NumPy, Pillow, OpenAI SDK
  (the Meta Model API is OpenAI-compatible), `meta-sam-parser`, Streamlit, pytest

## Quick start

```bash
git clone https://github.com/Mallard64/inspec.git && cd inspec
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                               # put your Meta Model API key in .env
scripts/download_loco.sh screw_bag breakfast_box   # MVTec LOCO AD, into data/ (gitignored)
.venv/bin/python -m pytest -q

# compile -> self-repair on 60 good kits -> evaluate on the test set (writes runs/<name>/)
.venv/bin/python scripts/e2e.py --calib 60 --test --name mine

.venv/bin/streamlit run app.py                     # the demo page
```

The app reads saved runs (`runs/run3` for Screw Bag, `runs/bb4` for Breakfast Box, made by
`scripts/e2e.py`). In it, **"Run it live"** compiles the list and runs self-repair against the
API, and **"Live model calls"** skips every cache for one kit and lists each Meta model call with
its time. More commands: [reproduce the results](docs/benchmarks.md#reproduce-the-results).

| Variable | Purpose |
|---|---|
| `META_API_KEY` | Meta Model API key (Muse Spark and SAM 3.1). Read from `.env`, never committed |
| `INSPEC_LLM_PROVIDER` | `meta` (default) or `baseten` |
| `BASETEN_API_KEY`, `BASETEN_MODEL` | Only for Baseten; hackathon keys work with `meta-models/muse-spark-open-1026` |

## Future steps

- **Concept-repair tie-break.** When two words fit equally well, prefer the one that finds fewer
  objects. On Muse Spark Open, "dried fruit" beat "banana slice" for the banana chips and also
  matched other items, so 10 of 11 boxes missing their banana chips passed.
- **Height.** Overflowing cereal (0 of 4 caught) looks the same from above; it needs a side view
  or depth.
- **Reviewer examples with real reviewers.** The examples were tested with a simulated reviewer
  who is never wrong. Next: a review queue page, and catching reviewers who disagree with each
  other before their decisions become examples.
- **More kits and cameras.** Three more LOCO categories are one download away; real phone photos
  of real kits haven't been tried.

## More detail

- [Benchmarks](docs/benchmarks.md): every result, significance tests, test-set use, limits
- [How it works](docs/how-it-works.md): why SAM alone isn't enough, the pipeline, the check-program
  schema, the calibration loop, project structure
- [Build log](docs/build-log.md): what was built each day, and how the work was split between me,
  Claude Code and Muse Code
- [SAM 3.1 output notes](docs/sam-output-format.md): the response format, verified against the API

## Dataset and licensing

MVTec LOCO AD (Bergmann et al.) is licensed CC BY-NC-SA 4.0. It is **not** in this repo:
`scripts/download_loco.sh` fetches it into `data/`, which is gitignored. This is a non-commercial
hackathon entry.
