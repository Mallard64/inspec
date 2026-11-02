"""Plain-English descriptions of check programs and results, for the UI.

The check program is JSON; a person watching the demo should read "Exactly 2 × nut" and "Every
long screw is 396–441 px long", not field names.
"""

from __future__ import annotations

from inspec.schema import Check, CheckProgram, Part


def label(part_id: str) -> str:
    return part_id.replace("_", " ")


def _num(x: float, metric: str | None = None) -> str:
    return f"{x:.0%}" if metric == "hole" else f"{x:,.0f}"


def _range(lo: float | None, hi: float | None, metric: str | None = None) -> str:
    if lo is not None and hi is not None:
        return f"{_num(lo, metric)}–{_num(hi, metric)}"
    if lo is not None:
        return f"at least {_num(lo, metric)}"
    return f"at most {_num(hi, metric)}"


def describe_check(check: Check) -> str:
    name = label(check.part)
    if check.type == "count":
        if check.min == check.max:
            return f"Exactly {int(check.min)} × {name}"
        if check.max is None:
            return f"{name.capitalize()} is present" if check.min == 1 else \
                f"At least {int(check.min)} × {name}"
        return f"{_range(check.min, check.max)} × {name}"
    if check.metric == "hole":
        return f"Every {name} has a hole of {_range(check.min, check.max, 'hole')} of its outline"
    if check.metric == "area":
        return f"{name.capitalize()} covers {_range(check.min, check.max)} px² (the amount)"
    return f"Every {name} is {_range(check.min, check.max)} px long"


def describe_limits(part: Part) -> str | None:
    """How an object is told apart as this part, or None when SAM's label alone decides."""
    bits = []
    for metric, unit in (("length", " px"), ("area", " px²"), ("hole", " of its outline")):
        lo, hi = getattr(part, f"min_{metric}"), getattr(part, f"max_{metric}")
        if lo is not None or hi is not None:
            bits.append(f"{metric} {_range(lo, hi, metric)}{unit}")
    return ", ".join(bits) if bits else None


def learned(compiled: CheckProgram, final: CheckProgram,
            concept_repairs: list[dict] | None = None) -> list[str]:
    """What concept repair and calibration changed, one sentence each."""
    out = [f"SAM didn't know \"{r['original']}\", so it looks for \"{r['chosen']}\" instead"
           for r in concept_repairs or [] if r["original"] != r["chosen"]]
    before = {p.id: p for p in compiled.parts}
    for part in final.parts:
        limits = describe_limits(part)
        old = before.get(part.id)
        if limits and (old is None or describe_limits(old) != limits):
            out.append(f"A {label(part.id)} is told apart by {limits}")
    known = {c.id for c in compiled.checks}
    out += [f"New check: {describe_check(c)}" for c in final.checks if c.id not in known]
    return out


def describe_result(check: Check | None, value, fallback: str) -> str:
    """One line for a check result: the rule, then what was found."""
    if check is None:
        return fallback
    if check.type == "count":
        return f"{describe_check(check)}: found {int(value)}"
    found = value if isinstance(value, (list, tuple)) else [value]
    shown = ", ".join(_num(v, check.metric) for v in found[:4]) or "none found"
    return f"{describe_check(check)}: measured {shown}"


_KIT_QUESTIONS = {
    "container_damaged": ("Container: no damage", "Container: damaged"),
    "item_discoloured": ("No unusual colours or stains", "Unusual colour or stain"),
    "foreign_object": ("Nothing that isn't on the list", "Something that isn't on the list"),
}


def describe_question(question: str, flagged: bool) -> str:
    """A damage-check answer as a finding: "Tangerines: no damage" / "Tangerines: damaged"."""
    if question in _KIT_QUESTIONS:
        return _KIT_QUESTIONS[question][flagged]
    item = label(question.removesuffix("_damaged")).capitalize()
    return f"{item}: {'damaged' if flagged else 'no damage'}"
