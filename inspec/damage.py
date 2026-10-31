"""Visual damage check: Muse Spark looks at the whole kit photo for defects the part checks can't
measure (a torn bag, a broken or painted part, a foreign object).

The checks in a CheckProgram count and measure parts; they can't see colour, bruises or a torn
container. Here Muse Spark answers yes/no questions per image (structured output): three about
the kit as a whole, and one "is any <item> damaged?" per packing-list item. The prompt names no
particular kit: it is built from the kit name and packing list, and the same wording is used for
Screw Bag and Breakfast Box. Calibration applies the same rule as for part checks: a question
that fires on known-good kits is wrong, so any question that flags more than a small share of good
calibration kits is switched off (``calibrate_damage``).

Damage is asked per item because what's normal differs by item: chipped almonds are normal, a
bruised tangerine isn't. With one shared "item broken" question, the almonds switched it off for
the fruit too.

Answers are cached on disk by (model, prompt, image) so re-evaluation doesn't re-call the model.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field, create_model

from inspec.compiler import _image_content
from inspec.llm import LLM, cached_generate

KIT_QUESTIONS = ("container_damaged", "item_discoloured", "foreign_object")
_LEADING_AMOUNT = re.compile(r"^(\d+|a|an|one|two|three|four|five|six|some)\s+", re.I)


def packing_items(packing_list: str) -> list[str]:
    """Item names from a packing list, without amounts: "2 nuts, granola" -> ["nuts", "granola"]."""
    items = []
    for chunk in re.split(r",|;|\band\b", packing_list):
        item = _LEADING_AMOUNT.sub("", chunk.strip()).strip()
        if item and item.lower() not in (i.lower() for i in items):
            items.append(item)
    return items


def item_question(item: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", item.lower()).strip("_") + "_damaged"


class DamageReport(BaseModel):
    """Base for the per-packing-list report types built by ``report_type``. Every bool field is a
    question."""

    def flags(self) -> set[str]:
        return {name for name, value in self if value is True}


def report_type(items: list[str]) -> type[DamageReport]:
    """Structured-output type: kit-wide questions, one damage question per item, then evidence."""
    fields: dict = {"container_damaged": (bool, Field(
        description="The bag, box or tray is torn, cut, cracked or dented"))}
    for item in items:
        fields[item_question(item)] = (bool, Field(
            description=f"Any of the {item} is damaged (see instructions)"))
    fields["item_discoloured"] = (bool, Field(
        description="A listed item has a colour, stain or mark unusual for it"))
    fields["foreign_object"] = (bool, Field(
        description="Something that is not a listed item, or an item of the wrong kind, is inside"))
    fields["evidence"] = (str, Field(description="Where each reported defect is"))
    return create_model("DamageReport", __base__=DamageReport, **fields)


def questions(report_cls: type[DamageReport]) -> list[str]:
    return [n for n, f in report_cls.model_fields.items() if f.annotation is bool]


INSTRUCTIONS = """\
You inspect a photo of a {kit_name} from a packing station, taken by a fixed overhead camera.
The packing list is: {packing_list}.
Ignore how many items there are and how much of each; that is checked elsewhere. Report only
physical defects you can actually see:
- container_damaged: the bag, box or tray holding the items is torn, cut, cracked or dented
{item_lines}
- item_discoloured: a listed item has a colour, paint, stain or mark that is unusual for that kind
  of item
- foreign_object: something that is not a listed item is inside, or an item of the wrong kind is
  mixed in with the others
Reflections, shadows, wrinkles, printing on the packaging and the natural variation between items
of one kind (shape, size, ripeness, a shiny edge or a hole that belongs to the part) are normal.
Judge each item against what is normal for that kind of item: some items are naturally irregular
or broken into pieces. Answer false unless the defect is clearly visible. In evidence, say where
you see each defect.
"""


class DamageChecker:
    def __init__(self, packing_list: str, *, kit_name: str = "kit", llm: LLM | None = None,
                 cache_dir: str | Path = ".cache/damage") -> None:
        self.llm = llm or LLM()
        self.items = packing_items(packing_list)
        self.report_type = report_type(self.items)
        self.questions = questions(self.report_type)
        item_lines = "\n".join(
            f"- {item_question(i)}: any of the {i} is damaged: broken, a piece missing or snapped "
            f"off, bent, cracked, crushed, or (for food) bruised, cut or rotten" for i in self.items)
        self.instructions = INSTRUCTIONS.format(packing_list=packing_list.strip(),
                                                kit_name=kit_name.strip() or "kit",
                                                item_lines=item_lines)
        self.cache_dir = Path(cache_dir)

    def inspect(self, image: str | Path) -> DamageReport:
        image = Path(image)
        return cached_generate(self.llm, self.instructions, [
            {"type": "input_text", "text": "Inspect this kit."}, _image_content(image)],
            self.report_type, [image], self.cache_dir)

    def inspect_many(self, images: list[str | Path], *,
                     workers: int = 8) -> dict[str, DamageReport]:
        with ThreadPoolExecutor(workers) as pool:
            return dict(zip(map(str, images), pool.map(self.inspect, images)))


def calibrate_damage(reports: dict[str, DamageReport], *,
                     max_false_alarm: float = 0.034) -> dict:
    """Keep the questions that flag at most ``max_false_alarm`` of known-good kits (default: 2 of
    60). Returns {"enabled": [...], "false_alarms": {question: count}, "images": n}."""
    n = len(reports)
    asked = questions(type(next(iter(reports.values())))) if reports else []
    counts = {q: sum(q in r.flags() for r in reports.values()) for q in asked}
    enabled = [q for q in asked if counts[q] <= max_false_alarm * n]
    return {"enabled": enabled, "false_alarms": counts, "images": n}


def damaged(report: DamageReport, enabled: list[str]) -> list[str]:
    """Enabled questions this report answers yes to (empty = no damage found)."""
    return [q for q in enabled if q in report.flags()]


def to_json(reports: dict[str, DamageReport]) -> str:
    return json.dumps({Path(p).name: r.model_dump() for p, r in reports.items()}, indent=1)
