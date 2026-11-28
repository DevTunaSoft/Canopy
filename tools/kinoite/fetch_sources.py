#!/usr/bin/env python3
"""Fetch official upstream Kinoite/ostree/Flatpak/systemd/KDE sources into scratch.

The fetch is a real command executed on the host, but it remains STATIC SOURCE
RETRIEVAL, not a Fedora Kinoite native runtime check. Each fetched page is
stored verbatim; a plain-text projection is generated for verifiable quotes.
"""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import pathlib
import subprocess
import sys
import urllib.parse

SOURCES = {
    "fedora_kinoite_guide": "https://docs.fedoraproject.org/en-US/fedora-kinoite/",
    "fedora_getting_started": "https://docs.fedoraproject.org/en-US/fedora-kinoite/getting-started/",
    "fedora_updates_rollbacks": "https://docs.fedoraproject.org/en-US/fedora-kinoite/updates-upgrades-rollbacks/",
    "fedora_technical": "https://docs.fedoraproject.org/en-US/fedora-kinoite/technical-information/",
    "fedora_faq": "https://docs.fedoraproject.org/en-US/fedora-kinoite/faq/",
    "fedora_installation": "https://docs.fedoraproject.org/en-US/fedora-kinoite/installation/",
    "fedora_tips": "https://docs.fedoraproject.org/en-US/fedora-kinoite/tips-and-tricks/",
    "fedora_troubleshooting": "https://docs.fedoraproject.org/en-US/fedora-kinoite/troubleshooting/",
    "fedora_toolbox": "https://docs.fedoraproject.org/en-US/fedora-kinoite/toolbox/",
    "fedora_project_kinoite": "https://fedoraproject.org/atomic-desktops/kinoite/",
    "fedora_download": "https://fedoraproject.org/atomic-desktops/kinoite/download/",
    "fedora_dnf": "https://docs.fedoraproject.org/en-US/quick-docs/dnf/",
    "rpm_ostree_handbook": "https://coreos.github.io/rpm-ostree/administrator-handbook/",
    "ostree_adapting": "https://ostreedev.github.io/ostree/adapting-existing/",
    "flatpak_using": "https://docs.flatpak.org/en/latest/using-flatpak.html",
    "flatpak_sandbox": "https://docs.flatpak.org/en/latest/sandbox-permissions.html",
    "systemd_unit": "https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html",
    "kde_session": "https://docs.kde.org/stable_kf6/en/plasma-desktop/kcontrol/kcmsmserver/",
    "sddm_theming": "https://raw.githubusercontent.com/sddm/sddm/develop/docs/THEMING.md",
    "kde_autostart": "https://docs.kde.org/trunk_kf6/en/plasma-workspace/kcontrol/autostart/index.html",
}

ALLOWED_HOSTS = {
    "docs.fedoraproject.org",
    "fedoraproject.org",
    "coreos.github.io",
    "ostreedev.github.io",
    "docs.flatpak.org",
    "www.freedesktop.org",
    "docs.kde.org",
    "raw.githubusercontent.com",
}


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.depth:
            self.parts.append(data)


def text_of(raw: bytes) -> str:
    parser = _Text()
    parser.feed(raw.decode("utf-8", errors="replace"))
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_one(key: str, url: str, outdir: pathlib.Path) -> dict:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"non-official host for {key}: {host}")
    proc = subprocess.run(
        [
            "curl",
            "--location",
            "--silent",
            "--show-error",
            "--max-time",
            "60",
            "--write-out",
            "\n__FETCH_META__%{http_code} %{url_effective} %{content_type}\n",
            url,
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        return {"key": key, "requested_url": url, "error": proc.stderr.decode("utf-8", "replace").strip()}
    out = proc.stdout.decode("utf-8", errors="replace")
    marker = "\n__FETCH_META__"
    if marker not in out:
        return {"key": key, "requested_url": url, "error": "missing curl metadata marker"}
    body, meta = out.rsplit(marker, 1)
    http_code, final_url, content_type = meta.strip().split(" ", 2)
    # Normalize line endings so stored bytes/digests are identical on every host.
    raw = body.encode("utf-8", errors="replace").replace(b"\r\n", b"\n")
    html_path = outdir / f"{key}.html"
    txt_path = outdir / f"{key}.txt"
    html_path.write_bytes(raw)
    txt_path.write_bytes(text_of(raw).encode("utf-8") + b"\n")
    return {
        "key": key,
        "requested_url": url,
        "final_url": final_url,
        "http_code": int(http_code),
        "content_type": content_type,
        "html_sha256": hashlib.sha256(raw).hexdigest(),
        "text_sha256": hashlib.sha256(txt_path.read_bytes()).hexdigest(),
        "html_path": str(html_path),
        "text_path": str(txt_path),
        "bytes": len(raw),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="scratch/kinoite_validation directory")
    args = ap.parse_args()
    outdir = pathlib.Path(args.out).resolve()
    srcdir = outdir / "sources"
    srcdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, url in SOURCES.items():
        row = fetch_one(key, url, srcdir)
        rows.append(row)
        print(f"{key}: {row.get('http_code', 'ERR')} {row.get('final_url', row.get('error'))}")
    report = {
        "purpose": "STATIC SOURCE RETRIEVAL (not a Fedora Kinoite native runtime check)",
        "sources": rows,
        "ok": all(r.get("http_code") == 200 for r in rows),
    }
    (outdir / "sources.json").write_bytes(
        (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
