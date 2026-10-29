"""Calibration: run a program on known-good kits, have Muse Spark repair what fails, re-run.

The compiler can't see pixel sizes, so its first program has no limits and rejects good kits (on
Screw Bag every screw counts as both long and short). Each round we run the program on good images
and, if any fail, send Muse Spark the failed checks plus every object's measurements. It returns a
repaired program, which must keep the packing list's count checks exactly: the only way to make a
good kit pass is to describe the parts better, never to accept a different quantity.

Every round is kept (program, failures, rejected repair attempts) so the loop can be shown.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from inspec.executor import ProgramResult, fetch_segments, run_program
from inspec.llm import LLM, Generation
from inspec.schema import CheckProgram
from inspec.segments import Segment

if TYPE_CHECKING:
    from inspec.sam_client import SamClient

REPAIR_INSTRUCTIONS = """\
You repair a check program for an automated kit inspection station. Every kit you are shown is
known to be GOOD (complete and correct), yet the program rejected some of them. Fix the program so
every good kit passes, while it would still catch kits with missing, extra or wrong-size parts.

How the program runs on one image:
- SAM segments each part's `concept`. Overlapping segments are merged into one object that carries
  every concept label SAM gave it (SAM often gives one object several labels, e.g. a nut is also
  labelled "washer", and a screw head is labelled "nut" inside the screw).
- Each object is measured: `length` (px along its main axis), `area` (px), `hole` (fraction of the
  filled outline that is hole: 0 for a solid part, ~0.4 for a flat washer).
- Parts are tried IN ORDER. An object goes to the first part whose concept is among the object's
  labels and whose limits (min_/max_ length, area, hole) it meets. Objects matching no part are
  ignored. A part with no limits, placed after the others, catches every remaining object with its
  label.
- `count` checks bound how many objects a part gets; `measure` checks bound a metric of each of a
  part's objects.

Rules for your repair:
- Keep every part id and concept. Keep every count check exactly as it is (same id, part, min,
  max). The quantities come from the packing list and are correct.
- Fix failures by setting part limits and part order, using the measurements. Group the objects
  of all images by labels and size, find the gaps between groups, and put each split threshold in
  the middle of the widest gap, not right at the edge of the good values. Use the metric that
  separates the groups with the biggest margin; `hole` often separates parts that `area` can't.
- Add a `measure` check on `length` for each part whose size defines it (e.g. two lengths of
  screw): set min and max about 4% outside the range seen on good kits, so a part that is clearly
  too long or too short is caught. Do not add measure checks on `hole`, or on parts whose size the
  packing list doesn't specify: those vary with how a part lies and would reject good kits.
- Leave `merge_overlap` as it is. Parts that touch are already handled by the merging step.
- Segmentation sometimes fails on a single kit (e.g. two crossing screws returned as one object
  with about twice the normal area, or a part measured far longer than the rest of its group).
  Base every threshold and range on the bulk of each group; a lone value far outside it is a
  measurement failure, not a reason to move a threshold or widen a range. Leave such kits failing
  and name them in `notes`. A few failing kits out of many is the expected result.
- Change only what the evidence calls for. Say what you changed and why in `notes`.
Return the complete repaired program.
"""


@dataclass
class Round:
    number: int
    program: CheckProgram  # the program this round evaluated
    passed: int
    total: int
    failures: dict[str, list[str]]  # image name -> failed check messages
    repair: Generation[CheckProgram] | None = None  # the repair that produced the next program

    def to_dict(self) -> dict:
        out = {"round": self.number, "passed": self.passed, "total": self.total,
               "failures": self.failures, "program": self.program.model_dump(mode="json")}
        if self.repair is not None:
            out["repair"] = {"attempts": self.repair.attempts, "rejected": self.repair.errors,
                             "notes": self.repair.value.notes}
        return out


@dataclass
class Calibration:
    program: CheckProgram  # best program found (most calibration images passing)
    converged: bool  # that program passes every calibration image
    rounds: list[Round] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"converged": self.converged, "rounds": [r.to_dict() for r in self.rounds],
                "program": self.program.model_dump(mode="json")}


def fetch_many(program: CheckProgram, images: list[str | Path], client: SamClient, *,
               workers: int = 8) -> dict[str, dict[str, list[Segment]]]:
    """Segments for every image (keyed by path string), fetched in parallel. SAM results are
    cached on disk, so this is cheap after the first run."""
    with ThreadPoolExecutor(workers) as pool:
        segs = pool.map(lambda p: fetch_segments(program, p, client), images)
        return {str(p): s for p, s in zip(images, segs)}


def run_many(program: CheckProgram,
             segments: dict[str, dict[str, list[Segment]]]) -> dict[str, ProgramResult]:
    return {path: run_program(program, segs) for path, segs in segments.items()}


def evidence_table(results: dict[str, ProgramResult]) -> str:
    """What the model reads: sorted measurements of every object grouped by the part it went to
    (exact ranges and gaps, computed here rather than eyeballed), then per failing image its
    failed checks and one line per object."""
    groups: dict[str, list[dict[str, float]]] = {}
    for result in results.values():
        owner = {ref: check.part_id for check in result.checks for ref in check.evidence}
        for ref, m in result.metrics.items():
            label = "+".join(sorted(result.labels[ref]))
            key = f"part {owner[ref]}" if ref in owner else f"unassigned, labels {label}"
            groups.setdefault(key, []).append(m)
    passed = sum(r.passed for r in results.values())
    lines = [f"{passed}/{len(results)} good kits pass.", "",
             "# Measurements of all objects in all kits, by the part each went to (sorted)"]
    for key, ms in sorted(groups.items()):
        lines.append(f"## {key}: {len(ms)} objects")
        for metric, fmt in (("length", "{:.0f}"), ("area", "{:.0f}"), ("hole", "{:.2f}")):
            lines.append(f"  {metric}: " + " ".join(fmt.format(v) for v in
                                                    sorted(m[metric] for m in ms)))
    lines += ["", "# Failing kits"]
    for path, result in results.items():
        if result.passed:
            continue
        name = Path(path).name
        lines.append(f"## {name}")
        lines += [f"  failed {c.message}" for c in result.failed()]
        owner = {ref: check.part_id for check in result.checks for ref in check.evidence}
        for ref, m in sorted(result.metrics.items(), key=lambda kv: -kv[1]["length"]):
            labels = "+".join(sorted(result.labels[ref]))
            lines.append(f"  {str(ref):10} labels={labels:18} length={m['length']:6.1f} "
                         f"area={m['area']:7.0f} hole={m['hole']:.3f} "
                         f"part={owner.get(ref, '-')}")
    return "\n".join(lines)


def keeps_counts(original: CheckProgram) -> Callable[[CheckProgram], None]:
    """Validator for repairs: same parts (id, concept) and identical count checks."""
    counts = {c.id: (c.part, c.min, c.max) for c in original.checks if c.type == "count"}
    parts = {p.id: p.concept.lower() for p in original.parts}

    def validate(repaired: CheckProgram) -> None:
        got_parts = {p.id: p.concept.lower() for p in repaired.parts}
        if got_parts != parts:
            raise ValueError(f"parts must stay {parts} (id: concept); got {got_parts}")
        got = {c.id: (c.part, c.min, c.max) for c in repaired.checks if c.type == "count"}
        if got != counts:
            raise ValueError(f"count checks must stay exactly {counts} (id: part, min, max); "
                             f"got {got}")

    return validate


def _same_rules(a: CheckProgram, b: CheckProgram) -> bool:
    return a.model_dump(exclude={"notes"}) == b.model_dump(exclude={"notes"})


def calibrate(program: CheckProgram, good_images: list[str | Path], *, sam: SamClient,
              llm: LLM | None = None, max_rounds: int = 4, workers: int = 8,
              log: Callable[[str], None] = print) -> Calibration:
    """Repair ``program`` until it passes every image in ``good_images`` or ``max_rounds`` runs
    are used up. Round 1 evaluates the input program; each later round evaluates a repair."""
    if not good_images:
        raise ValueError("calibration needs at least one good image")
    llm = llm or LLM()
    segments = fetch_many(program, good_images, sam, workers=workers)
    validate = keeps_counts(program)
    rounds: list[Round] = []
    current = program
    best: tuple[Round, dict[str, ProgramResult]] | None = None
    worse: list[str] = []  # repairs of the best program that scored lower, told to the model
    for number in range(1, max_rounds + 1):
        results = run_many(current, segments)
        failures = {Path(p).name: [c.message for c in r.failed()]
                    for p, r in results.items() if not r.passed}
        round_ = Round(number, current, len(results) - len(failures), len(results), failures)
        rounds.append(round_)
        log(f"round {number}: {round_.passed}/{round_.total} good kits pass")
        if best is None or round_.passed > best[0].passed:
            best, worse = (round_, results), []
        else:
            worse.append(f"A repair scored {round_.passed}/{round_.total} (best is "
                         f"{best[0].passed}/{best[0].total}), so it was discarded. Its notes: "
                         f"{current.notes}")
            log(f"  not better than round {best[0].number}; repairing that program instead")
        if best[0].passed == best[0].total or number == max_rounds:
            break
        base, base_results = best
        text = ("Current program:\n" + base.program.model_dump_json(indent=1)
                + "\n\nResults on good kits:\n" + evidence_table(base_results))
        if worse:
            text += "\n\nEarlier repairs of this program that made things worse:\n" + "\n".join(worse)
        round_.repair = llm.generate(REPAIR_INSTRUCTIONS, [{"type": "input_text", "text": text}],
                                     CheckProgram, validate=validate)
        if round_.repair.errors:
            log(f"  repair needed {round_.repair.attempts} attempts; rejected: "
                f"{round_.repair.errors}")
        log(f"  repair notes: {round_.repair.value.notes}")
        current = round_.repair.value
        if _same_rules(current, base.program):
            log("  repair changed nothing; stopping")
            break
    assert best is not None
    return Calibration(best[0].program, best[0].passed == best[0].total, rounds)
