"""Draw part masks over a kit photo.

Pure Numpy + Pillow: each object in a :class:`ProgramResult` gets a fixed colour
per part id so the Streamlit page can show what the program saw.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from inspec.executor import ProgramResult, SegmentRef

ALPHA = 0.45

PALETTE: tuple[tuple[int, int, int], ...] = (
    (230, 57, 70),
    (37, 150, 190),
    (52, 168, 83),
    (250, 173, 20),
    (148, 103, 189),
    (255, 127, 14),
    (44, 160, 160),
    (214, 39, 103),
)

UNASSIGNED_COLOR: tuple[int, int, int] = (150, 150, 150)


def _part_colors(result: ProgramResult) -> dict[str, tuple[int, int, int]]:
    """Fixed colour per part id, in the order the program's checks name parts, so a part keeps
    its colour across images whatever was found."""
    part_ids = list(dict.fromkeys(c.part_id for c in result.checks if c.part_id))
    colors = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(part_ids)}
    colors["unassigned"] = UNASSIGNED_COLOR
    return colors


def object_parts(result: ProgramResult) -> dict[SegmentRef, str]:
    """Part id per object: the ``part_id`` of the ``count`` check whose evidence holds it.

    Objects in ``result.unassigned`` (or in no count evidence) map to ``"unassigned"``.
    """
    owner: dict[SegmentRef, str] = {}
    for check in result.checks:
        # CheckResult carries no type; run_program stores an int for count checks
        # and a list of per-instance values for measure checks.
        if isinstance(check.value, list):
            continue
        for ref in check.evidence:
            owner.setdefault(ref, check.part_id)
    parts: dict[SegmentRef, str] = {}
    for ref in result.objects:
        parts[ref] = "unassigned" if ref in result.unassigned else owner.get(ref, "unassigned")
    return parts


def _mask_for(image_size: tuple[int, int], ref: SegmentRef, result: ProgramResult) -> np.ndarray:
    """Bool (H, W) mask of one object, clipped to the image size."""
    width, height = image_size
    full = np.asarray(result.objects[ref].full_mask(), dtype=bool)
    if full.shape == (height, width):
        return full
    mask = np.zeros((height, width), dtype=bool)
    h = min(height, full.shape[0])
    w = min(width, full.shape[1])
    mask[:h, :w] = full[:h, :w]
    return mask


def render(image: Image.Image, result: ProgramResult) -> Image.Image:
    """RGB copy of ``image`` with each object's mask alpha-blended in its part colour.

    A short text label (part id) is drawn at the top-left of each object's box.
    The input image is not modified.
    """
    base = image.convert("RGB")
    canvas = np.asarray(base).astype(np.float64)
    width, height = base.size
    parts = object_parts(result)
    colors = _part_colors(result)
    for ref, part_id in parts.items():
        mask = _mask_for((width, height), ref, result)
        if not mask.any():
            continue
        color = np.array(colors[part_id], dtype=np.float64)
        canvas[mask] = canvas[mask] * (1.0 - ALPHA) + color * ALPHA
    out = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=max(12, width // 45))
    for ref, part_id in parts.items():
        x1, y1, _, _ = result.objects[ref].box
        x = min(max(int(x1), 0), width - 1)
        y = min(max(int(y1), 0), height - 1)
        draw.text((x + 1, y + 1), part_id, fill=(255, 255, 255), font=font,
                  stroke_width=max(2, width // 400), stroke_fill=(0, 0, 0))
    return out


def legend(result: ProgramResult) -> list[tuple[str, tuple[int, int, int], int]]:
    """``(part id, colour, object count)`` rows, one per part found, in colour order."""
    parts = object_parts(result)
    colors = _part_colors(result)
    counts: dict[str, int] = {}
    for part_id in parts.values():
        counts[part_id] = counts.get(part_id, 0) + 1
    return [(part_id, colors[part_id], counts[part_id]) for part_id in colors if part_id in counts]
