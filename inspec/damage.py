"""Visual damage check: Muse Spark looks at the whole kit photo for defects the part checks can't
measure (a torn bag, a broken or painted part, a foreign object).

The checks in a CheckProgram count and measure parts; they can't see colour, bruises or a torn
container. Here Muse Spark answers four yes/no questions per image (structured output). The
prompt names no particular kit: it is built from the kit name and packing list, and the same
wording is used for Screw Bag and Breakfast Box. Calibration applies the
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

QUESTIONS = ("container_damaged", "item_broken", "item_discoloured", "foreign_object")


class DamageReport(BaseModel):
    container_damaged: bool = Field(description="The bag, box or tray is torn, cut, cracked or dented")
    item_broken: bool = Field(description="A listed item is broken, crushed, cracked, bent or bruised")
    item_discoloured: bool = Field(description="A listed item has a colour, stain or mark unusual for it")
    foreign_object: bool = Field(description="Something that is not a listed item, or an item of the "
                                             "wrong kind, is inside")
    evidence: str = Field(description="Where each reported defect is")

    def flags(self) -> set[str]:
        return {q for q in QUESTIONS if getattr(self, q)}


INSTRUCTIONS = """\
You inspect a photo of a {kit_name} from a packing station, taken by a fixed overhead camera.
The packing list is: {packing_list}.
Ignore how many items there are and how much of each; that is checked elsewhere. Report only
physical defects you can actually see:
- container_damaged: the bag, box or tray holding the items is torn, cut, cracked or dented
- item_broken: a listed item is damaged: broken, a piece missing or snapped off, bent, cracked,
  crushed into fragments, or (for food) bruised, cut or rotten
- item_discoloured: a listed item has a colour, paint, stain or mark that is unusual for that kind
  of item
- foreign_object: something that is not a listed item is inside, or an item of the wrong kind is
  mixed in with the others
Reflections, shadows, wrinkles, printing on the packaging and the natural variation between items
of one kind (shape, size, ripeness, a shiny edge or a hole that belongs to the part) are normal.
Answer false unless the defect is clearly visible. In evidence, say where you see each defect.
"""


class DamageChecker:
    def __init__(self, packing_list: str, *, kit_name: str = "kit", llm: LLM | None = None,
                 cache_dir: str | Path = ".cache/damage") -> None:
        self.llm = llm or LLM()
        self.instructions = INSTRUCTIONS.format(packing_list=packing_list.strip(),
                                                kit_name=kit_name.strip() or "kit")
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
