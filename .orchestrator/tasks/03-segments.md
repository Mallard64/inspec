# Task 03: Parse SAM 3.1 output into segments

## Goal
Write `inspec/segments.py`, which turns raw `sam-3.1` response text into a list of `Segment` objects
with boxes and boolean masks.

## Context
Verified wire format (also in `docs/sam-output-format.md`):

```
<0f>0<|box;x1=180;y1=108;x2=220;y2=148;w=256;h=256|><|mask;x=0;y=0;data=41,41,!...|>,1<|box;...|><|mask;...|>
```

- Optional leading frame marker `<Nf>`; a single image is `<0f>`.
- Records look like `<object_id><|box;...|><|mask;...|>`, separated by commas. The empty string means
  zero matches.
- Box: `x1;y1;x2;y2` are inclusive source-image pixel corners; `w;h` are the image width and height.
  An optional `;c=<float>` confidence may appear in the box token.
- Mask: `data=<H>,<W>,<payload>`. **H (rows) comes first.** The mask is cropped to the box, so
  `H == y2-y1+1` and `W == x2-x1+1`. The first payload char gives the encoding: `~` = `"lossless"`,
  `!` = `"one_bit"`. An optional `;c=...` may appear before `data=`.
- Decode with Meta's `meta-sam-parser` (installed). Pass the **whole** payload, including the leading
  encoding char:

  ```python
  from meta_sam_parser import SegmentationMask, decode_mask_to_raster
  raw: bytes = decode_mask_to_raster(
      SegmentationMask(encoding="one_bit", payload=payload, width=W, height=H))
  # row-major, H*W bytes of 0/1
  ```

## Interface (implement exactly)

```python
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Segment:
    object_id: str
    box: tuple[int, int, int, int]   # x1, y1, x2, y2, inclusive, source-image pixels
    image_size: tuple[int, int]      # (width, height)
    mask: np.ndarray                 # bool, shape (y2-y1+1, x2-x1+1), cropped to box
    confidence: float | None = None

    @property
    def area(self) -> int: ...       # number of True pixels in mask

    def full_mask(self) -> np.ndarray: ...  # bool (height, width), mask pasted at (y1, x1)

def parse_sam_output(text: str) -> list[Segment]: ...
```

## Requirements
- Return segments in the order they appear. `""` or whitespace returns `[]`.
- Raise `ValueError` with a clear message on: an unknown encoding char, a box without a mask, mask
  dims that don't match the box, or a box outside the image.
- Keep it pure: no I/O and no network.
- Create `inspec/segments.py` and `tests/test_segments.py`. Do not touch any other file.

## Tests (`tests/test_segments.py`)
Fixtures are in `tests/fixtures/sam/` (see its README). Cover:
- `empty.txt` returns `[]`.
- `circles_one_bit.txt` returns 3 segments with boxes `{(20,108,60,148), (100,108,140,148),
  (180,108,220,148)}` (compare as a set) and `image_size == (256, 256)`. Each `area` is between 1250
  and 1350, `mask.shape == (41, 41)`, and `mask.dtype == bool`.
- `full_mask()` has shape `(256, 256)` and the same sum as `area`. For the disk centred at x=40 it's
  True at `[128, 40]` and False at `[0, 0]`.
- `circles_lossless.txt` gives masks identical to `circles_one_bit.txt`, matched by box.
- `rect_one_bit.txt`: one segment, box `(40, 60, 199, 99)`, `mask.shape == (40, 160)`, area `6400`.
- `ValueError` on a hand-built string with a bad encoding char, and on one with mismatched dims.

## Done when
- `/Users/bigdum/inspec/.venv/bin/python -m pytest tests/test_segments.py -q` passes, run from the
  worktree root.

## Constraints
- Python 3.11, type hints. Use only `numpy`, `meta-sam-parser` and the stdlib (all installed).
  Follow AGENTS.md.
