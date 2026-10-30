"""Visual damage check: Muse Spark looks at the whole kit photo for defects the part checks can't
measure (a torn bag, a broken or painted part, a foreign object).

The checks in a CheckProgram count and measure parts; they can't see colour or a torn bag. Here
Muse Spark answers four yes/no questions per image (structured output). Calibration applies the
same rule as for part checks: a question that fires on known-good kits is wrong, so any question
that flags more than a small share of good calibration kits is switched off (``calibrate_damage``).

Answers are cached on disk by (model, prompt, image) so re-evaluation doesn't re-call the model.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from inspec.compiler import _image_content
from inspec.llm import LLM, cached_generate

QUESTIONS = ("bag_torn", "part_broken", "part_discoloured", "foreign_object")


class DamageReport(BaseModel):
    bag_torn: bool = Field(description="The bag has a tear, cut or hole")
    part_broken: bool = Field(description="A part is clearly broken or bent")
    part_discoloured: bool = Field(description="A part has paint or a colour other than bare metal")
    foreign_object: bool = Field(description="Something that is not a listed part is in the bag")
    evidence: str = Field(description="Where each reported defect is")

    def flags(self) -> set[str]:
        return {q for q in QUESTIONS if getattr(self, q)}


INSTRUCTIONS = """\
You inspect a photo of a kit in a clear plastic bag. The packing list is: {packing_list}.
All parts should be plain bare metal. Ignore how many parts there are; that is checked
elsewhere. Report only physical defects you can actually see:
- bag_torn: the bag has a tear, cut or hole
- part_broken: a part is clearly broken: a piece is missing or snapped off, or a part is bent.
  Washers are closed rings; a reflection, shadow or the thin edge of a ring often looks like a gap
  but is not one. Only report a broken washer if a piece of the ring is visibly missing
- part_discoloured: a part has paint or a colour other than bare metal
- foreign_object: something that is not one of the listed parts or the bag is inside
Reflections, wrinkles and printed symbols on the bag are normal. Answer false unless the defect is
clearly visible. In evidence, say where you see each defect.
"""


class DamageChecker:
    def __init__(self, packing_list: str, *, llm: LLM | None = None,
                 cache_dir: str | Path = ".cache/damage") -> None:
        self.llm = llm or LLM()
        self.instructions = INSTRUCTIONS.format(packing_list=packing_list.strip())
        self.cache_dir = Path(cache_dir)

    def inspect(self, image: str | Path) -> DamageReport:
        image = Path(image)
        return cached_generate(self.llm, self.instructions, [
            {"type": "input_text", "text": "Inspect this kit."}, _image_content(image)],
            DamageReport, [image], self.cache_dir)

    def inspect_many(self, images: list[str | Path], *,
                     workers: int = 8) -> dict[str, DamageReport]:
        with ThreadPoolExecutor(workers) as pool:
            return dict(zip(map(str, images), pool.map(self.inspect, images)))


def calibrate_damage(reports: dict[str, DamageReport], *,
                     max_false_alarm: float = 0.034) -> dict:
    """Keep the questions that flag at most ``max_false_alarm`` of known-good kits (default: 2 of
    60). Returns {"enabled": [...], "false_alarms": {question: count}, "images": n}."""
    n = len(reports)
    counts = {q: sum(q in r.flags() for r in reports.values()) for q in QUESTIONS}
    enabled = [q for q in QUESTIONS if counts[q] <= max_false_alarm * n]
    return {"enabled": enabled, "false_alarms": counts, "images": n}


def damaged(report: DamageReport, enabled: list[str]) -> list[str]:
    """Enabled questions this report answers yes to (empty = no damage found)."""
    return [q for q in enabled if q in report.flags()]


def to_json(reports: dict[str, DamageReport]) -> str:
    return json.dumps({Path(p).name: r.model_dump() for p, r in reports.items()}, indent=1)
