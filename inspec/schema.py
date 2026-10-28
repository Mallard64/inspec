"""Check-program schema: what the compiler emits and the executor runs.

A program has two lists:

- ``parts``: named things to find. Each part is one SAM concept plus optional size limits, so two
  parts can share a concept ("long screw" and "short screw" are both ``screw``, split by length).
- ``checks``: assertions on parts. ``count`` bounds how many instances a part has; ``measure``
  bounds a metric of every instance of a part.

Models are deliberately flat (nullable fields, no nested unions) so the JSON schema stays simple
enough for LLM structured output.

Before checks run, the executor merges SAM segments into objects: a segment mostly inside a larger
one (``merge_overlap``) is the same object with an extra label. On Screw Bag, SAM labels hex nuts and
washers as both "nut" and "washer", and calls screw heads "nuts", so labels alone can't separate
parts; size limits do.

Units: pixels of the source image. ``length`` is the extent of the mask along its principal axis;
``area`` is the mask pixel count.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Metric = Literal["area", "length"]

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_concept(concept: str) -> str:
    """SAM 3.1 takes one short noun phrase per request; reject anything else."""
    stripped = concept.strip()
    words = stripped.split()
    if not stripped:
        raise ValueError("concept must not be empty")
    if len(words) > 4:
        raise ValueError(f"concept must be at most 4 words: {concept!r}")
    if "," in stripped or ";" in stripped or "and" in (w.lower() for w in words):
        raise ValueError(f"concept must be one noun phrase, not a list: {concept!r}")
    return stripped


def _check_id(value: str, what: str) -> None:
    if not _ID_RE.match(value):
        raise ValueError(f"{what} id must be snake_case: {value!r}")


def _check_range(lo: float | None, hi: float | None, what: str) -> None:
    if lo is not None and lo < 0:
        raise ValueError(f"{what}: min must be >= 0")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"{what}: min {lo} > max {hi}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Part(_Strict):
    id: str = Field(description="snake_case name, e.g. long_screw")
    concept: str = Field(description="One short noun phrase sent to SAM, e.g. 'screw'")
    min_length: float | None = Field(None, description="Instances shorter than this are not this part")
    max_length: float | None = Field(None, description="Instances longer than this are not this part")
    min_area: float | None = Field(None, description="Instances smaller than this are not this part")
    max_area: float | None = Field(None, description="Instances larger than this are not this part")

    @model_validator(mode="after")
    def _validate(self) -> Part:
        _check_id(self.id, "part")
        self.concept = validate_concept(self.concept)
        _check_range(self.min_length, self.max_length, f"part {self.id} length")
        _check_range(self.min_area, self.max_area, f"part {self.id} area")
        return self


class Check(_Strict):
    id: str = Field(description="snake_case name, e.g. nut_count")
    type: Literal["count", "measure"]
    part: str = Field(description="Part id this check applies to")
    metric: Metric | None = Field(None, description="Required for measure, null for count")
    min: float | None = Field(None, description="Inclusive lower bound")
    max: float | None = Field(None, description="Inclusive upper bound")
    reason: str = Field("", description="Why this check exists, in plain words")

    @model_validator(mode="after")
    def _validate(self) -> Check:
        _check_id(self.id, "check")
        if self.min is None and self.max is None:
            raise ValueError(f"check {self.id}: needs min, max or both")
        _check_range(self.min, self.max, f"check {self.id}")
        if self.type == "measure" and self.metric is None:
            raise ValueError(f"check {self.id}: measure needs a metric")
        if self.type == "count":
            if self.metric is not None:
                raise ValueError(f"check {self.id}: count takes no metric")
            for bound in (self.min, self.max):
                if bound is not None and bound != int(bound):
                    raise ValueError(f"check {self.id}: count bounds must be whole numbers")
        return self


class CheckProgram(_Strict):
    version: Literal[1] = 1
    kit_name: str
    parts: list[Part]
    checks: list[Check]
    merge_overlap: float = Field(0.8, description="Segments with at least this fraction inside "
                                 "a larger segment are the same object")
    notes: str = Field("", description="Compiler's short rationale")

    @model_validator(mode="after")
    def _validate(self) -> CheckProgram:
        part_ids = [p.id for p in self.parts]
        check_ids = [c.id for c in self.checks]
        for ids, what in ((part_ids, "part"), (check_ids, "check")):
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise ValueError(f"duplicate {what} ids: {sorted(dupes)}")
        if not self.parts or not self.checks:
            raise ValueError("program needs at least one part and one check")
        known = set(part_ids)
        for check in self.checks:
            if check.part not in known:
                raise ValueError(f"check {check.id} refers to unknown part {check.part!r}")
        if not 0 < self.merge_overlap <= 1:
            raise ValueError("merge_overlap must be in (0, 1]")
        return self

    def concepts(self) -> list[str]:
        """Distinct SAM concepts in first-use order: one SAM call each per image."""
        seen: dict[str, None] = {}
        for part in self.parts:
            seen.setdefault(part.concept.lower(), None)
        return list(seen)
