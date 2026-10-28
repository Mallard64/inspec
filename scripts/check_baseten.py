"""Check the Baseten setup: list available models, then try one compile.

Usage:
    .venv/bin/python scripts/check_baseten.py            # list models
    .venv/bin/python scripts/check_baseten.py --compile  # also compile the Screw Bag list

Needs BASETEN_API_KEY in .env. Set BASETEN_MODEL to a slug from the list before --compile.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from openai import OpenAI  # noqa: E402

from inspec.llm import PROVIDERS  # noqa: E402


def main() -> int:
    load_dotenv()
    provider = PROVIDERS["baseten"]
    key = os.environ.get(provider.key_env)
    if not key:
        print(f"{provider.key_env} is not set. Add it to .env.")
        return 1
    client = OpenAI(api_key=key, base_url=provider.base_url)
    models = sorted(m.id for m in client.models.list())
    print(f"{len(models)} models on Baseten:")
    for model_id in models:
        marker = "  <- Muse" if "muse" in model_id.lower() else ""
        print(f"  {model_id}{marker}")
    print(f"\nBASETEN_MODEL = {os.environ.get(provider.model_env) or '(not set)'}")

    if "--compile" in sys.argv:
        from inspec.compiler import compile_program
        from inspec.llm import LLM

        result = compile_program("1 long screw, 1 short screw, 2 nuts, 2 washers",
                                 kit_name="screw bag", llm=LLM("baseten"))
        print(f"\nCompiled in {result.attempts} attempt(s); rejected attempts: {result.errors}")
        print(result.value.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
