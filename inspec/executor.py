"""Run a CheckProgram on one image's SAM segments.

Pure functions, except ``fetch_segments`` which calls SAM once per concept.
Only numpy and the stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Union

import numpy as np

from inspec.schema import CheckProgram
from inspec.segments import Segment, parse_sam_output

if TYPE_CHECKING:
    from inspec.sam_client import SamClient


@dataclass(frozen=True)
class SegmentRef:
    concept: str  # lowercased
    index: int  # position in segments_by_concept[concept]

    def __str__(self) -> str:
        return f"{self.concept}#{self.index}"


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    value: float | list[float]  # count -> number of instances; measure -> metric per instance
    expected: tuple[float | None, float | None]  # (min, max)
    evidence: list[SegmentRef]  # instances of the part the check looked at
    message: str  # e.g. "nut_count: found 3, expected 2..2"


@dataclass
class ProgramResult:
    passed: bool  # all checks passed
    checks: list[CheckResult] = field(default_factory=list)
    dropped: list[tuple[SegmentRef, SegmentRef, float]] = field(default_factory=list)
    unassigned: list[SegmentRef] = field(default_factory=list)
    metrics: dict[SegmentRef, dict[str, float]] = field(default_factory=dict)

    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        """JSON-safe dict (refs as "concept#index"), no numpy arrays."""
        return {
            "passed": bool(self.passed),
            "checks": [
                {
                    "check_id": c.check_id,
                    "passed": bool(c.passed),
                    "value": (
                        [float(v) for v in c.value]
                        if isinstance(c.value, list)
                        else c.value
                    ),
                    "expected": [
                        None if c.expected[0] is None else float(c.expected[0]),
                        None if c.expected[1] is None else float(c.expected[1]),
                    ],
                    "evidence": [str(r) for r in c.evidence],
                    "message": c.message,
                }
                for c in self.checks
            ],
            "dropped": [
                {"dropped": str(d), "kept": str(k), "iou": float(iou)}
                for d, k, iou in self.dropped
            ],
            "unassigned": [str(r) for r in self.unassigned],
            "metrics": {
                str(r): {"area": float(m["area"]), "length": float(m["length"])}
                for r, m in self.metrics.items()
            },
        }


def mask_length(segment: Segment) -> float:
    """Extent of the mask along its principal axis, in pixels.

    The (x, y) coordinates of True pixels are projected onto the eigenvector
    of the coordinate covariance with the largest eigenvalue; the length is
    ``max - min + 1``. Empty masks give 0, single-pixel masks give 1.
    """
    mask = np.asarray(segment.mask, dtype=bool)
    ys, xs = np.nonzero(mask)
    n = int(xs.size)
    if n == 0:
        return 0.0
    if n == 1:
        return 1.0
    coords = np.column_stack((xs.astype(np.float64), ys.astype(np.float64)))
    centered = coords - coords.mean(axis=0)
    cov = (centered.T @ centered) / n
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
    except np.linalg.LinAlgError:
        return float(max(int(xs.max()) - int(xs.min()), int(ys.max()) - int(ys.min())) + 1)
    order = int(np.argmax(eigenvalues))
    axis = eigenvectors[:, order]
    norm = float(np.linalg.norm(axis))
    if norm == 0.0 or not np.isfinite(norm):
        return float(max(int(xs.max()) - int(xs.min()), int(ys.max()) - int(ys.min())) + 1)
    axis = axis / norm
    proj = centered @ axis
    return float(proj.max() - proj.min() + 1.0)


def mask_iou(a: Segment, b: Segment) -> float:
    """IoU of two segments' full-image masks, via their box intersection."""
    ax1, ay1, ax2, ay2 = a.box
    bx1, by1, bx2, by2 = b.box
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    x2, y2 = min(ax2, bx2), min(ay2, by2)
    if x1 > x2 or y1 > y2:
        return 0.0
    ma = np.asarray(a.mask, dtype=bool)[y1 - ay1 : y2 - ay1 + 1, x1 - ax1 : x2 - ax1 + 1]
    mb = np.asarray(b.mask, dtype=bool)[y1 - by1 : y2 - by1 + 1, x1 - bx1 : x2 - bx1 + 1]
    inter = int(np.logical_and(ma, mb).sum())
    union = int(a.mask.sum()) + int(b.mask.sum()) - inter
    if union == 0:
        return 0.0
    return inter / union


def _format_bound(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _check_count(n: int, lo: float | None, hi: float | None) -> bool:
    if lo is not None and n < lo:
        return False
    if hi is not None and n > hi:
        return False
    return True


def run_program(
    program: CheckProgram,
    segments_by_concept: dict[str, list[Segment]],
) -> ProgramResult:
    """Run ``program`` on one image's segments and return per-check verdicts."""
    for concept in program.concepts():
        if concept not in segments_by_concept:
            raise ValueError(f"segments_by_concept is missing concept {concept!r}")

    refs: dict[str, list[SegmentRef]] = {
        concept: [SegmentRef(concept=concept, index=i) for i in range(len(segs))]
        for concept, segs in segments_by_concept.items()
    }
    seg_of: dict[SegmentRef, Segment] = {}
    for concept, segs in segments_by_concept.items():
        for i, seg in enumerate(segs):
            seg_of[refs[concept][i]] = seg

    # Dedupe first, rule by rule. Dropped segments leave the pool entirely.
    dropped_set: set[SegmentRef] = set()
    dropped: list[tuple[SegmentRef, SegmentRef, float]] = []
    for rule in program.dedupe:
        keep_c = rule.keep.lower()
        drop_c = rule.drop.lower()
        keep_refs = [r for r in refs.get(keep_c, []) if r not in dropped_set]
        drop_refs = [r for r in refs.get(drop_c, []) if r not in dropped_set]
        for drop_ref in drop_refs:
            best_ref: SegmentRef | None = None
            best_iou = 0.0
            for keep_ref in keep_refs:
                iou = mask_iou(seg_of[drop_ref], seg_of[keep_ref])
                if best_ref is None or iou > best_iou:
                    best_ref = keep_ref
                    best_iou = iou
            if best_ref is not None and best_iou >= rule.min_iou:
                dropped_set.add(drop_ref)
                dropped.append((drop_ref, best_ref, float(best_iou)))

    kept = [r for r in seg_of if r not in dropped_set]

    # Metrics for every kept segment.
    metrics: dict[SegmentRef, dict[str, float]] = {}
    for ref in kept:
        seg = seg_of[ref]
        metrics[ref] = {"area": float(seg.area), "length": float(mask_length(seg))}

    # Assign kept segments to parts.
    part_instances: dict[str, list[SegmentRef]] = {p.id: [] for p in program.parts}
    claimed: set[SegmentRef] = set()
    for ref in kept:
        concept = ref.concept
        m = metrics[ref]
        for part in program.parts:
            if part.concept.lower() != concept:
                continue
            if part.min_length is not None and m["length"] < part.min_length:
                continue
            if part.max_length is not None and m["length"] > part.max_length:
                continue
            if part.min_area is not None and m["area"] < part.min_area:
                continue
            if part.max_area is not None and m["area"] > part.max_area:
                continue
            part_instances[part.id].append(ref)
            claimed.add(ref)
    unassigned = [r for r in kept if r not in claimed]

    # Checks.
    results: list[CheckResult] = []
    for check in program.checks:
        instances = list(part_instances.get(check.part, []))
        lo, hi = check.min, check.max
        expected = (lo, hi)
        span = f"{_format_bound(lo)}..{_format_bound(hi)}"
        if check.type == "count":
            n = len(instances)
            ok = _check_count(n, lo, hi)
            results.append(
                CheckResult(
                    check_id=check.id,
                    passed=ok,
                    value=n,
                    expected=expected,
                    evidence=instances,
                    message=f"{check.id}: found {n}, expected {span}",
                )
            )
        else:
            metric = check.metric or "length"
            values = [float(metrics[r][metric]) for r in instances]
            ok = all(
                (lo is None or v >= lo) and (hi is None or v <= hi) for v in values
            )
            shown = ", ".join(f"{v:.1f}" for v in values)
            results.append(
                CheckResult(
                    check_id=check.id,
                    passed=ok,
                    value=values,
                    expected=expected,
                    evidence=instances,
                    message=f"{check.id}: found [{shown}] {metric}, expected {span}",
                )
            )

    return ProgramResult(
        passed=all(c.passed for c in results),
        checks=results,
        dropped=dropped,
        unassigned=unassigned,
        metrics=metrics,
    )


def fetch_segments(
    program: CheckProgram,
    image_path: Union[str, Path],
    client: SamClient,
) -> dict[str, list[Segment]]:
    """Fetch SAM segments for each distinct concept in ``program``."""
    out: dict[str, list[Segment]] = {}
    for concept in program.concepts():
        out[concept] = parse_sam_output(client.segment_text(image_path, concept))
    return out
