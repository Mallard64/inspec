# Inspec

**Type a packing list, show Inspec a photo of the kit, and it tells you what's wrong, with a mask on
every part it counted.**

Built solo for the **Meta Global AI Developer Hackathon**, Indie Developer track, theme **Push the
Frontier** (Meta models on a hard manufacturing problem). Build window Oct 26 – Nov 4, 2026. All code
in this repo was written during the event; the commit history is the record.

> **Status (Oct 30):** the full pipeline works end to end on two MVTec LOCO kits, Screw Bag and
> Breakfast Box: packing list → Muse Spark
> compiler → SAM 3.1 → checks → Muse Spark calibration loop → evaluation, compared against a
> vision-only Muse Spark baseline. A Streamlit page (`app.py`) shows the loop with part masks.
> [Results](#results) are measured on the held-out test set. The [Status](#status) table is the
> source of truth.

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
- **Result so far (MVTec LOCO, held-out test sets).** On Screw Bag the calibrated program catches
  all 137 kits with wrong parts, counts or screw sizes, and rejects 1–2 of 122 good kits; before
  calibration it rejected every good kit. On a second kit, Breakfast Box, the same code (plus three
  general fixes) catches 78 of 83 logical defects with 0 of 102 false alarms. The strongest vision-only baseline I could
  build (Muse Spark with 3 reference photos and a size guide) catches 130 of 137, counting as well
  as Inspec but missing 6 of 65 wrong-size-screw kits. False-alarm rates are comparable.
  [Details and significance tests.](#vision-only-baseline)

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
- **Not done yet:** AUROC (verdicts are binary for now) and the vision baseline on Breakfast Box.
  See [Breakfast Box](#second-category-breakfast-box).

### How the test set was used

A perfect score deserves suspicion, so here is the full record (from the session log and `runs/`):

- **Where the numbers come from.** Every part limit and length range in a program is set by the
  calibration loop from 60 `train/good` images; the code that computes them never reads
  validation or test. Development before the first test run (merging, the hole metric, the
  carve-out, the repair prompt) used `train/good` and `validation/good` only.
- **How often Screw Bag test was evaluated: 10 times.** Runs 1, 2 and 3, the Baseten run, the damage-check
  run and two baseline runs; then two more baseline runs (3 references, with and without a size
  guide), made with Inspec frozen, and the kit-neutral damage prompt (`sb-final`): 10 in all. Each run's program and
  report are saved.
- **What changed between test runs.** Once, for the part checks: after run 2 I added the "lone
  outlier is a measurement failure" rule to the repair prompt. The trigger was run 2's calibration
  notes on training data (it widened the short-screw range to 419 px to fit one training kit), not
  its test score, which was already 137/137. **Run 1 had no change after seeing test and also scored
  137/137 with 1 of 122 false alarms.**
- **Breakfast Box test: evaluated twice**, each time after freezing. First the unchanged method
  (`bb1`; a crash in the SAM parser before any result doesn't count). I then saw its per-defect
  numbers on the whole test set, chose to work on amounts and a general damage prompt, developed
  both on the even-numbered anomalies only, froze (`188ea10`) and evaluated once more (`bb4-final`).
  The odd half is reported separately; it scores like the dev half.
- **Screw Bag with the kit-neutral damage prompt:** one more evaluation (`sb-final`), same protocol.
- **The one place I tuned on test images** is the damage check's `part_broken` wording, on the
  even-numbered structural images. That's disclosed under [Damage check](#damage-check-muse-spark-vision),
  with the untouched odd half reported separately.
- **Why 137/137 is plausible.** Every logical defect in Screw Bag is a whole missing or extra
  part, a second screw of the wrong type (43% longer or shorter), or a screw about 28% short.
  Good-kit screws vary by about 3% and the learned ranges sit about 4% outside that, so these
  defects are far outside them. Structural defects, which aren't counting or size problems, get
  43%.

### Damage check (Muse Spark vision)

Part checks count and measure; they can't see a torn bag or paint. So
[`inspec/damage.py`](inspec/damage.py) asks Muse Spark four yes/no questions about each photo:
container damaged, item broken, item discoloured, foreign object. The prompt names no kit: it is
built from the kit name and packing list, and the same wording runs on Screw Bag and Breakfast
Box. Calibration uses the part checks' rule: a question that fires on more than 2 of 60 good
calibration kits is switched off. On Screw Bag none did (one fired once), so all four stay on. A
kit is rejected if a part check fails or the damage check finds something (`runs/sb-final`:
`scripts/e2e.py --program runs/run3/final.json --damage --test --calib 60`):

| | Part checks only | Damage check only | Both |
|---|---|---|---|
| False alarms, `validation/good` (60) | 2 (3.3%) | 2 | 4 (6.7%) |
| False alarms, `test/good` (122) | 2 (1.6%) | 4 | 6 (4.9%) |
| Caught, `test/logical_anomalies` (137) | 137 | 3 | 137 |
| Caught, `test/structural_anomalies` (82) | 35 (43%) | 53 (65%) | **69 (84%)** |
| … bag broken / colour / contamination / part broken | 0/16, 0/16, 19/25, 16/25 | 14/16, 14/16, 14/25, 11/25 | 14/16, 14/16, 23/25, 18/25 |

The two halves of the result come from different methods. Part checks find wrong counts and some
broken parts. Muse Spark finds bag damage and paint. Each is poor at the other's job.
"Damage check only" catches just 3 of 137 logical defects because it never asks about counts.
The fair vision-only comparison is [below](#vision-only-baseline).

How honest is this? Both damage prompts were developed on the even-numbered test anomalies and
evaluated once on the odd half after the code was frozen. With both checks: 33/41 on the dev half,
**36/41 on the held-out half**. An earlier prompt written only for Screw Bag ("washers are closed
rings") scored a little higher (71/82, 5/122 false alarms); I replaced it so the same prompt works
for any kit.

### Vision-only baseline

What you'd build without Inspec: one Muse Spark call with the packing list and the photo, no SAM,
no checks, no calibration ([`inspec/baseline.py`](inspec/baseline.py)). The model reports how many
of each listed part it sees and whether anything is damaged; the kit fails if a count is off or it
reports damage. I tried to make it as strong as I could before comparing:

- **0 / 1 / 3 ref:** shown 0, 1 or 3 good training kits first (`--references N`).
- **3 ref + size guide:** also told, in words, what Inspec's calibration measured on training
  kits: "the long screw is about 43% longer than the short screw, and screws of one type vary in
  length by only about 3%", and that a screw of neither size is wrong (`--hint`).

| | 0 ref | 1 ref | 3 ref | 3 ref + size guide | Inspec part checks | Inspec + damage check |
|---|---|---|---|---|---|---|
| False alarms, `validation/good` (60) | 2 | 1 | 5 | 3 | 2 | 4 |
| False alarms, `test/good` (122) | 5 | 4 | 9 | 9 | 2 | 6 |
| Caught, `test/logical_anomalies` (137) | 79 | 106 | 116 | 130 | **137** | **137** |
| … missing / extra parts (72 kits) | 71 | 71 | 72 | 71 | 72 | 72 |
| … wrong-size screws (65 kits) | 8 | 35 | 44 | 59 | **65** | **65** |
| Caught, `test/structural_anomalies` (82) | 63 | 66 | 71 | 69 | 35 | 69 |

Inspec columns are run 3's program, with the kit-neutral damage check. "Wrong-size screws" are LOCO's `screw_too_long` (21),
`screw_too_short` (20), `1_very_short_screw` (17) and `2_very_short_screws` (7); the other 72
kits have only missing or extra parts (24 of them more than one such defect). Measured on the
masks, these are not subtle: a `screw_too_long` kit holds two long screws (414–422 px each)
instead of one long and one short, `screw_too_short` holds two short ones (287–298 px), and a very
short screw is 203–217 px against a normal 288–296 px (about 28% shorter).

Against the strongest baseline (3 ref + size guide), on the same kits, with exact paired tests:

| | Inspec + damage | Baseline | Only Inspec catches | Only baseline catches | p |
|---|---|---|---|---|---|
| Logical defects (137) | 137 | 130 | 7 | 0 | 0.016 |
| Structural defects (82) | 69 | 69 | 7 | 7 | 1.0 |
| Good test kits rejected (122) | 6 (2 without damage check) | 9 | 5 | 8 | 0.58 (0.07) |

What this shows, without spin:

- **Counting is a tie.** Muse Spark alone gets 71–72 of 72 missing/extra-part kits.
- **Size is where Inspec wins, but by less than the first baseline suggested.** Zero-shot, the model
  catches 8 of 65 wrong-size-screw kits; with references and a size guide, 59. Inspec gets all 65,
  and the 7 logical kits only one side catches all go Inspec's way (p = 0.016). In those 7, the
  model reports "1 long screw, 1 short screw … the kit is fine" for a bag holding two short screws.
- **The size guide is itself a measurement.** The baseline only got to 59 once I told it the
  ratio Inspec's calibration had measured. Without someone measuring, it sits at 35–44.
- **False alarms are comparable.** 2–6 vs 9 of 122 leans Inspec's way but isn't significant.
  Adding reference photos made the baseline catch more and reject more good kits.
- **Damage is a vision-model job.** SAM masks show what a part is and how big, not whether it's
  scratched, painted or torn, so the part checks alone get 35 of 82 structural defects. The damage
  check (a Muse Spark vision call) brings that to 69, level with the baseline. Inspec + damage is
  a hybrid by design: **measure what can be measured, ask the model about the rest.**
- **Evidence.** A baseline verdict is a sentence; an Inspec verdict names the failed check and
  the masks it measured, which an operator can verify at a glance.
- **Scope.** One LOCO category (Screw Bag), one baseline run per variant. Differences of a few
  kits are within run-to-run noise; only the logical-defect gap is statistically supported.

### Second category: Breakfast Box

Packing list "2 tangerines, 1 nectarine, granola, banana chips, almonds". No code is specific to
this kit. Compiled, concept-checked and calibrated on 60 `train/good` images, checked on
`validation/good`. The general fixes it needed were developed on the even-numbered test
anomalies; the code was then frozen (commit `188ea10`) and evaluated once (`runs/bb4-final`).

| | First frozen run (`bb1`) | Final (`bb4`) part checks | Final + damage check |
|---|---|---|---|
| False alarms, `validation/good` (62) | 0 | 0 | 4 (6.5%) |
| False alarms, `test/good` (102) | 0 | 0 | 4 (3.9%) |
| Caught, `test/logical_anomalies` (83) | 66 (80%) | **78 (94%)** | 78 |
| … held-out (odd) half (41) | | 38 | 38 |
| Caught, `test/structural_anomalies` (90) | 12 (13%) | 11 | **45 (50%)** |
| … held-out (odd) half (45) | | 5 | 24 |

By defect type, final with both checks:

- **Caught fully:** all 8 wrong fruit-count types (19/19), missing almonds / bananas / cereal /
  toppings (41/41), wrong ratio (12/12), compartments swapped (3/3), crushed toppings (7/7).
- **Partly:** underflow 3/4, contamination 34/40, mixed cereals 2/8, box damaged 1/4.
- **Missed:** overflow 0/4 (a heap that's too high has the same area from above) and **damaged
  fruit 1/31**, the largest structural type. See below.

What it took (all general, all also applied to Screw Bag):

- **Concept repair (new agent step).** SAM didn't know the compiler's words: "nectarine" found
  nothing on 45% of good kits, "banana chip" on 55%. Before calibration, Muse Spark proposes
  other phrases for any part SAM misses on good kits, each is tried on 20 good kits, and the one
  whose count best fits the packing list wins: "apple" for the nectarine (95%), "banana" for the
  chips (100%). Scoring by count rejects "fruit", which finds every fruit in the box.
  [`inspec/concepts.py`](inspec/concepts.py). On Screw Bag every concept is always found, so this
  step changes nothing there.
- **Amounts.** The cereal is one SAM mask per kit, so its area is its amount. The repair prompt
  now asks for an area range on such single-mass bulk items; calibration set granola to
  375k–481k px (good kits: 391k–462k). That catches underflow, swapped compartments (the cereal
  ends up in the small compartment) and wrong ratios.
- **Rules in code, not just the prompt.** One repair added a length range to the nectarine, which
  the prompt forbids for items with no listed size; it passed every calibration kit and then
  rejected 7 of 62 good validation kits. The repair validator now rejects length checks except on
  size-split parts, area checks except on bulk parts, and hole checks, and sends the reason back
  to the model. All four reported Screw Bag programs pass the new validator unchanged.
- **Ties count.** Calibration kept a repair only if more good kits passed, so a repair that added
  the granola range at no cost was thrown away. Ties are now kept.
- **Unquantified items** compile to "present" (min 1, no max) instead of "exactly 1".
- **Large SAM masks** come back downscaled to 1024 px on the long side; the parser now resizes
  them ([notes](docs/sam-output-format.md)).

Where it stops:

- **Damaged fruit (1/31).** The kit-neutral damage prompt does ask about bruised or cut items, but
  on good Breakfast Box trays Muse Spark reported "broken" items on 4 of 60 kits (chipped almonds,
  broken banana chips, which are normal) and a "cracked tray" on 24 of 60 (a black slot moulded
  into every tray). Calibration switched both questions off, as designed, which also switched off
  bruised-fruit detection. Showing the model a known-good kit for reference made things worse (it
  started comparing the two photos: 42 of 60 good Screw Bags flagged for a "foreign object"), so
  that was dropped.
- **Overflow (0/4)** isn't visible as area from above.
- **Known gap.** For a presence-only item any phrase that finds something fits, so "banana" beat
  "fruit" for the chips only by list order.

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

Baseline: **Muse Spark vision-only**. Same packing list and image, asked for per-part counts and
damage, with no SAM and no checks. It runs on the same images with the same metrics
([results](#vision-only-baseline)).

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
| Damage check, Muse Spark vision (`inspec/damage.py`) | Done (tested), kit-neutral prompt; [results](#damage-check-muse-spark-vision) |
| Concept repair before calibration (`inspec/concepts.py`) | Done (tested); used on [Breakfast Box](#second-category-breakfast-box) |
| Vision-only baseline (`inspec/baseline.py`, `scripts/baseline.py`) | Done (tested); [results](#vision-only-baseline) |
| Streamlit app (`app.py`, overlay in `inspec/overlay.py`) | Done; runs on saved runs and cached results, live recompile optional |

Unit tests: 100 passing (SAM client, parser, schema, LLM client, compiler, concept repair, executor, calibration,
damage, baseline, overlay). The app was smoke-tested headless with Streamlit's `AppTest`.

## Roadmap

| Date | Goal |
|---|---|
| Oct 26 | ✅ Setup, SAM API research, SAM client and parser |
| Oct 27–28 | Check schema, compiler, executor |
| Oct 28 | ✅ First end-to-end run, calibration loop, Screw Bag eval |
| Oct 29 | ✅ Damage check, vision-only baseline, Streamlit UI |
| Oct 30–Nov 1 | AUROC; second LOCO category if time allows |
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
- Streamlit for the UI

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
# vision-only baseline (1 Muse Spark call per image, cached in .cache/baseline)
.venv/bin/python scripts/baseline.py --name baseline1 --references 1

# the demo page: pick a run, see its calibration rounds, inspect any kit with masks
.venv/bin/streamlit run app.py
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
  concepts.py     # ✅ swap concepts SAM misses on good kits for ones it finds (Muse Spark + SAM)
  calibrate.py    # ✅ run on good kits, Muse Spark repairs failing checks, re-run
  evaluate.py     # ✅ false-alarm rate and recall per LOCO split and defect type
  damage.py       # ✅ Muse Spark vision check for torn bag, broken/painted part, foreign object
  baseline.py     # ✅ Muse Spark vision-only baseline: counts + damage from the photo
  overlay.py      # ✅ draw part masks and labels on a kit photo
app.py            # ✅ Streamlit page: compile -> calibrate -> inspect with masks -> eval
scripts/          # ✅ dataset download, e2e runner, baseline runner, Baseten check
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
- **Oct 29.** Added the Muse Spark damage check (structural recall 43% → 87%). Built the vision-only
  baseline and ran it zero-shot and with one reference photo. It was stronger than I expected: it
  counts parts nearly as well as Inspec. Inspec's clear advantage is size: 65 of 65 wrong-size
  screw kits caught against the baseline's 8–35 (revised on Oct 30, below). Muse Code
  built the Streamlit page and overlay (task 06); in review I fixed part colours that changed
  between images, a PASS banner that showed above a damage FAIL, and unreadably small labels.
- **Oct 30.** Stress-tested the claim. Counted test-set use from the session log (9 evaluations;
  one prompt change between part-check test runs, made for a training-data reason; written up in
  [How the test set was used](#how-the-test-set-was-used)). Measured the "wrong-length" defects on
  the masks: they are swapped screw types and stubs, not 10% length errors, so I corrected that
  wording. Strengthened the baseline with 3 reference photos and a size guide: it went from 35 to
  59 of 65 wrong-size kits, so the gap is real (p = 0.016) but much smaller than first reported.
  Started Breakfast Box. SAM didn't know "nectarine" or "banana chip", so I added a concept-repair
  step before calibration (it picked "apple" and "banana"). Fixed bulk items compiled as "exactly 1"
  and a parser crash on SAM's downscaled large masks. Frozen, one test run: 0 of 102 false alarms,
  all 60 fruit-count and missing-item kits caught, 66 of 83 logical overall, 12 of 90 structural.
  Then, developing on the even half only: an area range for single-mass bulk items, measure rules
  enforced in the validator (the model had put a length range on the nectarine), tied repairs
  kept, and a damage prompt that names no kit. Tried a reference photo in the damage check; it
  backfired, so it's gone. Froze at `188ea10`, evaluated once: Breakfast Box 78/83 logical and
  45/90 structural, 4/102 false alarms; Screw Bag with the new damage prompt 69/82 structural
  (36/41 on the held-out half) against 71/82 for the old Screw Bag-specific prompt.

## Limits

- Two LOCO categories. Breakfast Box has no vision baseline yet, and its damaged fruit (31 kits)
  is almost entirely missed.
- The baseline is one prompt design in four variants, each run once per image. More reference
  photos and the size guide closed most of the size gap (8 → 59 of 65); a better prompt might
  close more. The comparison shows where each approach is weak, not a ceiling for vision-only
  models.
- About 1–2% of good kits fail because SAM merges two touching screws into one mask. The program
  can't fix that, and calibration correctly leaves those kits failing.
- The repair is an LLM output, so runs differ (see Results). Each run's program is saved and can
  be re-evaluated without the model.
- Built for kits photographed from a fixed overhead camera, like MVTec LOCO. It hasn't been tested
  on other setups.
- The part checks target logical errors (counts, sizes). Surface damage relies on the Muse Spark
  damage check, which adds false alarms (2 → 5 of 122 good test kits).
- Parts SAM can't name reliably with a short noun phrase will be hard to check.

## Future improvements

To be filled in honestly at the end of the build.
