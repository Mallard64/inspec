"""Concept repair: find words SAM actually understands for each part, before calibration.

The compiler picks a concept from the packing list ("nectarine", "banana chip"), but SAM 3.1 may
not know that word: on Breakfast Box, "nectarine" finds nothing on 2 of 5 good kits and "banana
chip" on 4 of 5, while "apple" and "banana slice" find them every time. Calibration can't fix
this because it must keep concepts fixed.

So, for each part whose concept finds nothing on too many good kits, Muse Spark proposes other
short phrases for what the item looks like, each one is tried on the same good kits, and the
phrase whose count most often fits the packing list wins. Scoring by count (not just "found
something") rules out catch-alls like "fruit", which returns every item in the box.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

from inspec.compiler import _image_content
from inspec.llm import LLM
from inspec.schema import CheckProgram
from inspec.segments import parse_sam_output

if TYPE_CHECKING:
    from inspec.sam_client import SamClient

MIN_FOUND = 0.9  # a concept must find something on at least this share of good kits


class ConceptIdeas(BaseModel):
    alternatives: list[str] = Field(description="Other short noun phrases, 1-2 words, singular")


IDEAS_INSTRUCTIONS = """\
A segmentation model (SAM) finds objects in a photo from a short noun phrase. It did not reliably
find this item from a kit's packing list using the phrase given. Look at the photo of a good kit
and propose up to 6 other phrases SAM might know for the same item: everyday synonyms, or a
common object it looks like (e.g. a plum might be found as "fruit" or "ball"). Each phrase is 1-2
words, singular, with no colour, size, position or count words.
"""


@dataclass
class Probe:
    concept: str
    found: float  # share of kits where SAM returned at least one instance
    fits: float  # share of kits where the instance count fits the packing list
    counts: list[int]


@dataclass
class PartRepair:
    part: str
    original: str
    chosen: str
    probes: list[Probe] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"part": self.part, "original": self.original, "chosen": self.chosen,
                "probes": [vars(p) for p in self.probes]}


def expected_range(program: CheckProgram, concept: str) -> tuple[int, float]:
    """Total instances of ``concept`` a good kit should hold: summed over the parts sharing it."""
    parts = {p.id for p in program.parts if p.concept.lower() == concept.lower()}
    counts = [c for c in program.checks if c.type == "count" and c.part in parts]
    lo = sum(int(c.min or 0) for c in counts)
    hi = float("inf") if any(c.max is None for c in counts) else sum(c.max for c in counts)
    return lo, hi


def probe(concept: str, images: list[Path], lo: int, hi: float, sam: SamClient, *,
          workers: int = 8) -> Probe:
    with ThreadPoolExecutor(workers) as pool:
        counts = list(pool.map(lambda p: len(parse_sam_output(sam.segment_text(p, concept))),
                               images))
    n = max(len(counts), 1)
    return Probe(concept, sum(c > 0 for c in counts) / n,
                 sum(lo <= c <= hi for c in counts) / n, counts)


def repair_concepts(program: CheckProgram, good_images: list[str | Path], *, sam: SamClient,
                    llm: LLM | None = None, workers: int = 8,
                    log: Callable[[str], None] = print) -> tuple[CheckProgram, list[PartRepair]]:
    """Return ``program`` with weak concepts replaced, and a record of every part that was probed.

    Parts sharing a concept (long and short screw) are probed once and keep sharing."""
    images = [Path(p) for p in good_images]
    llm = llm or LLM()
    replaced: dict[str, str] = {}
    repairs: list[PartRepair] = []
    for part in program.parts:
        concept = part.concept.lower()
        if concept in replaced:
            continue
        lo, hi = expected_range(program, concept)
        if lo == 0:
            continue
        current = probe(concept, images, lo, hi, sam, workers=workers)
        if current.found >= MIN_FOUND:
            continue
        log(f"concept {concept!r} for {part.id}: found on {current.found:.0%} of good kits; "
            f"asking for alternatives")
        ideas = llm.generate(IDEAS_INSTRUCTIONS, [
            {"type": "input_text", "text": f"Item: {part.id.replace('_', ' ')}\n"
                                           f"Phrase that failed: {concept}"},
            _image_content(images[0])], ConceptIdeas).value.alternatives
        probes = [current]
        for alt in dict.fromkeys(a.strip().lower() for a in ideas if a.strip()):
            if alt != concept and len(alt.split()) <= 3:
                probes.append(probe(alt, images, lo, hi, sam, workers=workers))
        best = max(probes, key=lambda p: (p.fits, p.found, p is current))
        for p in probes:
            log(f"  {p.concept!r}: found {p.found:.0%}, count fits {p.fits:.0%}")
        if best is not current and best.fits > current.fits:
            replaced[concept] = best.concept
            log(f"  -> using {best.concept!r}")
        repairs.append(PartRepair(part.id, concept, replaced.get(concept, concept), probes))
    if not replaced:
        return program, repairs
    data = program.model_dump()
    for p in data["parts"]:
        p["concept"] = replaced.get(p["concept"].lower(), p["concept"])
    return CheckProgram.model_validate(data), repairs
