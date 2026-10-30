"""Compile a packing list into a CheckProgram with Muse Spark.

The prompt encodes what we verified about SAM 3.1 (see docs/sam-output-format.md and the README
build log):

- SAM takes one short noun phrase per call and ignores size words: "long screw" returns every
  screw. So items that differ only by size share one base-noun concept and are told apart by
  measured length or area.
- The compiler can't see pixel sizes, so it leaves size limits empty. Calibration on known-good
  images fills them in from real measurements.
"""

from __future__ import annotations

import base64
from pathlib import Path

from inspec.llm import LLM, Generation
from inspec.schema import CheckProgram

INSTRUCTIONS = """\
You compile a kit's packing list into a check program for an automated visual inspection station.
An overhead camera photographs each kit. A segmentation model (SAM) finds every instance of a
concept, and plain code runs your checks on the resulting masks.

Rules for parts:
- One part per distinct item in the packing list. Part ids are snake_case ("long_screw").
- `concept` is what SAM is asked to find: the plain base noun, singular, 1-2 words ("screw",
  "nut", "washer"). SAM ignores size, position, colour and count words, so never put those in a
  concept.
- Items that differ only by size (long vs short, large vs small) MUST share the same concept and
  become separate parts, e.g. long_screw and short_screw both with concept "screw".
- Leave every limit (min_/max_ length, area, hole) null. You can't see pixel measurements; a
  calibration step sets them from measurements of known-good kits.

Rules for checks:
- One `count` check per part, with min and max both equal to the quantity in the packing list
  (metric null). Id like "nut_count".
- An item with no quantity (loose or bulk items such as "granola" or "almonds") must be present
  but its amount isn't a count: use min 1 and max null.
- Do not add `measure` checks; calibration adds them when evidence calls for it.
- Give every check a one-line `reason` quoting the packing list.

Use `notes` to flag anything calibration must resolve, e.g. parts that share a concept and still
need a size split.
"""


def _image_content(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{data}"}


def compile_program(packing_list: str, *, kit_name: str = "kit",
                    example_images: list[str | Path] | None = None,
                    llm: LLM | None = None) -> Generation[CheckProgram]:
    """Packing list (+ optional photos of good kits) -> validated CheckProgram."""
    if not packing_list.strip():
        raise ValueError("packing list is empty")
    content: list[dict] = [{"type": "input_text", "text":
                            f"Kit name: {kit_name}\nPacking list: {packing_list.strip()}"}]
    for path in example_images or []:
        content.append(_image_content(Path(path)))
    return (llm or LLM()).generate(INSTRUCTIONS, content, CheckProgram)
