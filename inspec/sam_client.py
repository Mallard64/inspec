"""SAM 3.1 client with on-disk caching of raw response text."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "sam-3.1"

_SUFFIX_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class SamClient:
    def __init__(
        self,
        cache_dir: str | Path = ".cache/sam",
        *,
        client: Any | None = None,
        model: str = DEFAULT_MODEL,
        mask_encoding: str = "one_bit",
    ) -> None:
        if mask_encoding not in ("one_bit", "lossless"):
            raise ValueError(
                f"mask_encoding must be 'one_bit' or 'lossless', got {mask_encoding!r}"
            )
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.mask_encoding = mask_encoding
        if client is not None:
            self._client = client
        else:
            load_dotenv()
            api_key = os.environ.get("META_API_KEY")
            if not api_key:
                raise RuntimeError("Set META_API_KEY in .env")
            import openai

            self._client = openai.OpenAI(api_key=api_key, base_url=DEFAULT_BASE_URL)

    def segment_text(self, image_path: str | Path, concept: str) -> str:
        """Raw SAM output text for one concept in one image. Cached."""
        validated = self._validate_concept(concept)
        path = Path(image_path)
        image_bytes = path.read_bytes()
        mime = self._mime_for_suffix(path.suffix)
        image_sha = hashlib.sha256(image_bytes).hexdigest()
        key = hashlib.sha256(
            (f"{self.model}\n{self.mask_encoding}\n{validated.lower()}\n" + image_sha).encode()
        ).hexdigest()
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.is_file():
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)["text"]

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        response = self._client.responses.create(
            model=self.model,
            metadata={"mask_encoding": self.mask_encoding},
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": validated},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )
        text = self._extract_text(response)
        payload = {
            "model": self.model,
            "mask_encoding": self.mask_encoding,
            "concept": validated.lower(),
            "image_sha256": image_sha,
            "text": text,
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.cache_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_name, cache_file)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return text

    @staticmethod
    def _validate_concept(concept: str) -> str:
        stripped = concept.strip()
        if not stripped:
            raise ValueError("concept must not be empty")
        if len(stripped.split()) > 4:
            raise ValueError(f"concept must be at most 4 words, got {concept!r}")
        if "," in stripped or ";" in stripped:
            raise ValueError(f"concept must not contain ',' or ';', got {concept!r}")
        if "and" in stripped.split():
            raise ValueError(f"concept must not contain the word 'and', got {concept!r}")
        return stripped

    @staticmethod
    def _mime_for_suffix(suffix: str) -> str:
        mime = _SUFFIX_TO_MIME.get(suffix.lower())
        if mime is None:
            raise ValueError(f"unsupported image suffix: {suffix!r}")
        return mime

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            output = response.output
        except AttributeError:
            return ""
        if not output:
            return ""
        first = output[0]
        content = getattr(first, "content", None)
        if not content:
            return ""
        text = getattr(content[0], "text", None)
        if text is None:
            return ""
        return text
