# Inspec — rules for Muse Code

You are implementing one scoped task from a brief in `.orchestrator/tasks/`. Another agent plans the
work and reviews your diff, so stay inside the brief.

## Scope
- Change only the files the brief lists. If you need to touch another file, stop and explain why in
  your final message instead of editing it.
- Don't change public interfaces, the check-program schema (`inspec/schema.py`), or prompts in
  `inspec/compiler.py` unless the brief says to.
- No new dependencies unless the brief lists them.

## Code
- Python 3.11, type hints on public functions, small pure functions where possible.
- Read secrets from the environment (`META_API_KEY`); never hard-code or log them.
- Meta Model API base URL: `https://api.meta.ai/v1` (OpenAI-SDK compatible).
- SAM 3.1 takes one short noun phrase per request. Empty output means zero matches, not an error.

## Data
- Never add files under `data/` to git. The dataset is non-commercial and stays out of the public repo.

## Done
- Run the tests named in "Done when" and make them pass before finishing.
- End with a short summary: files changed, tests run and their result, anything left undone.
