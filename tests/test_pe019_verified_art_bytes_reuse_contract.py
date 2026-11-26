"""PE-019 deterministic contract gate for reuse of already-verified art bytes.

The Windows-host offscreen profile showed the approved-art gate plus icon
renderer as a demonstrated startup phase (137 ms + 94 ms medians on the
PE-002 candidate). The fix hands the exact SHA-verified PNG payloads from
verifyExactArtwork() to RoundedDockIconProvider, eliminating eight duplicate
file opens/reads without changing decoded pixels. This test has no timing
threshold and is NOT Mint, NOT visual acceptance and NOT a speedup claim;
screen-reader behavior for this C++ path is NOT_RUN.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "prototype" / "classic" / "main.cpp"
PROVIDER = ROOT / "prototype" / "classic" / "RoundedDockIconProvider.cpp"
HEADER = ROOT / "prototype" / "classic" / "RoundedDockIconProvider.h"
MAX_SOURCE_BYTES = 300_000


def bounded(text, path):
    if not isinstance(text, str):
        raise AssertionError(path + " must be text")
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise AssertionError(path + " exceeds the bounded contract")
    return text


def check_contract(main, provider, header):
    main = bounded(main, "main.cpp")
    provider = bounded(provider, "RoundedDockIconProvider.cpp")
    header = bounded(header, "RoundedDockIconProvider.h")
    for required in (
        "QHash<QString, QByteArray> *verifiedBytes = nullptr",
        "verifiedBytes->insert(relative, bytes)",
        "verifiedBytes && keepBytes",
        "verify(item.toObject(), true)",
        "verifyExactArtwork(requested, !landscapeMode, &error,\n"
        "                                &verifiedArtBytes)",
        "productionPackRoot, &verifiedArtBytes)",
        "verifiedArtBytes.clear();",
        "SHA-256 mismatch, refusing substitute",
        "icons.size() != 8",
    ):
        if required not in main:
            raise AssertionError("main.cpp lost verified-art contract: " + required)
    for required in (
        "QHash<QString, QByteArray> *verifiedBytes = nullptr",
        "QBuffer buffer(&verified.value())",
        "reader.setFormat(\"PNG\")",
        "QImageReader reader(sourcePath)",
        "verified icon cannot be decoded",
    ):
        if required not in header and required not in provider:
            raise AssertionError("provider lost byte-reuse contract: " + required)
    if "QBuffer buffer(&verified.value())" not in provider:
        raise AssertionError("provider no longer decodes the verified payload")
    return True


class VerifiedArtBytesReuseContract(unittest.TestCase):
    def test_compiled_source_reuses_verified_art_bytes(self):
        check_contract(
            MAIN.read_text(encoding="utf-8"),
            PROVIDER.read_text(encoding="utf-8"),
            HEADER.read_text(encoding="utf-8"),
        )

    def test_gate_rejects_duplicate_file_read_variant(self):
        main = MAIN.read_text(encoding="utf-8")
        hostile = main.replace("productionPackRoot, &verifiedArtBytes)",
                               "productionPackRoot);", 1)
        self.assertNotEqual(hostile, main)
        with self.assertRaises(AssertionError):
            check_contract(
                hostile,
                PROVIDER.read_text(encoding="utf-8"),
                HEADER.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
