# Benchmarks

Every number Inspec reports, how it was measured, and how the test set was used. Back to the [README](../README.md).

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
- **How often Screw Bag test was evaluated: 12 times.** Runs 1, 2 and 3, the Baseten run, the damage-check
  run and two baseline runs; then two more baseline runs (3 references, with and without a size
  guide), made with Inspec frozen, the kit-neutral damage prompt (`sb-final`) and the per-item
  damage questions (`sb-final2`), and PASS / REVIEW / FAIL (`sb-final2-triage`): 12 in all. Each run's program and
  report are saved.
- **What changed between test runs.** Once, for the part checks: after run 2 I added the "lone
  outlier is a measurement failure" rule to the repair prompt. The trigger was run 2's calibration
  notes on training data (it widened the short-screw range to 419 px to fit one training kit), not
  its test score, which was already 137/137. **Run 1 had no change after seeing test and also scored
  137/137 with 1 of 122 false alarms.**
- **Breakfast Box test: evaluated five times** (plus two baseline runs), each time after freezing;
  the fourth is the Muse Spark Open run, with code unchanged since `6aa7546`, and the fifth the
  PASS / REVIEW / FAIL scoring (`429343c`), which reuses the frozen program and damage answers. First the unchanged method
  (`bb1`; a crash in the SAM parser before any result doesn't count). I then saw its per-defect
  numbers on the whole test set, chose to work on amounts and a general damage prompt, developed
  both on the even-numbered anomalies only, froze (`188ea10`) and evaluated once more (`bb4-final`).
  The odd half is reported separately; it scores like the dev half. After the baseline run showed
  Inspec's damage check missing bruised fruit (1/31), I traced it on training kits (calibration
  had switched off the one shared "item broken" question, see below), changed it to per-item
  questions, checked that on `train/good`, `validation/good` and the even-numbered anomalies,
  froze (`6aa7546`) and evaluated once more (`bb5-final`, and `sb-final2` for Screw Bag).
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
[`inspec/damage.py`](../inspec/damage.py) asks Muse Spark yes/no questions about each photo: three
about the whole kit (container damaged, item discoloured, foreign object) and one "is any of the
<item> damaged?" per packing-list item. The prompt names no kit: it is built from the kit name and
packing list, and the same code runs on Screw Bag and Breakfast Box. Calibration uses the part
checks' rule: a question that fires on more than 2 of 60 good calibration kits is switched off.
On Screw Bag none did, so all seven stay on. A kit is rejected if a part check fails or the
damage check finds something (`runs/sb-final2`:
`scripts/e2e.py --program runs/run3/final.json --damage --test --calib 60`):

| | Part checks only | Damage check only | Both |
|---|---|---|---|
| False alarms, `validation/good` (60) | 2 (3.3%) | 1 | 3 (5.0%) |
| False alarms, `test/good` (122) | 2 (1.6%) | 5 | 7 (5.7%) |
| Caught, `test/logical_anomalies` (137) | 137 | 5 | 137 |
| Caught, `test/structural_anomalies` (82) | 35 (43%) | 57 (70%) | **71 (87%)** |
| … bag broken / colour / contamination / part broken | 0/16, 0/16, 19/25, 16/25 | 15/16, 13/16, 16/25, 13/25 | 15/16, 13/16, 23/25, 20/25 |

**Why per item.** What's normal differs by item. With one shared "item broken" question, chipped
almonds (normal) fired it on 4 of 60 good Breakfast Boxes, calibration switched it off, and with
it went bruised-fruit detection: 1 of 31 caught. Per item, calibration switches off only
`almonds_damaged` (5/60) and keeps `tangerines_damaged` and `nectarine_damaged` (0/60 each).

The two halves of the result come from different methods. Part checks find wrong counts and some
broken parts. Muse Spark finds bag damage and paint. Each is poor at the other's job.
"Damage check only" catches just 3 of 137 logical defects because it never asks about counts.
The fair vision-only comparison is [below](#vision-only-baseline).

How honest is this? Each damage prompt was developed on the even-numbered test anomalies and
evaluated on the odd half only after the code was frozen. With both checks: 33/41 on the dev half,
**38/41 on the held-out half**. Earlier versions, for the record: a prompt written only for Screw
Bag got 71/82 with 5/122 false alarms; the first kit-neutral prompt, one shared "item broken"
question, got 69/82 with 6/122.

### Vision-only baseline

What you'd build without Inspec: one Muse Spark call with the packing list and the photo, no SAM,
no checks, no calibration ([`inspec/baseline.py`](../inspec/baseline.py)). The model reports how many
of each listed part it sees and whether anything is damaged; the kit fails if a count is off or it
reports damage. I tried to make it as strong as I could before comparing:

- **0 / 1 / 3 ref:** shown 0, 1 or 3 good training kits first (`--references N`).
- **3 ref + size guide:** also told, in words, what Inspec's calibration measured on training
  kits: "the long screw is about 43% longer than the short screw, and screws of one type vary in
  length by only about 3%", and that a screw of neither size is wrong (`--hint`).

| | 0 ref | 1 ref | 3 ref | 3 ref + size guide | Inspec part checks | Inspec + damage check |
|---|---|---|---|---|---|---|
| False alarms, `validation/good` (60) | 2 | 1 | 5 | 3 | 2 | 3 |
| False alarms, `test/good` (122) | 5 | 4 | 9 | 9 | 2 | 7 |
| Caught, `test/logical_anomalies` (137) | 79 | 106 | 116 | 130 | **137** | **137** |
| … missing / extra parts (72 kits) | 71 | 71 | 72 | 71 | 72 | 72 |
| … wrong-size screws (65 kits) | 8 | 35 | 44 | 59 | **65** | **65** |
| Caught, `test/structural_anomalies` (82) | 63 | 66 | 71 | 69 | 35 | 71 |

Inspec columns are run 3's program, with the per-item damage check (`sb-final2`). "Wrong-size screws" are LOCO's `screw_too_long` (21),
`screw_too_short` (20), `1_very_short_screw` (17) and `2_very_short_screws` (7); the other 72
kits have only missing or extra parts (24 of them more than one such defect). Measured on the
masks, these are not subtle: a `screw_too_long` kit holds two long screws (414–422 px each)
instead of one long and one short, `screw_too_short` holds two short ones (287–298 px), and a very
short screw is 203–217 px against a normal 288–296 px (about 28% shorter).

Against the strongest baseline (3 ref + size guide), on the same kits, with exact paired tests:

| | Inspec + damage | Baseline | Only Inspec catches | Only baseline catches | p |
|---|---|---|---|---|---|
| Logical defects (137) | 137 | 130 | 7 | 0 | 0.016 |
| Structural defects (82) | 71 | 69 | 7 | 5 | 0.77 |
| Good test kits rejected (122) | 7 (2 without damage check) | 9 | 6 | 8 | 0.79 (0.07) |

What this shows, without spin:

- **Counting is a tie.** Muse Spark alone gets 71–72 of 72 missing/extra-part kits.
- **Size is where Inspec wins, but by less than the first baseline suggested.** Zero-shot, the model
  catches 8 of 65 wrong-size-screw kits; with references and a size guide, 59. Inspec gets all 65,
  and the 7 logical kits only one side catches all go Inspec's way (p = 0.016). In those 7, the
  model reports "1 long screw, 1 short screw … the kit is fine" for a bag holding two short screws.
- **The size guide is itself a measurement.** The baseline only got to 59 once I told it the
  ratio Inspec's calibration had measured. Without someone measuring, it sits at 35–44.
- **False alarms are comparable.** 2–7 vs 9 of 122 leans Inspec's way but isn't significant.
  Adding reference photos made the baseline catch more and reject more good kits.
- **Damage is a vision-model job.** SAM masks show what a part is and how big, not whether it's
  scratched, painted or torn, so the part checks alone get 35 of 82 structural defects. The damage
  check (a Muse Spark vision call) brings that to 71, level with the baseline (69). Inspec + damage is
  a hybrid by design: **measure what can be measured, ask the model about the rest.**
- **Evidence.** A baseline verdict is a sentence; an Inspec verdict names the failed check and
  the masks it measured, which an operator can verify at a glance.
- **Scope.** One LOCO category (Screw Bag), one baseline run per variant. Differences of a few
  kits are within run-to-run noise; only the logical-defect gap is statistically supported.

### Second category: Breakfast Box

Packing list "2 tangerines, 1 nectarine, granola, banana chips, almonds". No code is specific to
this kit. Compiled, concept-checked and calibrated on 60 `train/good` images, checked on
`validation/good`. The general fixes it needed were developed on the even-numbered test
anomalies; the code was then frozen and evaluated once: part checks at `188ea10`
(`runs/bb4-final`), the per-item damage check at `6aa7546` (`runs/bb5-final`).

| | First frozen run (`bb1`) | Final part checks | + shared damage question (`bb4-final`) | + per-item damage questions (`bb5-final`) |
|---|---|---|---|---|
| False alarms, `validation/good` (62) | 0 | 0 | 4 (6.5%) | 5 (8.1%) |
| False alarms, `test/good` (102) | 0 | 0 | 4 (3.9%) | 4 (3.9%) |
| Caught, `test/logical_anomalies` (83) | 66 (80%) | **78 (94%)** | 78 | 78 |
| … held-out (odd) half (41) | | 38 | 38 | 38 |
| Caught, `test/structural_anomalies` (90) | 12 (13%) | 11 | 45 (50%) | **68 (76%)** |
| … held-out (odd) half (45) | | 5 | 24 | 33 |

By defect type, final with both checks:

- **Caught fully:** all 8 wrong fruit-count types (19/19), missing almonds / bananas / cereal /
  toppings (41/41), wrong ratio (12/12), compartments swapped (3/3), crushed toppings (7/7).
- **Mostly:** contamination 35/40, damaged fruit 23/31, underflow 3/4.
- **Missed:** overflow 0/4 (a heap that's too high has the same area from above), mixed cereals
  2/8, box damaged 1/4 (the "container damaged" question fires on the tray's moulded slot on
  26 of 60 good kits, so calibration switches it off).

What it took (all general, all also applied to Screw Bag):

- **Concept repair (new agent step).** SAM didn't know the compiler's words: "nectarine" found
  nothing on 45% of good kits, "banana chip" on 55%. Before calibration, Muse Spark proposes
  other phrases for any part SAM misses on good kits, each is tried on 20 good kits, and the one
  whose count best fits the packing list wins: "apple" for the nectarine (95%), "banana" for the
  chips (100%). Scoring by count rejects "fruit", which finds every fruit in the box.
  [`inspec/concepts.py`](../inspec/concepts.py). On Screw Bag every concept is always found, so this
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
  them ([notes](sam-output-format.md)).

Where it stops:

- **Damaged fruit was 1/31 with one shared damage question**, because chipped almonds got it
  switched off; per-item questions fixed that (23/31). Showing the model a known-good kit for
  reference was tried first and made things worse (it started comparing the two photos: 42 of 60
  good Screw Bags flagged for a "foreign object"), so the damage check uses no reference images.
- **Overflow (0/4)** isn't visible as area from above.
- **Known gap.** For a presence-only item any phrase that finds something fits, so "banana" beat
  "fruit" for the chips only by list order.

#### Breakfast Box on Muse Spark Open (Baseten)

The same code with compile, concept repair and calibration on Muse Spark Open
(`--provider baseten`, `runs/bb-baseten1`), then one test run of its program (`runs/bb-baseten1-test`).
Part checks only: the damage check wasn't run on Baseten. It converged in 2 rounds (60/60 good kits)
and reached the same granola area range and the same "apple" for the nectarine.

| | Muse Spark 1.3 (Meta API, `bb4-final`) | Muse Spark Open (Baseten) |
|---|---|---|
| False alarms, `validation/good` (62) | 0 | 1 |
| False alarms, `test/good` (102) | 0 | 3 |
| Caught, `test/logical_anomalies` (83) | **78** | 71 (p = 0.09) |
| … held-out (odd) half (41) | 38 | 34 |
| … missing bananas (11) | **11** | 1 |
| … overflow (4) | 0 | 3 |
| Caught, `test/structural_anomalies` (90) | 11 | 14 |

The gap is one choice. For the banana chips, "dried fruit" and "banana slice" both fit 100% of
calibration kits, and the open model listed "dried fruit" first. It also matches the other dried
items, so a box with no banana chips still passes the presence check. That's the
[known tie-break gap](#second-category-breakfast-box) with a measured cost: concept repair should
prefer the phrase that finds the fewest objects among those that fit. I haven't made that change,
since it would be chosen after seeing this test result. The 3 overflow kits it catches aren't
explained yet; I haven't investigated them.

#### Breakfast Box vision-only baseline

The same baseline as on Screw Bag (`scripts/baseline.py`), run once per variant after the freeze:
`runs/bb-baseline0` (zero-shot) and `runs/bb-baseline3` (3 good `train` kits shown first). There's
no hint variant: the Screw Bag hint was a measured size ratio, and the analogue here (how much
granola a good box holds) wasn't tried.

| | 0 ref | 3 ref | Inspec part checks | Inspec + shared damage question | Inspec + per-item damage (final) |
|---|---|---|---|---|---|
| False alarms, `validation/good` (62) | 3 | 3 | 0 | 4 | 5 |
| False alarms, `test/good` (102) | 2 | 6 | 0 | 4 | 4 |
| Caught, `test/logical_anomalies` (83) | 67 | 68 | **78** | **78** | **78** |
| … wrong ratio / underflow / swapped (19) | 7 | 8 | 18 | 18 | 18 |
| Caught, `test/structural_anomalies` (90) | 54 | **70** | 11 | 45 | 68 |
| … fruit damaged (31) | 22 | **25** | 0 | 1 | 23 |
| … toppings crushed (7) | 0 | 7 | 7 | 7 | 7 |

Paired exact tests, final Inspec vs 3 ref (the shared-question version in brackets):

| | Inspec | Baseline | Only Inspec | Only baseline | p |
|---|---|---|---|---|---|
| Logical (83) | 78 | 68 | 10 | 0 | 0.002 |
| Structural (90) | 68 (45) | 70 | 3 | 5 | 0.73 (< 0.00001) |
| Good test kits rejected (102) | 4 | 6 | 3 | 5 | 0.73 |

- **Counting is a tie again**, as on Screw Bag: both get every wrong-fruit-count and
  missing-item kit.
- **Amounts are Inspec's.** The model alone catches 8 of 19 wrong-ratio, underflow and swapped
  kits; the calibrated granola area catches 18.
- **Damage is now a tie** (68 vs 70, p = 0.73). With one shared damage question it was a clear
  loss (45 vs 70): calibration had switched it off because of chipped almonds. Per-item questions
  kept the fruit questions on, at the cost of one more false alarm on validation (5 vs 4 of 62)
  and none on test (4 of 102).

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

Metrics, image-level, per split ([`inspec/evaluate.py`](../inspec/evaluate.py)):
- **Recall** on anomalies (bad kits caught), overall and per defect type. Defect types are read
  from LOCO's ground-truth masks.
- **False-alarm rate** on good kits (good kits rejected)
- **Calibration before vs after:** the raw compiled program vs the repaired one, on the same images
- Planned: **AUROC**, using the number of failed checks (or the margin) as the anomaly score

Baseline: **Muse Spark vision-only**. Same packing list and image, asked for per-part counts and
damage, with no SAM and no checks. It runs on the same images with the same metrics
([results](#vision-only-baseline)).

## Limits

- Two LOCO categories. On Breakfast Box, overflow (0/4), mixed cereals (2/8) and box damage
  (1/4) are still mostly missed, and 8 of 31 damaged-fruit kits.
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
  damage check, which adds false alarms (2 → 7 of 122 good Screw Bag test kits).
- Parts SAM can't name reliably with a short noun phrase will be hard to check.

## Error analysis and PASS / REVIEW / FAIL

Every error in the final runs (`sb-final2`, `bb5-final`; validation and test good kits, all test
anomalies), re-run from cached answers and sorted by cause:

| Cause | False rejects (19) | Misses (38) |
|---|---|---|
| Muse Spark damage check: wrong "yes" (a "cracked" washer, a "broken" banana chip, a "foreign" nut) or wrong "no" | **15** | **33** |
| SAM merged two touching parts (one 713 px "screw") | 2 | 0 |
| Range: test screws 1.5–1.7% longer than any calibration screw | 2 | 0 |
| Range: one underflow box within the granola range | 0 | 1 |
| Not visible from above (overflow) | 0 | 4 |

So the model's damage judgement is the biggest source of error in both directions, and measured
ranges cause 3 errors in total. Percentile-based ranges wouldn't fix the two tight ones (those
screws are longer than every calibration screw, so percentiles would only tighten the range).
Switching off the noisy damage questions would trade catches for false rejects: `washers_damaged`
fires on 3 of 120 good calibration and validation kits but is the only flag on 3 dev-half defects.

Instead the verdict has three levels ([`inspec/triage.py`](../inspec/triage.py)):

- **FAIL**: a count is wrong, or a measurement is more than 3% outside its range.
- **REVIEW**: the only reasons are a Muse Spark damage answer or a measurement within 3% of a
  limit. A person looks.
- **PASS**: nothing flagged.

The 3% margin was chosen on `validation/good` only: the one good validation kit that failed a
measure check without a SAM merge was 1.75% over its limit, and the measured defects in the dev
half are 12% or more outside theirs. Frozen at `429343c`, then scored once on test
(`scripts/triage_eval.py --test`, `runs/*-triage/triage.json`):

| | Screw Bag | Breakfast Box |
|---|---|---|
| Good test kits: FAIL (hard reject) | **1** / 122 (was 7) | **0** / 102 (was 4) |
| Good test kits: REVIEW | 6 / 122 | 4 / 102 |
| Logical defects: FAIL / REVIEW / PASS | 137 / 0 / 0 | 78 / 0 / 5 |
| Structural defects: FAIL / REVIEW / PASS | 34 / 37 / 11 | 11 / 57 / 22 |
| Validation good kits: FAIL / REVIEW | 1 / 2 (of 60) | 0 / 5 (of 62) |

Nothing that was caught before is lost (FAIL + REVIEW equals the old reject count), and no logical
defect is softened to REVIEW. The one remaining hard reject of a good kit is a SAM merge: two
touching screws read as one long one, so the counts really are wrong in the masks. The price is
review work: most damage defects arrive as REVIEW, alongside 6 (Screw Bag) and 4 (Breakfast Box)
good kits per hundred-odd.

## Reproduce the results

Setup is in the [README quick start](../README.md#quick-start). Then:

```bash
scripts/download_loco.sh screw_bag breakfast_box

# Screw Bag: compile -> concept check -> calibrate on 60 good kits -> evaluate (writes runs/<name>/)
.venv/bin/python scripts/e2e.py --calib 60 --test --name mine
# re-evaluate a saved program with the damage check, without recompiling
.venv/bin/python scripts/e2e.py --program runs/mine/final.json --calib 60 --damage --test --name mine-dmg
# Breakfast Box
.venv/bin/python scripts/e2e.py --data data/breakfast_box --kit-name "breakfast box" \
  --packing-list "2 tangerines, 1 nectarine, granola, banana chips, almonds" --calib 60 --test --name bb
# vision-only baseline (3 reference kits; add --hint "..." for the size guide)
.venv/bin/python scripts/baseline.py --references 3 --name base3
# compile and calibrate on Muse Spark Open via Baseten
.venv/bin/python scripts/e2e.py --provider baseten --calib 60 --name baseten
```

The first full run makes about 1,400 SAM calls, a few minutes with 8 threads. Every SAM result and
Muse Spark damage/baseline answer is cached under `.cache/`, so re-evaluations are fast. Compile and
repair calls are not cached, and their output differs from run to run; each run's programs are
saved in `runs/<name>/`.
