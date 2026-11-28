"""Bounded eight-initial-Shell-Pack inventory contract (metadata only).

The eight first-party identities, their free-by-construction bindings, the
one-host shared-core ownership and the synthetic switch ledger are checked
without loading QML or touching a desktop session.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from canopy_features.settings import shell_pack_manifest as m
from tools.check_shell_pack import (
    CAPABILITIES,
    INITIAL_CATALOG,
    PackValidationError,
    validate_catalog,
    validate_pack,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tools" / "shell_packs"
BASE = "ec910d7a"
BANNED_MANIFEST = (
    "paid", "purchase", "subscription", "activation", "unlock", "telemetry",
    "http://", "https://", "dbus", "daemon",
)
QML_HOOKS = (
    "Timer", "NetworkRequest", "createQmlObject", "Process", "DBus",
    "Qt.createComponent", "WebSocket",
)


def definition(**overrides):
    values = {
        "builtin_id": m.MODERN_BUILTIN_ID,
        "manifest_id": m.MODERN_MANIFEST_ID,
        "name": "Modern",
        "capabilities": frozenset({"app-launcher"}),
        "entrypoint": "ui/Main.qml",
        "source": "tools/shell_packs/modern",
    }
    values.update(overrides)
    return m.PackDefinition(**values)


class InitialShellPackCatalogTests(unittest.TestCase):
    def test_initial_eight_identities_are_bounded_and_unique(self):
        self.assertEqual(len(m.INITIAL_PACK_IDS), 8)
        self.assertEqual(len(set(m.INITIAL_PACK_IDS)), 8)
        self.assertEqual(m.MAX_DEFINITIONS, 8)
        self.assertEqual(m.BUILTIN_IDS, frozenset(m.INITIAL_PACK_IDS))
        self.assertEqual(len(m.CATALOG_IDS), 7)
        self.assertEqual(tuple(m.CATALOG_IDS), m.INITIAL_PACK_IDS[1:])
        self.assertEqual(m.CATALOG_IDS[m.MODERN_BUILTIN_ID], m.MODERN_MANIFEST_ID)
        self.assertEqual(set(INITIAL_CATALOG.values()), set(m.CATALOG_IDS.values()))

    def test_inventory_snapshot_contains_all_eight(self):
        snap = m.inventory_snapshot()
        self.assertEqual(snap.problems, ())
        self.assertEqual(snap.checked_manifests, 7)
        self.assertEqual(
            tuple(item.builtin_id for item in snap.definitions),
            m.INITIAL_PACK_IDS,
        )
        classic = snap.get(m.CLASSIC_BUILTIN_ID)
        self.assertIsNotNone(classic)
        self.assertEqual(classic.manifest_id, m.CLASSIC_BUILTIN_ID)
        self.assertEqual(classic.source, "built-in:approved-classic")
        self.assertEqual(classic.capabilities, frozenset())
        for builtin_id, manifest_id in m.CATALOG_IDS.items():
            item = snap.get(builtin_id)
            self.assertIsNotNone(item)
            self.assertEqual(item.manifest_id, manifest_id)
            self.assertTrue(item.capabilities)
            self.assertTrue(item.capabilities <= CAPABILITIES)
            self.assertEqual(item.source, m.PACK_DIRS[builtin_id].as_posix())
        self.assertEqual(snap.as_dict()["initial_pack_ids"], list(m.INITIAL_PACK_IDS))

    def test_shared_core_owns_every_service_once(self):
        services = m.shared_core_snapshot()
        self.assertEqual(len(services), len(m.SHARED_CORE_SERVICES))
        self.assertTrue(all(value == "host-owned" for value in services.values()))
        self.assertEqual(m.PACK_OWNED_SERVICES, frozenset())
        snap = m.inventory_snapshot()
        self.assertTrue(all(item.owned_services == frozenset()
                            for item in snap.definitions))

    def test_free_by_construction_fails_closed(self):
        self.assertEqual(m.PAID_TIERS, frozenset())
        self.assertFalse(m.ACTIVATION_REQUIRED)
        self.assertEqual(m.TELEMETRY_ENDPOINTS, frozenset())
        self.assertTrue(all(item.free for item in m.inventory_snapshot().definitions))
        with self.assertRaises(m.ShellPackManifestError):
            definition(tier="paid")
        with self.assertRaises(m.ShellPackManifestError):
            definition(owned_services=frozenset({"compositor-session"}))
        with self.assertRaises(m.ShellPackManifestError):
            definition(builtin_id="org.canopy.unlisted")

    def test_catalog_checker_accepts_seven_expected_manifests(self):
        descriptors = validate_catalog(CATALOG)
        self.assertEqual(
            [item["id"] for item in descriptors],
            [INITIAL_CATALOG[name] for name in sorted(INITIAL_CATALOG)],
        )
        cli = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_shell_pack.py"),
             "--catalog", str(CATALOG)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn("SHELL_PACK_CATALOG_PASS: 7", cli.stdout)
        for name in INITIAL_CATALOG:
            self.assertEqual(validate_pack(CATALOG / name)["id"], INITIAL_CATALOG[name])

    def test_catalog_checker_rejects_missing_or_extra_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "packs"
            shutil.copytree(CATALOG, root)
            self.assertEqual(len(validate_catalog(root)), 7)
            shutil.rmtree(root / "lite")
            with self.assertRaisesRegex(PackValidationError, "unexpected catalog contents"):
                validate_catalog(root)
            shutil.copytree(root / "modern", root / "lite")
            with self.assertRaises(PackValidationError):
                validate_catalog(root)  # binding mismatch for io.canopy.modern
            shutil.copytree(CATALOG / "lite", root / "lite", dirs_exist_ok=True)
            (root / "future").mkdir()
            with self.assertRaisesRegex(PackValidationError, "unexpected catalog contents"):
                validate_catalog(root)

    def test_manifests_and_qml_have_no_paid_or_runtime_hooks(self):
        for name in INITIAL_CATALOG:
            manifest_text = (CATALOG / name / "manifest.json").read_text(encoding="utf-8")
            hits = [token for token in BANNED_MANIFEST if token in manifest_text.lower()]
            self.assertEqual(hits, [], name)
            descriptor = validate_pack(CATALOG / name)
            self.assertEqual(descriptor["permissions"], [])
            self.assertEqual(descriptor["switch_strategy"], "same-session")
            qml = (CATALOG / name / "ui" / "Main.qml").read_text(encoding="utf-8")
            code = "\n".join(
                line for line in qml.splitlines()
                if not line.lstrip().startswith("//")
            )
            for token in QML_HOOKS:
                self.assertNotIn(token, code, name)

    def test_all_eight_pairs_transition_and_roll_back(self):
        snap = m.inventory_snapshot()
        pairs = 0
        for source in m.INITIAL_PACK_IDS:
            for target in m.INITIAL_PACK_IDS:
                if source == target:
                    continue
                prepared = m.prepare_switch(snap, source, target)
                self.assertEqual(prepared.phase, "PREPARED")
                applied = m.apply_switch(prepared)
                self.assertEqual(applied.active_id, target)
                committed = m.verify_switch(applied, True)
                self.assertEqual(committed.committed_id, target)
                released = m.release_inactive(committed)
                self.assertEqual(released.phase, "RELEASED")
                self.assertEqual(released.active_id, target)
                failed = m.verify_switch(
                    m.apply_switch(m.prepare_switch(snap, source, target)), False
                )
                self.assertEqual(failed.phase, "ROLLED_BACK")
                self.assertEqual(failed.active_id, source)
                self.assertEqual(failed.committed_id, source)
                self.assertTrue(failed.as_dict()["real_runtime_verified"] is False)
                pairs += 1
        self.assertEqual(pairs, 56)

    def test_hundred_synthetic_round_trips(self):
        snap = m.inventory_snapshot()
        result = m.run_synthetic_round_trips(snap)
        self.assertEqual(result["round_trips"], 100)
        self.assertEqual(result["transitions"], 300)
        self.assertEqual(result["pack_ids"], list(m.INITIAL_PACK_IDS))
        self.assertEqual(len(result["sequence_sha256"]), 64)
        self.assertFalse(result["real_runtime_verified"])
        with self.assertRaises(m.ShellPackManifestError):
            m.run_synthetic_round_trips(snap, 101)
        with self.assertRaises(m.ShellPackManifestError):
            m.run_synthetic_round_trips(snap, 0)

    def test_unidentifiable_or_illegal_switch_rejected(self):
        snap = m.inventory_snapshot()
        cases = (
            lambda: m.prepare_switch(snap, "org.canopy.unlisted", m.MODERN_BUILTIN_ID),
            lambda: m.prepare_switch(snap, m.CLASSIC_BUILTIN_ID, "../escape"),
            lambda: m.verify_switch(
                m.apply_switch(m.prepare_switch(
                    snap, m.CLASSIC_BUILTIN_ID, m.HERITAGE_BUILTIN_ID)), "yes"
            ),
            lambda: m.rollback_switch(m.verify_switch(
                m.apply_switch(m.prepare_switch(
                    snap, m.CLASSIC_BUILTIN_ID, m.MODERN_BUILTIN_ID)), True)),
            lambda: m.load_pack_definition(m.CLASSIC_BUILTIN_ID),
            lambda: m.load_pack_definition("org.canopy.unlisted"),
        )
        for case in cases:
            with self.assertRaises(m.ShellPackManifestError):
                case()

    def test_classic_identity_binding_unchanged(self):
        classic = m.inventory_snapshot().get(m.CLASSIC_BUILTIN_ID)
        self.assertIsNotNone(classic)
        self.assertEqual(classic.source, "built-in:approved-classic")
        self.assertEqual(classic.capabilities, frozenset())
        self.assertNotIn(m.CLASSIC_BUILTIN_ID, m.CATALOG_IDS)
        self.assertNotIn("classic", INITIAL_CATALOG)
        self.assertFalse((CATALOG / "classic").exists())
        for name in INITIAL_CATALOG:
            for rel in ("manifest.json", "ui/Main.qml", "README.md"):
                path = CATALOG / name / rel
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8").lower()
                for token in ("alpine", "wallpaper", "tux",
                              "prototype/classic", "persisted_preferences"):
                    self.assertNotIn(token, text, (name, rel, token))
        # Historical diff is supporting evidence only: shallow CI checkouts
        # may not carry the base commit, so absence degrades to source checks.
        probe = subprocess.run(
            ["git", "cat-file", "-e", BASE + "^{commit}"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        if probe.returncode == 0:
            changed = subprocess.run(
                ["git", "diff", "--name-only", BASE, "HEAD", "--",
                 "prototype/classic", "docs/CLASSIC*",
                 "canopy_features/settings/persisted_preferences.py"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(changed.returncode, 0, changed.stderr)
            self.assertEqual(changed.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
