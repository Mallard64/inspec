#!/usr/bin/env bash
set -euo pipefail

LICENSE_MSG="MVTec LOCO AD is CC BY-NC-SA 4.0 (non-commercial). Do not commit data/."
VALID_CATS="screw_bag breakfast_box juice_bottle pushpins splicing_connectors"

usage() {
  cat <<'EOF'
Usage: scripts/download_loco.sh [--dry-run] [category ...]

Download and extract MVTec LOCO AD categories into data/.

Categories (default: screw_bag):
  screw_bag breakfast_box juice_bottle pushpins splicing_connectors

Options:
  --dry-run   Print what would happen without downloading or writing anything.
  -h, --help  Print this usage and exit 0.

Environment:
  DATA_DIR     Destination directory (default: <repo root>/data).
  KEEP_ARCHIVE=1  Keep the downloaded <cat>.tar.xz after extraction.
EOF
}

url_for() {
  case "$1" in
    screw_bag)
      printf '%s\n' "https://www.mydrive.ch/shares/48241/be5dc3a69c92932644aaac945451d4e7/download/430647115-1646843129/screw_bag.tar.xz"
      ;;
    breakfast_box)
      printf '%s\n' "https://www.mydrive.ch/shares/163664/72c9e87685863a0e3e81179febe3f530/download/430647124-1646846875/breakfast_box.tar.xz"
      ;;
    juice_bottle)
      printf '%s\n' "https://www.mydrive.ch/shares/48239/3ad28d48636eada48f0caded666a804a/download/430647100-1646843074/juice_bottle.tar.xz"
      ;;
    pushpins)
      printf '%s\n' "https://www.mydrive.ch/shares/163665/81ffd38d51732e11027d99cf18c18dd2/download/430647097-1646846662/pushpins.tar.xz"
      ;;
    splicing_connectors)
      printf '%s\n' "https://www.mydrive.ch/shares/48242/9202635b7b15beba2ceea1674c7deebc/download/430647132-1646843288/splicing_connectors.tar.xz"
      ;;
    *)
      return 1
      ;;
  esac
}

is_valid() {
  case "$1" in
    screw_bag|breakfast_box|juice_bottle|pushpins|splicing_connectors)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

DRY_RUN=0
CATS=()

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      printf '%s\n' "$LICENSE_MSG"
      usage
      exit 0
      ;;
    -*)
      printf "error: unknown option '%s'\n" "$arg" >&2
      usage >&2
      exit 2
      ;;
    *)
      CATS+=("$arg")
      ;;
  esac
done

if [ "${#CATS[@]}" -eq 0 ]; then
  CATS=("screw_bag")
fi

for cat in "${CATS[@]}"; do
  if ! is_valid "$cat"; then
    printf "error: unknown category '%s'. Valid categories: %s\n" "$cat" "$VALID_CATS" >&2
    exit 2
  fi
done

printf '%s\n' "$LICENSE_MSG"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${DATA_DIR:-${REPO_ROOT}/data}"

if [ "$DRY_RUN" -eq 1 ]; then
  for cat in "${CATS[@]}"; do
    url="$(url_for "$cat")"
    if [ -d "${DATA_DIR}/${cat}/train" ]; then
      printf '%s: already present, skipping\n' "$cat"
    else
      printf '%s: would download %s to %s/%s.tar.xz and extract into %s\n' \
        "$cat" "$url" "$DATA_DIR" "$cat" "$DATA_DIR"
    fi
  done
  exit 0
fi

mkdir -p "$DATA_DIR"

for cat in "${CATS[@]}"; do
  url="$(url_for "$cat")"
  if [ -d "${DATA_DIR}/${cat}/train" ]; then
    printf '%s: already present, skipping\n' "$cat"
    continue
  fi
  partial="${DATA_DIR}/${cat}.tar.xz.partial"
  archive="${DATA_DIR}/${cat}.tar.xz"
  curl -fL --retry 3 -o "$partial" "$url"
  mv "$partial" "$archive"
  tar -xJf "$archive" -C "$DATA_DIR"
  if [ "${KEEP_ARCHIVE:-0}" != "1" ]; then
    rm -f "$archive"
  fi
  if [ ! -d "${DATA_DIR}/${cat}/train" ]; then
    printf "error: extraction of '%s' did not produce %s/%s/train\n" "$cat" "$DATA_DIR" "$cat" >&2
    exit 1
  fi
done
