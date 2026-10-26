from pathlib import Path

import numpy as np
import pytest

from inspec.segments import Segment, parse_sam_output

FIXTURES = Path(__file__).parent / "fixtures" / "sam"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_empty() -> None:
    assert parse_sam_output(_read("empty.txt")) == []
    assert parse_sam_output("") == []
    assert parse_sam_output("   \n  ") == []


def test_circles_one_bit() -> None:
    segments = parse_sam_output(_read("circles_one_bit.txt"))
    assert len(segments) == 3
    assert {s.box for s in segments} == {
        (20, 108, 60, 148),
        (100, 108, 140, 148),
        (180, 108, 220, 148),
    }
    for s in segments:
        assert isinstance(s, Segment)
        assert s.image_size == (256, 256)
        assert 1250 <= s.area <= 1350
        assert s.mask.shape == (41, 41)
        assert s.mask.dtype == bool


def test_full_mask() -> None:
    segments = parse_sam_output(_read("circles_one_bit.txt"))
    by_box = {s.box: s for s in segments}
    disk = by_box[(20, 108, 60, 148)]
    full = disk.full_mask()
    assert full.shape == (256, 256)
    assert full.dtype == bool
    assert int(full.sum()) == disk.area
    assert full[128, 40]
    assert not full[0, 0]


def test_circles_lossless_matches_one_bit() -> None:
    one_bit = {s.box: s.mask for s in parse_sam_output(_read("circles_one_bit.txt"))}
    lossless = {s.box: s.mask for s in parse_sam_output(_read("circles_lossless.txt"))}
    assert set(lossless) == set(one_bit)
    for box, mask in lossless.items():
        assert np.array_equal(mask, one_bit[box])


def test_rect_one_bit() -> None:
    (segment,) = parse_sam_output(_read("rect_one_bit.txt"))
    assert segment.box == (40, 60, 199, 99)
    assert segment.image_size == (320, 200)
    assert segment.mask.shape == (40, 160)
    assert segment.mask.dtype == bool
    assert segment.area == 6400


def test_bad_encoding_char_raises() -> None:
    raw = _read("circles_one_bit.txt").replace("data=41,41,!", "data=41,41,?", 1)
    with pytest.raises(ValueError, match="encoding"):
        parse_sam_output(raw)


def test_mismatched_dims_raise() -> None:
    raw = _read("circles_one_bit.txt").replace("data=41,41,", "data=40,41,", 1)
    with pytest.raises(ValueError, match="don't match"):
        parse_sam_output(raw)
