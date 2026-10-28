import json
from pathlib import Path

import numpy as np
import pytest

from inspec.executor import (
    ProgramResult,
    SegmentRef,
    fetch_segments,
    mask_iou,
    mask_length,
    run_program,
)
from inspec.schema import CheckProgram
from inspec.segments import Segment, parse_sam_output

FIXTURES = Path(__file__).parent / "fixtures" / "sam"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _segment(
    mask: np.ndarray,
    x0: int = 0,
    y0: int = 0,
    image_size: tuple[int, int] = (1000, 1000),
    object_id: str = "0",
) -> Segment:
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    return Segment(
        object_id=object_id,
        box=(x0, y0, x0 + w - 1, y0 + h - 1),
        image_size=image_size,
        mask=mask,
    )


def _bar(length: int, x0: int = 0, y0: int = 0) -> Segment:
    return _segment(np.ones((20, length), dtype=bool), x0=x0, y0=y0)


def _program(
    parts: list[dict],
    checks: list[dict],
    dedupe: list[dict] | None = None,
) -> CheckProgram:
    return CheckProgram(
        kit_name="test",
        parts=parts,  # type: ignore[arg-type]
        dedupe=dedupe or [],  # type: ignore[arg-type]
        checks=checks,  # type: ignore[arg-type]
    )


def _disk(radius: int = 20, size: int = 64) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    c = size // 2
    return (xx - c) ** 2 + (yy - c) ** 2 <= radius**2


# --- mask_length ---


def test_mask_length_horizontal_rect_from_fixture() -> None:
    (segment,) = parse_sam_output(_read("rect_one_bit.txt"))
    assert segment.mask.shape == (40, 160)
    assert mask_length(segment) == pytest.approx(160, abs=1)


def test_mask_length_vertical_rect() -> None:
    segment = _segment(np.ones((160, 40), dtype=bool))
    assert mask_length(segment) == pytest.approx(160, abs=1)


def test_mask_length_diagonal_line() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    for i in range(100):
        mask[i, i] = True
    assert mask_length(_segment(mask)) == pytest.approx(141, abs=2)


def test_mask_length_disk() -> None:
    assert mask_length(_segment(_disk(20))) == pytest.approx(41, abs=2)


def test_mask_length_degenerate() -> None:
    assert mask_length(_segment(np.zeros((10, 10), dtype=bool))) == 0.0
    assert mask_length(_segment(np.ones((1, 1), dtype=bool))) == 1.0


# --- mask_iou ---


def test_mask_iou_identical() -> None:
    a = _bar(30)
    assert mask_iou(a, _bar(30)) == pytest.approx(1.0)


def test_mask_iou_disjoint() -> None:
    a = _bar(30, x0=0)
    b = _bar(30, x0=200)
    assert mask_iou(a, b) == 0.0


def test_mask_iou_half_overlap() -> None:
    a = _segment(np.ones((10, 10), dtype=bool), x0=0, y0=0)
    b = _segment(np.ones((10, 10), dtype=bool), x0=5, y0=0)
    assert mask_iou(a, b) == pytest.approx(1 / 3)


def test_mask_iou_empty_union() -> None:
    a = _segment(np.zeros((10, 10), dtype=bool), x0=0, y0=0)
    b = _segment(np.zeros((10, 10), dtype=bool), x0=0, y0=0)
    assert mask_iou(a, b) == 0.0


# --- dedupe ---


def _nut_washer_program() -> CheckProgram:
    return _program(
        parts=[
            {"id": "nut", "concept": "nut"},
            {"id": "washer", "concept": "washer"},
        ],
        dedupe=[{"keep": "washer", "drop": "nut", "min_iou": 0.5}],
        checks=[
            {"id": "nut_count", "type": "count", "part": "nut", "min": 1, "max": 1},
        ],
    )


def test_dedupe_drops_overlapping_segment() -> None:
    washer = _segment(np.ones((20, 20), dtype=bool), x0=10, y0=10)
    nut_same = _segment(np.ones((20, 20), dtype=bool), x0=10, y0=10)
    nut_far = _segment(np.ones((20, 20), dtype=bool), x0=500, y0=500)
    result = run_program(
        _nut_washer_program(),
        {"nut": [nut_same, nut_far], "washer": [washer]},
    )
    assert result.dropped == [
        (SegmentRef("nut", 0), SegmentRef("washer", 0), pytest.approx(1.0))
    ]
    (check,) = result.checks
    assert check.passed
    assert check.value == 1
    assert check.evidence == [SegmentRef("nut", 1)]
    assert SegmentRef("nut", 0) not in result.metrics


# --- count checks ---


def _count_program(min_value: float | None, max_value: float | None) -> CheckProgram:
    return _program(
        parts=[{"id": "nut", "concept": "nut"}],
        checks=[
            {
                "id": "nut_count",
                "type": "count",
                "part": "nut",
                "min": min_value,
                "max": max_value,
            }
        ],
    )


def test_count_pass_and_message() -> None:
    result = run_program(
        _count_program(2, 2),
        {"nut": [_bar(10, x0=0), _bar(10, x0=100)]},
    )
    (check,) = result.checks
    assert check.passed
    assert check.value == 2
    assert result.passed
    assert "2" in check.message
    assert check.expected == (2, 2)


def test_count_fail() -> None:
    result = run_program(
        _count_program(2, 2),
        {"nut": [_bar(10)]},
    )
    (check,) = result.checks
    assert not check.passed
    assert check.value == 1
    assert not result.passed
    assert result.failed() == [check]


def test_count_open_bounds_min_only() -> None:
    program = _count_program(2, None)
    assert run_program(program, {"nut": [_bar(10), _bar(10, x0=50)]}).passed
    assert run_program(program, {"nut": [_bar(10), _bar(10, x0=50), _bar(10, x0=90)]}).passed
    assert not run_program(program, {"nut": [_bar(10)]}).passed


# --- length split + measure ---


def _screw_program() -> CheckProgram:
    return _program(
        parts=[
            {"id": "long_screw", "concept": "screw", "min_length": 300},
            {"id": "short_screw", "concept": "screw", "max_length": 300},
        ],
        checks=[
            {"id": "long_count", "type": "count", "part": "long_screw", "min": 1, "max": 1},
            {"id": "short_count", "type": "count", "part": "short_screw", "min": 1, "max": 1},
        ],
    )


def test_length_split_assigns_one_instance_each() -> None:
    result = run_program(
        _screw_program(),
        {"screw": [_bar(400), _bar(250, x0=0, y0=100)]},
    )
    assert result.passed
    by_id = {c.check_id: c for c in result.checks}
    assert by_id["long_count"].evidence == [SegmentRef("screw", 0)]
    assert by_id["short_count"].evidence == [SegmentRef("screw", 1)]
    assert result.unassigned == []


def test_measure_fail_message_contains_value() -> None:
    program = _program(
        parts=[{"id": "long_screw", "concept": "screw", "min_length": 300}],
        checks=[
            {
                "id": "long_length",
                "type": "measure",
                "part": "long_screw",
                "metric": "length",
                "min": None,
                "max": 420,
            }
        ],
    )
    result = run_program(program, {"screw": [_bar(500)]})
    (check,) = result.checks
    assert check.value == [pytest.approx(500, abs=1)]
    assert not check.passed
    assert not result.passed
    assert "500" in check.message
    assert check.expected == (None, 420)


def test_measure_zero_instances_passes() -> None:
    program = _program(
        parts=[
            {"id": "long_screw", "concept": "screw", "min_length": 300},
            {"id": "short_screw", "concept": "screw", "max_length": 300},
        ],
        checks=[
            {
                "id": "short_length",
                "type": "measure",
                "part": "short_screw",
                "metric": "length",
                "min": None,
                "max": 290,
            }
        ],
    )
    result = run_program(program, {"screw": [_bar(400)]})
    (check,) = result.checks
    assert check.value == []
    assert check.passed
    assert check.evidence == []


# --- assignment / keys ---


def test_unassigned_segment_matching_no_part() -> None:
    program = _program(
        parts=[{"id": "long_screw", "concept": "screw", "min_length": 300}],
        checks=[
            {"id": "long_count", "type": "count", "part": "long_screw", "min": 0, "max": 5},
        ],
    )
    result = run_program(program, {"screw": [_bar(100)]})
    assert result.unassigned == [SegmentRef("screw", 0)]
    (check,) = result.checks
    assert check.value == 0
    assert check.passed


def test_missing_concept_raises() -> None:
    with pytest.raises(ValueError, match="nut"):
        run_program(_count_program(0, 5), {"screw": []})


def test_empty_list_gives_count_zero() -> None:
    result = run_program(_count_program(0, 0), {"nut": []})
    assert result.checks[0].value == 0
    assert result.passed


# --- serialization / fetch ---


def test_to_dict_is_json_safe() -> None:
    result = run_program(
        _screw_program(),
        {"screw": [_bar(400), _bar(250, x0=0, y0=100)]},
    )
    payload = result.to_dict()
    text = json.dumps(payload)
    assert isinstance(result, ProgramResult)
    assert json.loads(text)["passed"] is True
    for ref in list(payload["metrics"]) + payload["unassigned"]:
        assert isinstance(ref, str) and "#" in ref


def test_fetch_segments_calls_once_per_distinct_concept() -> None:
    text = _read("rect_one_bit.txt")

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def segment_text(self, image_path: str | Path, concept: str) -> str:
            self.calls.append(concept)
            return text

    client = FakeClient()
    out = fetch_segments(_screw_program(), "some.png", client)  # type: ignore[arg-type]
    assert set(out) == {"screw"}
    assert client.calls == ["screw"]
    assert len(out["screw"]) == 1

    program = _program(
        parts=[
            {"id": "long_screw", "concept": "screw", "min_length": 300},
            {"id": "nut", "concept": "nut"},
        ],
        checks=[
            {"id": "nut_count", "type": "count", "part": "nut", "min": 0, "max": 5},
        ],
    )
    client2 = FakeClient()
    out2 = fetch_segments(program, "some.png", client2)  # type: ignore[arg-type]
    assert sorted(client2.calls) == ["nut", "screw"]
    assert set(out2) == {"nut", "screw"}
