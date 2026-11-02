# Build log

What was built when, during the hackathon (Oct 26 – Nov 4, 2026), and how the work was split between me, Claude Code and Muse Code. Back to the [README](../README.md).

## Status

| Part | State |
|---|---|
| Repo setup, secrets handling, dataset license handling | Done |
| SAM 3.1 API probed; output format verified ([notes](sam-output-format.md)) | Done |
| Dataset download script (`scripts/download_loco.sh`) | Done (tested) |
| SAM client with disk cache (`inspec/sam_client.py`) | Done (tested) |
| SAM output parser (`inspec/segments.py`) | Done (tested) |
| Check-program schema (`inspec/schema.py`) | Done (tested) |
| LLM client: Meta default, optional Baseten (`inspec/llm.py`) | Done (tested); Baseten verified live |
| Packing-list compiler (`inspec/compiler.py`) | Done (tested) |
| Check executor: merging, carve-out, metrics (`inspec/executor.py`) | Done (tested) |
| Calibration loop (`inspec/calibrate.py`) | Done (tested), 3 live runs |
| Evaluation on Screw Bag (`inspec/evaluate.py`, `scripts/e2e.py`) | Done; [results](benchmarks.md#results) |
| Damage check, Muse Spark vision (`inspec/damage.py`) | Done (tested), kit-neutral prompt; [results](benchmarks.md#damage-check-muse-spark-vision) |
| Concept repair before calibration (`inspec/concepts.py`) | Done (tested); used on [Breakfast Box](benchmarks.md#second-category-breakfast-box) |
| Vision-only baseline (`inspec/baseline.py`, `scripts/baseline.py`) | Done (tested); [results](benchmarks.md#vision-only-baseline) |
| Streamlit app (`app.py`; plain-English checks in `inspec/explain.py`, overlay in `inspec/overlay.py`) | Done; one page in story order, runs on saved runs and cached results, live recompile optional |

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

## How this was built

Solo project. I designed the system and own every decision in it. AI coding tools are used and
disclosed so the contribution is clear:

- **Claude Code**: architecture, the check schema and compiler prompt, the calibration and eval
  design, and review of all code.
- **Muse Code** (Meta's coding agent): well-specified implementation tasks. Each has a written brief
  in [`.orchestrator/tasks/`](../.orchestrator/tasks/) and a line in
  [`.orchestrator/log.md`](../.orchestrator/log.md). Each task lands as its own branch merge, and every
  diff was reviewed and tested before merge.

Agent instructions are in [`CLAUDE.md`](../CLAUDE.md) and [`AGENTS.md`](../AGENTS.md).

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
  [above](how-it-works.md#why-this-is-hard-and-a-real-example)). Replaced dedupe rules with automatic object
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
  three times ([results](benchmarks.md#results)). Baseten first returned 401, which turned out to be my own bug: an
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
  [How the test set was used](benchmarks.md#how-the-test-set-was-used)). Measured the "wrong-length" defects on
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
- **Oct 31.** Ran the vision-only baseline on Breakfast Box: Inspec won logical defects (78 vs 68)
  and lost structural ones badly (45 vs 70), almost all bruised fruit (1/31 vs 25/31). The cause
  was calibration, not the model: one shared "item broken" question fired on chipped almonds and
  was switched off for everything. Made the damage check ask one question per packing-list item,
  checked it on training, validation and the even half, froze at `6aa7546` and evaluated once:
  Breakfast Box structural 68/90 (33/45 held-out), damaged fruit 23/31, 4/102 false alarms;
  Screw Bag structural 71/82 (38/41 held-out), 7/122 false alarms. The UI now loads the right
  kit for each run, and there's a [video script](video-script.md). Ran Breakfast Box on Muse
  Spark Open via Baseten: 71/83 logical vs 78, the gap almost all from its picking "dried fruit"
  for the banana chips (missing bananas 1/11).
