"""Tests for inspec.sam_client (no network; fake OpenAI-like client)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import inspec.sam_client as sam_client_mod
from inspec.sam_client import SamClient

FIXTURE = Path(__file__).parent / "fixtures" / "sam" / "circles.png"
SAMPLE_TEXT = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=256;h=256|>"


class FakeResponses:
    def __init__(self, fake: "FakeClient") -> None:
        self._fake = fake

    def create(self, **kwargs):
        self._fake.calls.append(kwargs)
        return self._fake.next_response()


class FakeClient:
    def __init__(self, texts: list[str] | None = None) -> None:
        self.calls: list[dict] = []
        self._texts = list(texts) if texts else [SAMPLE_TEXT]
        self.responses = FakeResponses(self)

    def next_response(self):
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]
        if text is _EMPTY:
            return SimpleNamespace(output=[])
        return SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(text=text)])])


class _Empty:
    pass


_EMPTY = _Empty()


def make_client(cache_dir, texts=None, **kwargs):
    fake = FakeClient(texts)
    client = SamClient(cache_dir=str(cache_dir), client=fake, **kwargs)
    return client, fake


def test_first_call_request_shape(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    text = client.segment_text(FIXTURE, "nut")
    assert text == SAMPLE_TEXT
    assert len(fake.calls) == 1
    kwargs = fake.calls[0]
    assert kwargs["model"] == "sam-3.1"
    assert kwargs["metadata"] == {"mask_encoding": "one_bit"}
    content = kwargs["input"][0]["content"]
    assert kwargs["input"][0]["role"] == "user"
    by_type = {item["type"]: item for item in content}
    assert by_type["input_text"]["text"] == "nut"
    assert by_type["input_image"]["image_url"].startswith("data:image/png;base64,")


def test_second_call_uses_cache(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    first = client.segment_text(FIXTURE, "nut")
    second = client.segment_text(FIXTURE, "nut")
    assert first == second == SAMPLE_TEXT
    assert len(fake.calls) == 1


def test_new_client_same_cache_dir_hits_cache(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    assert client.segment_text(FIXTURE, "nut") == SAMPLE_TEXT
    assert len(fake.calls) == 1
    client2, fake2 = make_client(tmp_path)
    assert client2.segment_text(FIXTURE, "nut") == SAMPLE_TEXT
    assert len(fake2.calls) == 0


def test_same_bytes_different_filename_hits_cache(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    assert client.segment_text(FIXTURE, "nut") == SAMPLE_TEXT
    copy = tmp_path / "copy.png"
    shutil.copyfile(FIXTURE, copy)
    assert client.segment_text(copy, "nut") == SAMPLE_TEXT
    assert len(fake.calls) == 1


def test_different_concept_makes_new_call(tmp_path) -> None:
    client, fake = make_client(tmp_path, texts=["AAA", "BBB"])
    assert client.segment_text(FIXTURE, "nut") == "AAA"
    assert client.segment_text(FIXTURE, "washer") == "BBB"
    assert len(fake.calls) == 2


def test_different_mask_encoding_makes_new_call(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    assert client.segment_text(FIXTURE, "nut") == SAMPLE_TEXT
    assert len(fake.calls) == 1
    other, fake2 = make_client(tmp_path, mask_encoding="lossless")
    assert other.segment_text(FIXTURE, "nut") == SAMPLE_TEXT
    assert len(fake2.calls) == 1
    assert fake2.calls[0]["metadata"] == {"mask_encoding": "lossless"}


def test_empty_output_returns_empty_string_and_is_cached(tmp_path) -> None:
    client, fake = make_client(tmp_path, texts=[_EMPTY])
    assert client.segment_text(FIXTURE, "nut") == ""
    assert client.segment_text(FIXTURE, "nut") == ""
    assert len(fake.calls) == 1
    files = list(Path(str(tmp_path)).glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["text"] == ""


@pytest.mark.parametrize(
    "concept", ["", "   ", "nut, washer", "nut; washer", "nut and washer", "a b c d e"]
)
def test_concept_validation_errors(tmp_path, concept: str) -> None:
    client, fake = make_client(tmp_path)
    with pytest.raises(ValueError):
        client.segment_text(FIXTURE, concept)
    assert len(fake.calls) == 0


def test_gif_raises_value_error(tmp_path) -> None:
    client, fake = make_client(tmp_path)
    gif = tmp_path / "img.gif"
    gif.write_bytes(b"GIF89a")
    with pytest.raises(ValueError):
        client.segment_text(gif, "nut")
    assert len(fake.calls) == 0


def test_missing_api_key_raises_runtime_error(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setattr(sam_client_mod, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="META_API_KEY"):
        SamClient(cache_dir=str(tmp_path), client=None)


def test_bad_mask_encoding_raises_value_error(tmp_path) -> None:
    with pytest.raises(ValueError):
        SamClient(cache_dir=str(tmp_path), client=FakeClient(), mask_encoding="nope")
