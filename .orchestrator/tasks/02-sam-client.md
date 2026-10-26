# Task 02: SAM 3.1 client with disk cache

## Goal
Write `inspec/sam_client.py`, which calls SAM 3.1 for one (image, concept) pair and caches the raw
response text on disk, so a repeated call never hits the API again.

## Context
- The Meta Model API is OpenAI-SDK compatible. Base URL `https://api.meta.ai/v1`, key in env var
  `META_API_KEY` (loaded from `.env` via `python-dotenv`).
- Verified request shape (see `docs/sam-output-format.md`):

  ```python
  client.responses.create(
      model="sam-3.1",
      metadata={"mask_encoding": "one_bit"},
      input=[{"role": "user", "content": [
          {"type": "input_text", "text": "nut"},
          {"type": "input_image", "image_url": "data:image/png;base64,<b64>"},
      ]}],
  )
  ```
- The result text is `response.output[0].content[0].text`. If `output` is empty or the first item
  has no content, treat the result as `""`. An empty string means zero matches and is a valid
  result to cache, not an error.
- Parsing the text is a separate module (task 03). This client returns raw text only.

## Interface (implement exactly)

```python
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "sam-3.1"

class SamClient:
    def __init__(
        self,
        cache_dir: str | Path = ".cache/sam",
        *,
        client: Any | None = None,     # injected OpenAI-like client; tests pass a fake
        model: str = DEFAULT_MODEL,
        mask_encoding: str = "one_bit",  # "one_bit" or "lossless"; else ValueError
    ) -> None: ...

    def segment_text(self, image_path: str | Path, concept: str) -> str:
        """Raw SAM output text for one concept in one image. Cached."""
```

## Requirements
- If `client` is None, call `load_dotenv()`, read `META_API_KEY` and build
  `openai.OpenAI(api_key=..., base_url=DEFAULT_BASE_URL)`. If the key is missing, raise
  `RuntimeError` saying to set `META_API_KEY` in `.env`. Never log or print the key.
- Concept validation: strip whitespace, then raise `ValueError` if the concept is empty, has more
  than 4 words, or contains `,` `;` or the word `and`. SAM takes one short noun phrase per request.
- Image: read bytes; MIME type from suffix (`.png` → `image/png`, `.jpg`/`.jpeg` → `image/jpeg`),
  otherwise `ValueError`. Send it as a base64 data URL.
- Cache key: sha256 of `f"{model}\n{mask_encoding}\n{concept.lower()}\n"` followed by the sha256 hex
  of the image bytes. Same image content at a different path gives a cache hit.
- Cache file `<cache_dir>/<key>.json`:
  `{"model", "mask_encoding", "concept", "image_sha256", "text"}`. Create `cache_dir` as needed. Write
  atomically: write to a temp file in the same directory, then `os.replace`.
- On a cache hit, return the stored `text` without calling the client.
- Let API errors propagate. The OpenAI SDK already retries transient failures.
- Create `inspec/sam_client.py` and `tests/test_sam_client.py`. Do not touch any other file.

## Tests (`tests/test_sam_client.py`, no network)
Use a fake client object whose `responses.create(**kwargs)` records kwargs and returns an object with
`.output[0].content[0].text`. Use `tmp_path` for the cache and the image fixture
`tests/fixtures/sam/circles.png`. Cover:
- The first call sends `model="sam-3.1"`, `metadata={"mask_encoding": "one_bit"}`, an `input_text`
  with the concept, and an `input_image` whose URL starts with `data:image/png;base64,`.
- Calling twice with the same image and concept makes one API call and returns the same text.
- A new `SamClient` on the same `cache_dir` hits the cache (no API call).
- The same bytes copied to a different filename hit the cache.
- A different concept, or a different `mask_encoding`, makes a new call.
- An empty `output` list returns `""` and is cached.
- Concept validation errors: `""`, `"nut, washer"`, `"nut and washer"`, `"a b c d e"`.
- `.gif` raises `ValueError`. A missing `META_API_KEY` (monkeypatch env, `client=None`) raises
  `RuntimeError`. Patch `load_dotenv` so a real `.env` isn't read.

## Done when
- `/Users/bigdum/inspec/.venv/bin/python -m pytest tests/test_sam_client.py -q` passes, run from the
  worktree root. Dependencies are already installed in that venv.

## Constraints
- Python 3.11, type hints on public functions. Use only `openai`, `python-dotenv` and the stdlib.
  Follow AGENTS.md.
