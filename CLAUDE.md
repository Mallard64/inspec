# Inspec — orchestration rules for Claude Code

Inspec is a kit-completeness inspector for the Meta Global AI Developer Hackathon (indie track, solo).
A user types a packing list ("1 long screw, 1 short screw, 2 nuts, 2 washers"), Muse Spark compiles it
into a JSON check program, SAM 3.1 segments and counts the parts in each kit image, and a calibration
loop repairs checks that fail on known-good kits. Build window: Oct 26 – Nov 4, 2026. Submission due
Nov 4, 9:00 PM ET.

## Your role: orchestrator, not typist

You (Claude Code) own design, decomposition, review, and integration. Delegate well-specified,
standard implementation work to the Muse Code agent (`muse exec`). Do the work yourself only when it
falls in "Claude does" below, or when Muse has failed the same task twice.

### Claude does
- Architecture, module boundaries, and the check-program JSON schema
- The spec compiler prompt and structured-output schema (core IP; quality matters most here)
- The calibration loop logic and the eval methodology (metrics, baselines, splits)
- Writing task briefs for Muse, reviewing every Muse diff, merging, resolving conflicts
- Debugging failures that cross module boundaries or that Muse could not fix
- Final README claims and results tables (verify every number against eval output)

### Muse does (standard tasks)
- Boilerplate and glue: API clients, CLI entry points, config loading, caching
- Parsing SAM 3.1 segmentation output into boxes/masks (spec given in the brief)
- Check executor functions once the schema is fixed (count, present, area, relative position)
- Streamlit UI pages and mask overlay rendering
- Unit tests for a module whose interface is already defined
- Scripts: dataset download, batch runners, result export
- Mechanical refactors and docstrings

Rule of thumb: if the task can be fully specified in under a page with a clear "done when", delegate it.
If deciding *what* to build is the hard part, keep it.

## How to delegate to Muse

1. Write a brief to `.orchestrator/tasks/<NN>-<slug>.md` using the template below.
2. Run Muse headless in its own worktree so parallel tasks don't collide:

   ```bash
   muse exec --json \
     --no-foreign-personal-context \
     --trust-workspace \
     --approval-mode never \
     --max-model-steps 40 \
     --reasoning-effort medium \
     -w create \
     --prompt-file .orchestrator/tasks/<NN>-<slug>.md \
     > .orchestrator/logs/<NN>-<slug>.jsonl
   ```

   - `--no-foreign-personal-context` stops Muse from sending machine-wide instruction files
     (e.g. `~/.claude/CLAUDE.md`) to Meta.
   - `--trust-workspace` is required for Muse to load this repo's `AGENTS.md`; without it the rules
     file is skipped. It does not disable the sandbox or approvals.
   - `-w create` needs at least one commit on the base branch.
   - `--approval-mode never` keeps headless runs from stalling; Muse's sandbox still contains them.
     Never use `--yolo` on this machine.
   - `--max-model-steps` is the only cost cap. Use 20 for small tasks, 40 default, 80 max.
   - Muse's sandbox network defaults to proxy-only. If a task needs `pip install`, install
     dependencies yourself first and say so in the brief.
3. Read the final records of the JSONL log for the outcome, then review the diff in the worktree.
4. Run the tests named in the brief yourself. Merge only if they pass and the diff stays in scope.
5. If it fails: rewrite the brief with the specific failure and retry once. A second failure means
   you do the task yourself and note why in `.orchestrator/log.md`.

Run independent tasks in parallel (separate worktrees). Never run two Muse tasks that edit the same file.

### Task brief template

```markdown
# Task NN: <title>

## Goal
One sentence.

## Context
Relevant files (paths), interfaces to call or implement, and any schema (paste it, don't reference it).

## Requirements
- Concrete, testable bullets
- Files to create or modify; files NOT to touch

## Done when
- `pytest tests/test_<x>.py` passes
- <other observable check>

## Constraints
- Python 3.11, no new dependencies unless listed here
- Follow AGENTS.md
```

Keep a one-line entry per task in `.orchestrator/log.md`: task id, delegated or self-done, result, retries.

## Hackathon rules (hard constraints)

- **New work only.** Everything is built from Oct 26 onward. Don't paste code from earlier projects.
- **Public repo.** Never commit secrets. API keys live in `.env` (gitignored); read `META_API_KEY`
  from the environment.
- **No dataset in git.** MVTec LOCO AD is non-commercial; images live in `data/` (gitignored) and
  are fetched by `scripts/download_loco.sh`.
- **Avoid the "simple image analyzer" anti-project.** The product story is the agent that compiles a
  packing list into checks and repairs them. Keep that loop visible in the UI and logs.
- **Meta models in the product.** The shipped app uses Muse Spark (compiler, calibration, baseline)
  and SAM 3.1 (segmentation). Muse Code is a dev tool here, not a product feature.

## Project layout

```
inspec/
  sam_client.py      # SAM 3.1 calls via Meta Model API (Responses API), disk cache by (image, concept)
  segments.py        # parse SAM output into boxes/masks
  schema.py          # check-program JSON schema (pydantic)
  compiler.py        # packing list + good images -> check program (Muse Spark, structured output)
  executor.py        # run a check program on one image -> verdicts with evidence
  calibrate.py       # run on good images, repair failing checks, re-run
  baseline.py        # Muse Spark vision-only pass/fail baseline
eval/
  run_eval.py        # LOCO eval: recall, false-alarm rate, AUROC per category
app.py               # Streamlit single page
scripts/download_loco.sh
tests/
.orchestrator/       # task briefs, Muse logs, orchestration log
```

## Model API facts to keep in briefs

- Base URL `https://api.meta.ai/v1`, OpenAI-SDK compatible. Key in `META_API_KEY`.
- SAM 3.1: model `sam-3.1`, Responses API, one short noun phrase per request ("nut", not
  "segment the nuts" or "nut, washer"). Spatial words and negation are unreliable; do position
  and negative logic in `executor.py`, never in the SAM prompt. A concept with no matches returns
  empty output, which is a valid result, not an error.
- Cache every SAM result; reruns of rules must not re-call SAM.

## Priorities when time is short

1. Packing list → compiled checks → verdict with mask, on Screw Bag
2. Calibration loop with a measurable before/after
3. Eval numbers vs the vision-only baseline
4. UI polish and the 3-minute video
5. Stretch: Breakfast Box, Muse Spark Open compiler, voice input, conveyor video
