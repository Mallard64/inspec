"""Parse raw `sam-3.1` response text into Segment objects.

Wire format (see ``docs/sam-output-format.md``)::

    <0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=0;y=0;data=H,W,<payload>|>,...

Pure: no I/O, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image
from meta_sam_parser import SegmentationMask, decode_mask_to_raster

_FRAME_RE = re.compile(r"<\d+f>")
_RECORD_RE = re.compile(
    r"(?P<object_id>[^<>,]+)"
    r"<\|box;(?P<box>[^|]*)\|>"
    r"<\|mask;(?P<mask>[^|]*)\|>"
)

_ENCODING_BY_MARKER = {"~": "lossless", "!": "one_bit"}


@dataclass(frozen=True)
class Segment:
    object_id: str
    box: tuple[int, int, int, int]  # x1, y1, x2, y2, inclusive, source-image pixels
    image_size: tuple[int, int]  # (width, height)
    mask: np.ndarray  # bool, shape (y2-y1+1, x2-x1+1), cropped to box
    confidence: float | None = None

    @property
    def area(self) -> int:
        """Number of True pixels in mask."""
        return int(self.mask.sum())

    def full_mask(self) -> np.ndarray:
        """Bool (height, width) mask pasted at (y1, x1)."""
        width, height = self.image_size
        x1, y1, x2, y2 = self.box
        full = np.zeros((height, width), dtype=bool)
        full[y1 : y2 + 1, x1 : x2 + 1] = self.mask
        return full


def _parse_box(body: str) -> tuple[tuple[int, int, int, int], tuple[int, int], float | None]:
    fields: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Malformed box token {body!r}: {part!r} has no '='.")
        key, _, value = part.partition("=")
        fields[key.strip()] = value.strip()
    try:
        x1 = int(fields["x1"])
        y1 = int(fields["y1"])
        x2 = int(fields["x2"])
        y2 = int(fields["y2"])
        width = int(fields["w"])
        height = int(fields["h"])
    except KeyError as exc:
        raise ValueError(f"Box token {body!r} is missing required field {exc}.") from exc
    except ValueError as exc:
        raise ValueError(f"Box token {body!r} has a non-integer coordinate: {exc}.") from exc
    confidence: float | None = None
    if "c" in fields:
        try:
            confidence = float(fields["c"])
        except ValueError as exc:
            raise ValueError(
                f"Box token {body!r} has non-numeric confidence {fields['c']!r}."
            ) from exc
    if width <= 0 or height <= 0:
        raise ValueError(f"Box token {body!r} has non-positive image size {(width, height)}.")
    if not (0 <= x1 <= x2 < width and 0 <= y1 <= y2 < height):
        raise ValueError(
            f"Box {(x1, y1, x2, y2)} is outside the {width}x{height} image."
        )
    return (x1, y1, x2, y2), (width, height), confidence


def _parse_mask(body: str) -> tuple[str, int, int]:
    data: str | None = None
    for part in body.split(";"):
        part = part.strip()
        if part.startswith("data="):
            data = part[len("data=") :]
            break
    if data is None:
        raise ValueError(f"Mask token {body!r} has no 'data=' field.")
    # data=<H>,<W>,<payload>: split off the first two comma-separated fields;
    # the payload itself may contain commas, so split at most twice.
    head = data.split(",", 2)
    if len(head) != 3 or not head[0] or not head[1] or not head[2]:
        raise ValueError(f"Mask token {body!r} has malformed 'data=' field {data!r}.")
    try:
        mask_h = int(head[0])
        mask_w = int(head[1])
    except ValueError as exc:
        raise ValueError(
            f"Mask token {body!r} has non-integer dimensions {head[0]!r},{head[1]!r}."
        ) from exc
    return head[2], mask_w, mask_h


def _decode_mask(payload: str, width: int, height: int) -> np.ndarray:
    try:
        encoding = _ENCODING_BY_MARKER[payload[0]]
    except (IndexError, KeyError):
        marker = payload[0] if payload else ""
        raise ValueError(
            f"Unknown mask encoding char {marker!r}: expected '!' (one_bit) or '~' (lossless)."
        ) from None
    try:
        raw: bytes = decode_mask_to_raster(
            SegmentationMask(encoding=encoding, payload=payload, width=width, height=height)
        )
    except Exception as exc:
        raise ValueError(f"Could not decode {encoding} mask payload: {exc}.") from exc
    arr = np.frombuffer(raw, dtype=np.uint8).astype(bool).reshape((height, width))
    return arr


def _is_downscaled(mask_w: int, mask_h: int, box_w: int, box_h: int) -> bool:
    """SAM caps a mask's long side (seen: 1024 px for an 835x1062 box) and scales the other side
    to match. Accept only that: smaller on both sides, same scale on both within rounding."""
    if mask_w > box_w or mask_h > box_h or max(mask_w, mask_h) >= max(box_w, box_h):
        return False
    scale = max(mask_w, mask_h) / max(box_w, box_h)
    return abs(round(box_w * scale) - mask_w) <= 1 and abs(round(box_h * scale) - mask_h) <= 1


def parse_sam_output(text: str) -> list[Segment]:
    """Parse raw `sam-3.1` response text into Segments, in order of appearance."""
    body = text.strip()
    if not body:
        return []
    body = _FRAME_RE.sub("", body, count=1).strip()
    if not body:
        return []

    matches = list(_RECORD_RE.finditer(body))
    pos = 0
    segments: list[Segment] = []
    for match in matches:
        gap = body[pos : match.start()].strip()
        if gap and gap.strip(",").strip():
            if "<|box;" in gap:
                raise ValueError(f"Box without a mask near {gap!r}.")
            raise ValueError(f"Could not parse SAM output near {gap!r}.")
        # A bare comma separator is fine; anything else was rejected above.
        box, image_size, confidence = _parse_box(match.group("box"))
        payload, mask_w, mask_h = _parse_mask(match.group("mask"))
        x1, y1, x2, y2 = box
        box_w, box_h = x2 - x1 + 1, y2 - y1 + 1
        if (mask_w, mask_h) != (box_w, box_h) and not _is_downscaled(mask_w, mask_h, box_w, box_h):
            raise ValueError(
                f"Mask dims {(mask_w, mask_h)} don't match box {(x1, y1, x2, y2)} "
                f"(expected {(box_w, box_h)})."
            )
        mask = _decode_mask(payload, mask_w, mask_h)
        if mask.shape != (box_h, box_w):
            mask = np.asarray(Image.fromarray(mask).resize((box_w, box_h), Image.NEAREST))
        segments.append(
            Segment(
                object_id=match.group("object_id"),
                box=box,
                image_size=image_size,
                mask=mask,
                confidence=confidence,
            )
        )
        pos = match.end()
    tail = body[pos:].strip()
    if tail and tail.strip(",").strip():
        if "<|box;" in tail:
            raise ValueError(f"Box without a mask near {tail!r}.")
        raise ValueError(f"Could not parse SAM output near {tail!r}.")
    if not matches and body.strip(",").strip():
        raise ValueError(f"Could not parse SAM output near {body!r}.")
    return segments
