#!/usr/bin/env bash
# Build a Canopy test-only Mint ISO from a verified original on a Linux build host.
# Requires xorriso, rsync, and an Ubuntu/Mint-compatible ISO with isolinux/grub configs.
set -euo pipefail
if [[ $# -ne 3 ]]; then echo "Usage: $0 SOURCE.iso EXPECTED_SHA256 OUTPUT.iso" >&2; exit 2; fi
source_iso=$(realpath "$1"); expected=$2; output=$(realpath -m "$3")
[[ "$expected" =~ ^[[:xdigit:]]{64}$ ]] || { echo "Invalid SHA256" >&2; exit 2; }
[[ "$source_iso" != "$output" ]] || { echo "Output must differ from source" >&2; exit 2; }
[[ $(sha256sum "$source_iso" | cut -d' ' -f1) == "${expected,,}" ]] || { echo "ISO hash mismatch" >&2; exit 1; }
for cmd in xorriso rsync python3; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/tree"
xorriso -osirrox on -indev "$source_iso" -extract / "$tmp/tree" >/dev/null
# Fail closed: Mint releases differ in installer/boot layout.
[[ -f "$tmp/tree/casper/filesystem.squashfs" ]] || { echo "Unsupported Mint ISO: casper squashfs missing" >&2; exit 1; }
[[ -f "$tmp/tree/boot/grub/grub.cfg" ]] || { echo "Unsupported Mint ISO: GRUB config missing" >&2; exit 1; }
# Do not ship a purported unattended image until bootloader replay and preseed
# integration have been independently tested on Mint 22.3.
echo "PASS: verified ISO extracted; unattended image generation is not yet enabled." >&2
echo "No output ISO written. The bootloader and installer integration are pending." >&2
