import numpy as np
from PIL import Image

from inspec.executor import run_program
from inspec.overlay import legend, object_parts, render
from inspec.schema import CheckProgram
from inspec.segments import Segment


def _segment(mask: np.ndarray, x0: int, y0: int) -> Segment:
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    return Segment(
        object_id=f"{x0},{y0}",
        box=(x0, y0, x0 + w - 1, y0 + h - 1),
        image_size=(20, 20),
        mask=mask,
    )


def _program() -> CheckProgram:
    return CheckProgram(
        kit_name="test",
        parts=[
            {"id": "long_screw", "concept": "screw"},
            {"id": "nut", "concept": "nut"},
        ],
        checks=[
            {"id": "long_screw_count", "type": "count", "part": "long_screw", "min": 1, "max": 1},
            {"id": "nut_count", "type": "count", "part": "nut", "min": 1, "max": 1},
        ],
    )


def _result():
    screw = np.zeros((4, 12), dtype=bool)
    screw[1:3, :] = True
    nut = np.zeros((5, 5), dtype=bool)
    nut[1:4, 1:4] = True
    stray = np.zeros((3, 3), dtype=bool)
    stray[1, 1] = True
    segments = {
        "screw": [_segment(screw, 1, 1)],
        "nut": [_segment(nut, 12, 12)],
        "washer": [_segment(stray, 0, 15)],
    }
    return run_program(_program(), segments)


def test_object_parts_maps_evidence_and_unassigned():
    result = _result()
    assert result.passed
    parts = object_parts(result)
    assert set(parts) == set(result.objects)
    by_part = {part: ref for ref, part in parts.items()}
    assert parts[by_part["long_screw"]] == "long_screw"
    assert parts[by_part["nut"]] == "nut"
    unassigned = [ref for ref in result.unassigned]
    assert len(unassigned) == 1
    assert parts[unassigned[0]] == "unassigned"


def test_render_blends_mask_leaves_rest_and_input_untouched():
    result = _result()
    image = Image.new("RGB", (20, 20), (10, 10, 10))
    before = np.asarray(image).copy()
    out = render(image, result)
    assert out.size == image.size
    assert out.mode == "RGB"
    assert np.array_equal(np.asarray(image), before)
    out_arr = np.asarray(out)
    # A masked pixel changes colour; the top-right corner is in no mask
    # and under no label, so it stays put.
    assert not np.array_equal(out_arr[2, 5], np.array([10, 10, 10]))
    assert np.array_equal(out_arr[0, 19], np.array([10, 10, 10]))


def test_legend_counts_match_objects():
    result = _result()
    rows = legend(result)
    assert [r[0] for r in rows] == ["long_screw", "nut", "unassigned"]  # program order
    assert {r[0]: r[2] for r in rows} == {"long_screw": 1, "nut": 1, "unassigned": 1}
    assert all(len(r[1]) == 3 for r in rows)


def test_part_keeps_its_colour_when_other_parts_are_missing():
    full = dict((p, c) for p, c, _ in legend(_result()))
    no_screw = _result()
    no_screw.objects = {r: s for r, s in no_screw.objects.items() if r.concept != "screw"}
    assert dict((p, c) for p, c, _ in legend(no_screw))["nut"] == full["nut"]
