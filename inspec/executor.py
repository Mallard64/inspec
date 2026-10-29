"""Run a CheckProgram on one image's SAM segments.

Pure functions, except ``fetch_segments`` which calls SAM once per concept.
Only numpy and the stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    part_id: str = ""  # the part the check is about


@dataclass
class ProgramResult:
    passed: bool  # all checks passed
    checks: list[CheckResult] = field(default_factory=list)
    merged: list[tuple[SegmentRef, SegmentRef, float]] = field(default_factory=list)  # (absorbed, object, overlap)
    unassigned: list[SegmentRef] = field(default_factory=list)  # objects that match no part
    metrics: dict[SegmentRef, dict[str, float]] = field(default_factory=dict)  # per object
    labels: dict[SegmentRef, set[str]] = field(default_factory=dict)  # every concept SAM gave the object
    objects: dict[SegmentRef, Segment] = field(default_factory=dict)  # final mask per object
    split: list[tuple[SegmentRef, SegmentRef]] = field(default_factory=list)  # (part, carved from)

    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        """JSON-safe dict (refs as "concept#index"), no numpy arrays."""
        return {
            "passed": bool(self.passed),
            "checks": [
                {
                    "check_id": c.check_id,
                    "part_id": c.part_id,
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
            "merged": [
                {"absorbed": str(a), "object": str(o), "overlap": float(v)}
                for a, o, v in self.merged
            ],
            "labels": {str(r): sorted(ls) for r, ls in self.labels.items()},
            "split": [{"object": str(a), "carved_from": str(b)} for a, b in self.split],
            "unassigned": [str(r) for r in self.unassigned],
            "metrics": {str(r): {k: float(v) for k, v in m.items()} for r, m in self.metrics.items()},
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


def _holes(mask: np.ndarray) -> np.ndarray:
    """Background pixels not 4-connected to the border of the box (same shape as ``mask``)."""
    mask = np.pad(np.asarray(mask, dtype=bool), 1)
    outside = np.zeros_like(mask)
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    free = ~mask
    while True:  # flood fill the background from the border
        grown = outside.copy()
        grown[1:, :] |= outside[:-1, :]
        grown[:-1, :] |= outside[1:, :]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        grown &= free
        if np.array_equal(grown, outside):
            break
        outside = grown
    return (free & ~outside)[1:-1, 1:-1]


def hole_fraction(segment: Segment) -> float:
    """Fraction of the filled outline that is enclosed background: holes / (mask + holes)."""
    area = segment.area
    if area == 0:
        return 0.0
    holes = int(_holes(segment.mask).sum())
    return holes / (holes + area)


def mask_overlap(a: Segment, b: Segment) -> float:
    """Fraction of the smaller mask that lies inside the other (1.0 = fully contained)."""
    ax1, ay1, ax2, ay2 = a.box
    bx1, by1, bx2, by2 = b.box
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    x2, y2 = min(ax2, bx2), min(ay2, by2)
    if x1 > x2 or y1 > y2:
        return 0.0
    ma = np.asarray(a.mask, dtype=bool)[y1 - ay1 : y2 - ay1 + 1, x1 - ax1 : x2 - ax1 + 1]
    mb = np.asarray(b.mask, dtype=bool)[y1 - by1 : y2 - by1 + 1, x1 - bx1 : x2 - bx1 + 1]
    inter = int(np.logical_and(ma, mb).sum())
    smaller = min(int(a.mask.sum()), int(b.mask.sum()))
    if smaller == 0:
        return 0.0
    return inter / smaller


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


# A segment inside another that has a hole of its own and is under half the container's size is a
# separate part touching it (a washer lying against a screw), not a piece of it (a screw head is
# solid). Measured on 100 Screw Bag train images: heads 0.0, touching nuts/washers >= 0.24.
SPLIT_MIN_HOLE = 0.1
SPLIT_MAX_AREA_RATIO = 0.5
SPLIT_MIN_OVERLAP = 0.5  # independent of merge_overlap: a touching part is carved out regardless


def _subtract(container: Segment, part: Segment) -> Segment:
    """``container`` with ``part``'s filled outline (mask and its holes) removed (same box)."""
    full = replace(part, mask=part.mask | _holes(part.mask)).full_mask()
    x1, y1, x2, y2 = container.box
    rest = container.mask & ~full[y1 : y2 + 1, x1 : x2 + 1]
    # The two masks' edges don't line up exactly, leaving thin slivers of rim that wreck the
    # principal-axis length (one short screw went from 295 to 401 px). A 2 px opening drops them.
    opened = np.pad(rest, 2)
    for step in (_erode, _erode, _dilate, _dilate):
        opened = step(opened)
    return replace(container, mask=rest & opened[2:-2, 2:-2])


def _erode(m: np.ndarray) -> np.ndarray:
    e = m.copy()
    e[1:] &= m[:-1]
    e[:-1] &= m[1:]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return e


def _dilate(m: np.ndarray) -> np.ndarray:
    d = m.copy()
    d[1:] |= m[:-1]
    d[:-1] |= m[1:]
    d[:, 1:] |= m[:, :-1]
    d[:, :-1] |= m[:, 1:]
    return d


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

    # Merge duplicates into objects. SAM gives one physical object several labels (a hex nut is
    # also a "washer") and finds parts of objects (a screw head is a "nut"), so any segment mostly
    # inside a larger one joins it. Largest first, so small pieces fold into whole objects.
    # Exception: a holed segment inside a much larger one is a touching part; carve it out.
    order = sorted(seg_of, key=lambda r: (-seg_of[r].area, r.concept, r.index))
    objects: dict[SegmentRef, Segment] = {}  # current mask of each object
    labels: dict[SegmentRef, set[str]] = {}
    merged: list[tuple[SegmentRef, SegmentRef, float]] = []
    split: list[tuple[SegmentRef, SegmentRef]] = []
    for ref in order:
        seg = seg_of[ref]
        best_ref: SegmentRef | None = None
        best = 0.0
        for obj, obj_seg in objects.items():
            overlap = mask_overlap(seg, obj_seg)
            if overlap > best:
                best_ref, best = obj, overlap
        container = objects[best_ref] if best_ref is not None else None
        if (container is not None and best >= SPLIT_MIN_OVERLAP
                and seg.area < SPLIT_MAX_AREA_RATIO * container.area
                and hole_fraction(seg) >= SPLIT_MIN_HOLE):
            objects[best_ref] = _subtract(container, seg)
            split.append((ref, best_ref))
        elif best_ref is not None and best >= program.merge_overlap:
            labels[best_ref].add(ref.concept)
            merged.append((ref, best_ref, float(best)))
            continue
        objects[ref] = seg
        labels[ref] = {ref.concept}
    kept = list(objects)

    metrics: dict[SegmentRef, dict[str, float]] = {
        ref: {"area": float(seg.area), "length": float(mask_length(seg)),
              "hole": float(hole_fraction(seg))}
        for ref, seg in objects.items()
    }

    # Each object goes to the first part (in program order) whose concept is among its labels and
    # whose limits it meets.
    part_instances: dict[str, list[SegmentRef]] = {p.id: [] for p in program.parts}
    unassigned: list[SegmentRef] = []
    for ref in kept:
        part = next((p for p in program.parts
                     if p.concept.lower() in labels[ref] and p.accepts(metrics[ref])), None)
        if part is None:
            unassigned.append(ref)
        else:
            part_instances[part.id].append(ref)

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
                    part_id=check.part,
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
                    part_id=check.part,
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
        merged=merged,
        unassigned=unassigned,
        metrics=metrics,
        labels=labels,
        objects=objects,
        split=split,
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
