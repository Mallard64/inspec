"""Three-way verdict: PASS, REVIEW or FAIL.

A measured failure far outside its range is evidence, so the kit FAILs. Two kinds of flag are
weaker and go to a person instead (REVIEW):

- a measurement just outside its range (within ``MARGIN`` of the limit), where mask noise or a
  part slightly beyond the calibration kits is as likely as a defect;
- a Muse Spark damage answer with no failed measurement behind it: a judgement, not a measurement.

``MARGIN`` was chosen on validation/good kits only (see docs/benchmarks.md): the one good
validation kit that failed a measure check without a SAM merge was 1.75% over its limit, while
the measured defects are 12% or more outside theirs.
"""

from __future__ import annotations

from inspec.executor import CheckResult

MARGIN = 0.03  # relative distance outside a measure range that still counts as borderline


def overshoot(result: CheckResult) -> float:
    """How far the worst value of a failed measure check lies outside its range, relative to the
    limit it crossed (0.02 = 2% beyond). Count checks and passed checks return 0."""
    if result.passed or not isinstance(result.value, list):
        return 0.0
    lo, hi = result.expected
    worst = 0.0
    for v in result.value:
        if lo is not None and v < lo:
            worst = max(worst, (lo - v) / lo if lo else float("inf"))
        if hi is not None and v > hi:
            worst = max(worst, (v - hi) / hi if hi else float("inf"))
    return worst


def triage(checks: list[CheckResult], damage_flags: list[str], *,
           margin: float = MARGIN) -> tuple[str, list[str]]:
    """("PASS" | "REVIEW" | "FAIL", reasons). Reasons are check messages and damage questions."""
    failed = [c for c in checks if not c.passed]
    hard = [c for c in failed if not isinstance(c.value, list) or overshoot(c) > margin]
    if hard:
        return "FAIL", [c.message for c in hard]
    if failed or damage_flags:
        return "REVIEW", [c.message for c in failed] + list(damage_flags)
    return "PASS", []
