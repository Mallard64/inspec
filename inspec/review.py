"""Human decisions on REVIEW kits, and what they teach the damage check.

Decisions are an append-only JSONL log; the latest decision per image wins. Every decision lists
the flags the reviewer saw, so each damage question gets a tally: kits it flagged that a reviewer
passed (an override: the question was wrong) or rejected (it was right). A question reviewers
keep overriding is suggested for switching off, the same way calibration switches off questions
that fire on good kits. Switching off is a person's click, stored per kit in a small JSON file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DECISIONS = ("PASS", "FAIL")
MIN_DECISIONS = 3   # don't suggest anything from fewer reviewed kits than this
MIN_OVERRIDE = 0.8  # share of a question's flags that reviewers passed


def record(log_path: Path, image: str, decision: str, *, kit: str, flags: list[str],
           note: str = "", reviewer: str = "") -> dict:
    """Append one decision on `image` (with the flags the reviewer saw) and return the entry."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    entry = dict(image=image, kit=kit, decision=decision, flags=list(flags), note=note.strip(),
                 reviewer=reviewer.strip(), time=time.strftime("%Y-%m-%dT%H:%M:%S"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load(log_path: Path) -> dict[str, dict]:
    """Latest decision per image. A missing log means no decisions yet."""
    if not log_path.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in log_path.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            latest[entry["image"]] = entry
    return latest


def tally(decisions: dict[str, dict], kit: str, questions: list[str]) -> dict[str, dict]:
    """Per damage question: how many kits it flagged that reviewers passed / rejected."""
    stats = {q: {"passed": 0, "rejected": 0} for q in questions}
    for entry in decisions.values():
        if entry.get("kit") != kit:
            continue
        for q in entry["flags"]:
            if q in stats:
                stats[q]["passed" if entry["decision"] == "PASS" else "rejected"] += 1
    return stats


def suggest_off(stats: dict[str, dict], *, min_decisions: int = MIN_DECISIONS,
                min_override: float = MIN_OVERRIDE) -> list[str]:
    """Questions reviewers keep overriding: enough decisions, mostly passed."""
    out = []
    for q, s in stats.items():
        n = s["passed"] + s["rejected"]
        if n >= min_decisions and s["passed"] / n >= min_override:
            out.append(q)
    return out


def switched_off(path: Path, kit: str) -> set[str]:
    """Questions a reviewer switched off for this kit."""
    if not path.exists():
        return set()
    return set(json.loads(path.read_text()).get(kit, []))


def set_switched_off(path: Path, kit: str, question: str, off: bool) -> None:
    data = json.loads(path.read_text()) if path.exists() else {}
    current = set(data.get(kit, []))
    current = current | {question} if off else current - {question}
    data[kit] = sorted(current)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
