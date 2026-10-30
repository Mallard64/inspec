"""Vision-only baseline: Muse Spark looks at the kit photo and says pass or fail, with no SAM,
no check program and no calibration.

This is what you'd build without Inspec: one prompt with the packing list and the photo. The model
reports a count per listed part and whether it sees damage; the verdict is computed here (counts
must match the list and no damage), so a failure can be split into "counts" and "damage".

With ``references`` the prompt also shows known-good kits first, which is the fairer comparison
to Inspec's calibration on good kits.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from inspec.compiler import _image_content
from inspec.llm import LLM, cached_generate


class PartCount(BaseModel):
    part: str = Field(description="Part name as written in the packing list")
    expected: int = Field(description="Quantity in the packing list")
    seen: int = Field(description="How many you count in the photo")


class BaselineVerdict(BaseModel):
    counts: list[PartCount]
    damage: bool = Field(description="A part is broken, bent or painted, the bag is torn, or "
                                     "something that is not a listed part is inside")
    reason: str = Field(description="One sentence: what is wrong, or that the kit is fine")

    def failures(self) -> list[str]:
        """"counts" and/or "damage"; empty means the kit passes."""
        out = []
        if any(c.seen != c.expected for c in self.counts):
            out.append("counts")
        if self.damage:
            out.append("damage")
        return out


INSTRUCTIONS = """\
You inspect photos of kits in a clear plastic bag at a packing station. The packing list is:
{packing_list}.
For the kit you inspect: count each listed part you can see (give one entry per line of the
packing list) and say whether there is any damage: a broken, bent or painted part, a torn bag, or
something inside that is not a listed part. Parts of different sizes count as different parts; a
part of the wrong size counts toward neither. Reflections and wrinkles in the bag are normal.
"""


class VisionBaseline:
    def __init__(self, packing_list: str, *, llm: LLM | None = None,
                 references: list[str | Path] = (), cache_dir: str | Path = ".cache/baseline"):
        self.llm = llm or LLM()
        self.instructions = INSTRUCTIONS.format(packing_list=packing_list.strip())
        self.references = [Path(p) for p in references]
        self.cache_dir = Path(cache_dir)

    def inspect(self, image: str | Path) -> BaselineVerdict:
        image = Path(image)
        content: list[dict] = []
        if self.references:
            content.append({"type": "input_text", "text":
                            f"{len(self.references)} known-good kit(s) for reference:"})
            content += [_image_content(p) for p in self.references]
        content += [{"type": "input_text", "text": "Inspect this kit."}, _image_content(image)]
        return cached_generate(self.llm, self.instructions, content, BaselineVerdict,
                               [*self.references, image], self.cache_dir)

    def inspect_many(self, images: list[str | Path], *,
                     workers: int = 8) -> dict[str, BaselineVerdict]:
        with ThreadPoolExecutor(workers) as pool:
            return dict(zip(map(str, images), pool.map(self.inspect, images)))
