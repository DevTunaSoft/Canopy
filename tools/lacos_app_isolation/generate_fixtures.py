"""Generate deterministic synthetic fixtures under scratch only.

Usage: python tools/lacos_app_isolation/generate_fixtures.py

No fixture models a real guest, real signature verification or a real launch.
The two hostile fixtures are raw byte sequences, not valid JSON documents.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canopy_features.app_isolation import canonical_bytes  # noqa: E402
from synthetic_fixtures import (  # noqa: E402
    FIXTURE_DIR, sha256_bytes, sha256_file, write_document,
)

BASE = {
    "schema": 1,
    "tool": "lacos_app_isolation",
    "tool_version": "1.0.0",
    "request_id": "req_flatpak_editor",
    "app": {
        "app_id": "org.example.notes",
        "ecosystem": "flatpak_flathub",
        "access_mode": "read_only",
        "permissions": ["audio_output", "documents_read", "network_filtered"],
    },
    "source": {
        "source_id": "flatpak_flathub",
        "provenance": "official-flathub",
        "signature": "gpg",
        "verified": True,
        "scope": "guest-only",
    },
    "host_context": "guest",
    "facts": {
        "signature_verified": True,
        "source_verified": True,
        "upstream_mechanism_available": True,
        "no_duplicate_service": True,
        "core_mutation_absent": True,
        "isolation_enforced": True,
    },
    "guest_class": "SYNTHETIC",
    "deployment_id": "deployment_20261128_0",
    "mechanisms": ["flatpak_portal", "flatpak_sandbox", "systemd_user_scope"],
    "no_paid_tiers": True,
    "no_telemetry": True,
    "no_accounts": True,
    "review_ack": False,
}


def variant(name: str, **changes):
    document = copy.deepcopy(BASE)
    document["request_id"] = name.lower().replace(".json", "")
    for key, value in changes.items():
        if "." in key:
            outer, inner = key.split(".", 1)
            document[outer][inner] = value
        else:
            document[key] = value
    return document


def documents() -> dict:
    podman = variant(
        "F002_valid_podman",
        app={
            "app_id": "com.example.viewer",
            "ecosystem": "rootless_podman_oci",
            "access_mode": "read_only",
            "permissions": ["documents_read", "network_filtered"],
        },
        source={
            "source_id": "rootless_podman_oci",
            "provenance": "verified-image",
            "signature": "cosign",
            "verified": True,
            "scope": "guest-only",
        },
        mechanisms=["rootless_oci", "systemd_user_scope"],
    )
    write_ack = variant(
        "F003_valid_write_ack",
        **{"app.access_mode": "explicit_write",
           "app.permissions": ["documents_read", "downloads_write"],
           "review_ack": True},
    )
    return {
        "F001_valid_flatpak.json": copy.deepcopy(BASE),
        "F002_valid_podman.json": podman,
        "F003_valid_write_ack.json": write_ack,
        "F010_unsigned.json": variant(
            "F010_unsigned", **{"source.signature": "unsigned",
                                "facts.signature_verified": False}),
        "F011_foreign_provenance.json": variant(
            "F011_foreign_provenance", **{"source.provenance": "untrusted-mirror"}),
        "F012_core_mutation.json": variant(
            "F012_core_mutation",
            **{"app.permissions": ["core_mutation", "documents_read"]}),
        "F013_duplicate_sandbox.json": variant(
            "F013_duplicate_sandbox",
            **{"app.permissions": ["duplicate_sandbox", "documents_read"],
               "mechanisms": ["own_sandbox"]}),
        "F014_duplicate_service.json": variant(
            "F014_duplicate_service", **{"facts.no_duplicate_service": False}),
        "F015_paid_tier.json": variant("F015_paid_tier", no_paid_tiers=False),
        "F016_telemetry.json": variant("F016_telemetry", no_telemetry=False),
        "F017_account.json": variant("F017_account", no_accounts=False),
        "F018_host_context.json": variant("F018_host_context", host_context="host"),
        "F019_real_guest.json": variant(
            "F019_real_guest", guest_class="REAL_GUEST_NOT_RUN"),
        "F020_write_without_review.json": variant(
            "F020_write_without_review",
            **{"app.access_mode": "explicit_write",
               "app.permissions": ["downloads_write"]}),
        "F021_unknown_permission.json": variant(
            "F021_unknown_permission",
            **{"app.permissions": ["filesystem_all"]}),
        "F022_wrong_ecosystem_source.json": variant(
            "F022_wrong_ecosystem_source", **{"source.source_id": "apt_deb"}),
        "F023_mech_non_upstream.json": variant(
            "F023_mech_non_upstream", mechanisms=["custom_sandbox"]),
    }


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, document in documents().items():
        write_document(FIXTURE_DIR / name, document)
    # Raw hostile bytes: duplicate JSON key and an oversized integer literal.
    (FIXTURE_DIR / "F024_hostile_duplicate_key.json").write_bytes(
        b'{"a":1,"a":2}\n')
    (FIXTURE_DIR / "F025_huge_integer.json").write_bytes(
        b'{"n":' + b"9" * 5000 + b'}\n')
    # Deterministic, canonical bytes: the valid fixture is exactly its
    # canonical document followed by one LF.
    if (FIXTURE_DIR / "F001_valid_flatpak.json").read_bytes() != (
            canonical_bytes(BASE) + b"\n"):
        raise AssertionError("valid fixture is not canonical")
    lines = []
    for path in sorted(FIXTURE_DIR.iterdir()):
        if path.is_file():
            lines.append("{}  {}\n".format(sha256_file(path), path.name))
    (FIXTURE_DIR / "SHA256SUMS").write_bytes("".join(lines).encode("ascii"))
    print("fixtures={} total_sha256={}".format(
        len(lines), sha256_bytes("".join(lines).encode("ascii"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
