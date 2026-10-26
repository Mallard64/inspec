# Task 01: MVTec LOCO download script

## Goal
Write `scripts/download_loco.sh`, which downloads and extracts MVTec LOCO AD categories into `data/`.

## Context
- The dataset is CC BY-NC-SA 4.0 and must never be committed. `data/` is already gitignored.
- One `.tar.xz` per category. Extracting `<cat>.tar.xz` creates `<cat>/` containing `train/`,
  `test/`, `validation/`, `ground_truth/`, `license.txt`, `readme.txt` and `defects_config.json`.
- Category URLs (official MVTec downloads page, hosted on mydrive.ch):
  - screw_bag: `https://www.mydrive.ch/shares/48241/be5dc3a69c92932644aaac945451d4e7/download/430647115-1646843129/screw_bag.tar.xz`
  - breakfast_box: `https://www.mydrive.ch/shares/163664/72c9e87685863a0e3e81179febe3f530/download/430647124-1646846875/breakfast_box.tar.xz`
  - juice_bottle: `https://www.mydrive.ch/shares/48239/3ad28d48636eada48f0caded666a804a/download/430647100-1646843074/juice_bottle.tar.xz`
  - pushpins: `https://www.mydrive.ch/shares/163665/81ffd38d51732e11027d99cf18c18dd2/download/430647097-1646846662/pushpins.tar.xz`
  - splicing_connectors: `https://www.mydrive.ch/shares/48242/9202635b7b15beba2ceea1674c7deebc/download/430647132-1646843288/splicing_connectors.tar.xz`

## Requirements
- Usage: `scripts/download_loco.sh [--dry-run] [category ...]`. With no categories, default to
  `screw_bag`. `-h`/`--help` prints usage and exits 0.
- Bash, `set -euo pipefail`. Only `curl` and `tar` as external tools.
- Destination is `$DATA_DIR`, defaulting to `<repo root>/data`, with the repo root resolved from the
  script's own location, not the cwd.
- For each category:
  - If `$DATA_DIR/<cat>/train` exists, print `<cat>: already present, skipping` and do nothing else.
  - Otherwise download with `curl -fL --retry 3` to `$DATA_DIR/<cat>.tar.xz.partial`, rename it to
    `<cat>.tar.xz` on success, extract it into `$DATA_DIR`, then delete the archive unless
    `KEEP_ARCHIVE=1`.
  - After extracting, check that `$DATA_DIR/<cat>/train` exists, or exit 1 with a clear message.
- `--dry-run` prints what would happen (including the URL) and touches nothing.
- An unknown category prints an error listing valid categories and exits 2, before any download.
- Print the license once at start:
  `MVTec LOCO AD is CC BY-NC-SA 4.0 (non-commercial). Do not commit data/.`
- Make the script executable.
- Create only `scripts/download_loco.sh`. Do not touch any other file.

## Done when
- `bash -n scripts/download_loco.sh` passes.
- `scripts/download_loco.sh --dry-run` prints the screw_bag URL and exits 0.
- `scripts/download_loco.sh --dry-run nope` exits 2.
- With `DATA_DIR=$(mktemp -d)` and `mkdir -p "$DATA_DIR/screw_bag/train"`, running
  `scripts/download_loco.sh screw_bag` prints the skip message, exits 0 and makes no network call.
- Don't attempt a real download. The sandbox has no general network access.

## Constraints
- No new dependencies. Follow AGENTS.md.
