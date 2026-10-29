import numpy as np
import pytest

import inspec.calibrate as cal
from inspec.llm import Generation
from inspec.schema import CheckProgram
from inspec.segments import Segment


def bar(length: int, y0: int) -> Segment:
    return Segment(object_id="0", box=(0, y0, length - 1, y0 + 19), image_size=(1000, 1000),
                   mask=np.ones((20, length), dtype=bool))


COMPILED = CheckProgram.model_validate({
    "kit_name": "screws",
    "parts": [{"id": "long_screw", "concept": "screw"}, {"id": "short_screw", "concept": "screw"}],
    "checks": [
        {"id": "long_count", "type": "count", "part": "long_screw", "min": 1, "max": 1},
        {"id": "short_count", "type": "count", "part": "short_screw", "min": 1, "max": 1},
    ],
})


def repaired(split: float, **changes) -> CheckProgram:
    data = COMPILED.model_dump()
    data["parts"][0]["min_length"] = split
    data.update(changes)
    return CheckProgram.model_validate(data)


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def generate(self, instructions, content, out_type, *, validate=None):
        self.prompts.append(content[0]["text"])
        value = self.outputs.pop(0)
        if validate is not None:
            validate(value)
        return Generation(value, 1)


@pytest.fixture
def good_kits(monkeypatch):
    kits = {f"{i}.png": {"screw": [bar(400 + i, 0), bar(290 + i, 100)]} for i in range(3)}
    monkeypatch.setattr(cal, "fetch_many", lambda program, images, client, workers: kits)
    return list(kits)


def test_repair_converges_and_keeps_history(good_kits):
    llm = FakeLLM([repaired(345)])
    result = cal.calibrate(COMPILED, good_kits, sam=None, llm=llm, log=lambda _: None)
    assert result.converged
    assert result.program.parts[0].min_length == 345
    assert [(r.passed, r.total) for r in result.rounds] == [(0, 3), (3, 3)]
    assert "part long_screw: 6 objects" in llm.prompts[0]  # first-match: both screws go to long
    assert result.to_dict()["rounds"][0]["repair"]["attempts"] == 1


def test_worse_repair_is_discarded_and_reported(good_kits):
    llm = FakeLLM([repaired(401), repaired(500), repaired(345)])
    result = cal.calibrate(COMPILED, good_kits, sam=None, llm=llm, log=lambda _: None)
    assert [r.passed for r in result.rounds] == [0, 2, 0, 3]
    assert result.converged and result.program.parts[0].min_length == 345
    assert "made things worse" in llm.prompts[2]
    assert '"min_length": 401.0' in llm.prompts[2]  # repaired from the best program, not the last


def test_unchanged_repair_stops_and_returns_best(good_kits):
    llm = FakeLLM([repaired(401), repaired(401, notes="same rules")])
    result = cal.calibrate(COMPILED, good_kits, sam=None, llm=llm, max_rounds=5,
                           log=lambda _: None)
    assert len(result.rounds) == 2 and not result.converged
    assert result.program.parts[0].min_length == 401


def test_keeps_counts_rejects_changed_quantities_and_parts():
    validate = cal.keeps_counts(COMPILED)
    validate(repaired(345))
    looser = COMPILED.model_dump()
    looser["checks"][0]["max"] = 2
    with pytest.raises(ValueError, match="count checks"):
        validate(CheckProgram.model_validate(looser))
    renamed = COMPILED.model_dump()
    renamed["parts"][1]["concept"] = "bolt"
    with pytest.raises(ValueError, match="parts"):
        validate(CheckProgram.model_validate(renamed))
