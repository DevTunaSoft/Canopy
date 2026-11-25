"""Source contracts for the default v3 five-icon Classic runtime mode.

PR #580 merged the proven v3 renderer correction into
``RoundedDockIconProvider.cpp`` but the integration shell still constructed
that renderer with every review flag false, so Mail/Terminal/Settings were
not corrected at runtime. These tests pin the compiled-shell wiring that
activates the proven mode by default in the approved-art path, together with
its exact rollbacks, the verified-pack path and its in-memory fallback.

These are deterministic source contracts; compiled Qt captures, the three
screenshots and the pixel diff are separate evidence and are not claimed here.
"""
from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
MAIN = CLASSIC / "main.cpp"
PROVIDER = CLASSIC / "RoundedDockIconProvider.cpp"
HEADER = CLASSIC / "RoundedDockIconProvider.h"

# Byte identity of the already-merged PR #580 renderer at integration tip
# a3714ef; this change activates it from main.cpp and must not edit it.
PROVIDER_SHA256_AT_A3714EF = (
    "cd23bd9ce75766c3288f63f5424ed90e0d85e8c8ccc6331a01e6e94ff145e25a"
)
BASE_TIP = "da74616f09d943ccb3c4fb5a5d624e0e6b25bc93"  # integration tip this branch was rebased onto (PR #590 merged)
TARGET_FIVE = ("browser", "mail", "files", "terminal", "settings")
FROZEN_THREE = ("calendar", "photos", "music")

# The flag names are part of the contract: keep the shell selection and this
# model in lockstep by asserting the exact C++ expressions below.
FLAG_MARKERS = (
    "--dock-original-fit",
    "--dock-inner-framing-review",
    "--dock-balanced-fit-review",
    "--dock-optical-balance-review",
    "--dock-clean-edges-review",
    "--dock-five-center-review",
)


def committed_bytes(path: Path) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", "HEAD:" + path.relative_to(ROOT).as_posix()])


def selected_modes(approved_mode: bool, flags: set[str]) -> tuple[bool, bool]:
    """Mirror of the shell's clean-edges / five-center selection expressions."""
    original_fit = "--dock-original-fit" in flags
    inner = "--dock-inner-framing-review" in flags
    balanced = "--dock-balanced-fit-review" in flags
    optical = "--dock-optical-balance-review" in flags
    clean_edges_flag = "--dock-clean-edges-review" in flags
    five_center_flag = "--dock-five-center-review" in flags
    conflicts = sum((inner, balanced, optical, clean_edges_flag, five_center_flag))
    if conflicts > 1 or (original_fit and conflicts > 0):
        return (False, False)  # shell rejects conflicting modes before rendering
    clean = (approved_mode and not original_fit and not inner and not balanced
             and not optical)
    five = clean and (five_center_flag or not clean_edges_flag)
    return (clean, five)


class ClassicFiveIconRuntimeModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.provider = PROVIDER.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")

    def test_merged_v3_renderer_is_activated_not_modified(self):
        provider_bytes = committed_bytes(PROVIDER).replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(provider_bytes).hexdigest(),
                         PROVIDER_SHA256_AT_A3714EF)
        self.assertIn('constexpr auto kPackRenderer = "canopy-five-qt-v3";',
                      self.provider)
        self.assertIn("renderFiveAtDensity", self.provider)
        self.assertIn("kFiveSourceEdgeTrim", self.provider)

    def test_default_approved_runtime_selects_the_proven_five_icon_mode(self):
        cpp = self.main
        for marker in (
                "const bool dockCleanEdgesReviewModeSelected =",
                "approvedMode && !dockOriginalFitMode &&",
                "!dockInnerReviewMode && !dockBalancedFitReviewMode &&",
                "!explicitOpticalBalanceReview;",
                "const bool dockFiveCenterModeSelected =",
                "dockCleanEdgesReviewModeSelected &&",
                "(dockFiveCenterReviewMode || !dockCleanEdgesReviewMode);",
                "approvedRoot, terminalCandidatePath, false, &roundedError,",
                "dockCleanEdgesReviewModeSelected, dockFiveCenterModeSelected,",
                "productionPackRoot);",
                "DOCK_FIVE_CENTER_ACTIVE: Browser, Mail, Files, Terminal, Settings",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        # The old all-false construction would leave the correction dormant.
        self.assertNotIn("approvedRoot, terminalCandidatePath, false, &roundedError);",
                         cpp)
        # Mirror the pinned expressions: the default approved-art launch and
        # the explicit five-center flag both select the corrected composition.
        for flags in (set(), {"--dock-five-center-review"}):
            with self.subTest(flags=sorted(flags)):
                self.assertEqual(selected_modes(True, flags), (True, True))
        self.assertEqual(selected_modes(False, set()), (False, False))

    def test_exact_rollbacks_and_fail_closed_flags_are_preserved(self):
        cpp = self.main
        for flag in FLAG_MARKERS:
            with self.subTest(flag=flag):
                self.assertIn('args.contains(QStringLiteral("%s"))' % flag, cpp)
        for marker in (
                "if (iconReviewFlags > 1)",
                "if (dockOriginalFitMode && iconReviewFlags > 0)",
                "if (dockInnerReviewMode && !approvedMode)",
                "if (dockBalancedFitReviewMode && !approvedMode)",
                "if (explicitOpticalBalanceReview && !approvedMode)",
                "if (dockOriginalFitMode && !approvedMode)",
                "if (dockCleanEdgesReviewMode && !approvedMode)",
                "if (dockFiveCenterReviewMode && !approvedMode)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        # Previous clean-matte appearance: exact rollback without five-center.
        self.assertEqual(selected_modes(True, {"--dock-clean-edges-review"}),
                         (True, False))
        # Original full fit and the other reviewed experiments stay available.
        self.assertEqual(selected_modes(True, {"--dock-original-fit"}),
                         (False, False))
        self.assertEqual(selected_modes(True, {"--dock-optical-balance-review"}),
                         (False, False))
        self.assertEqual(selected_modes(True, {"--dock-inner-framing-review"}),
                         (False, False))
        self.assertEqual(selected_modes(True, {"--dock-balanced-fit-review"}),
                         (False, False))
        self.assertEqual(selected_modes(
            True, {"--dock-clean-edges-review", "--dock-five-center-review"}),
            (False, False))

    def test_sha_verified_pack_and_in_memory_fallback_are_both_retained(self):
        cpp = self.main
        for marker in (
                "QCoreApplication::applicationDirPath() + QStringLiteral(\"/production-icons\")",
                '"../share/canopy/classic/icons"',
                '"--require-five-production-icons"',
                "!dockFiveCenterModeSelected || !roundedIcons->productionPackVerified()",
                "FIVE_PRODUCTION_PACK_VERIFIED: exactly five SHA-verified original-derived icons",
                "FIVE_PRODUCTION_PACK_FALLBACK: exact original-derived Qt renderer",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        provider = self.provider
        for marker in (
                "if (fiveOnlyCenterReviewMode && !productionPackRoot.isEmpty())",
                "m_productionPackValid = true;",
                "renderFiveAtDensity(original, id, 1, error)",
                'manifest.insert(QStringLiteral("renderer"), QLatin1String(kPackRenderer));',
                "spec.value(QStringLiteral(\"renderer\")).toString() ==",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, provider)
        # The verified pack is read only after its 15 PNG hashes match.
        self.assertLess(provider.index("m_productionPackValid = true;"),
                        provider.index("QImageReader packReader"))

    def test_only_five_ids_are_targeted_and_three_stay_frozen(self):
        provider = self.provider
        self.assertIn("const QStringList kFiveProductionIds = {", provider)
        self.assertIn("const QHash<QString, QPointF> kFiveDockCenterOffsets = {",
                      provider)
        for block_name in ("kFiveProductionIds", "kFiveDockCenterOffsets"):
            block = provider.split(block_name + " = {", 1)[1].split("};", 1)[0]
            for icon in TARGET_FIVE:
                with self.subTest(block=block_name, icon=icon):
                    self.assertIn('QStringLiteral("%s")' % icon, block)
            for icon in FROZEN_THREE:
                with self.subTest(block=block_name, frozen=icon):
                    self.assertNotIn('QStringLiteral("%s")' % icon, block)
        # The WS2 correction touches only Mail/Terminal/Settings edge trims;
        # Browser and Files keep their prior verified boundaries.
        trim = provider.split("kFiveSourceEdgeTrim = {", 1)[1].split("};", 1)[0]
        for icon in ("mail", "terminal", "settings"):
            self.assertIn('QStringLiteral("%s")' % icon, trim)
        for icon in FROZEN_THREE:
            self.assertNotIn('QStringLiteral("%s")' % icon, trim)

    def test_pack_export_is_offline_only_and_sha_verified(self):
        cpp = self.main
        for marker in (
                '"--export-five-production-icons"',
                "RoundedDockIconProvider productionSource(",
                "approvedRoot, QString(), false, &error, false, false, true, true);",
                "exportFiveProductionPack(",
                "FIVE_PRODUCTION_EXPORT_PASS: five verified original-master icons",
                "at 192/384/576 pixels; Calendar/Photos/Music excluded",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, cpp)
        export_if = cpp.split('args.indexOf(QStringLiteral("--export-five-production-icons"))', 1)[1]
        export_body = export_if.split("QQmlApplicationEngine engine;", 1)[0]
        self.assertIn("return 0;", export_body)  # never continues into the UI
        self.assertIn("!approvedMode || !terminalCandidatePath.isEmpty()", export_body)

    def test_no_quick_controls_wiring_is_duplicated_from_pr590(self):
        # PR #590 merged into the integration tip this branch was rebased
        # onto. Its wiring is legitimately present; exact occurrence counts
        # (measured at that base) prove this change neither re-adds nor
        # duplicates any of it. No git history is needed, so this also runs
        # in Foundation CI's shallow checkout.
        expected = {
            "verifyQuickControlsScene": 3,
            "canopyQuickControlsOverlay": 1,
            "QUICK_CONTROLS_FIXTURE_PASS": 1,
            "QShortcut": 4,
        }
        for marker, count in expected.items():
            with self.subTest(marker=marker):
                self.assertEqual(self.main.count(marker), count)

    def test_provider_constructor_still_requires_companion_flags(self):
        for marker in (
                "fiveOnlyCenterReviewMode && !cleanSourceEdgesReviewMode",
                "five-icon centering requires the existing clean-matte renderer",
                "conflicting icon framing experiments",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.provider)
        self.assertIn("bool fiveOnlyCenterReviewMode = false", self.header)
        self.assertIn("bool cleanSourceEdgesReviewMode = false", self.header)


if __name__ == "__main__":
    unittest.main()
