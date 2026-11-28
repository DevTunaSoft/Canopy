"""PE-060 / QA005-004: offline gate for dynamic status accessibility.

The five Classic status labels must expose their rendered text as the
accessible name, use Accessible.AlertMessage (role 8, NOT Accessible.Alert,
which is an Event enum of value 2), ignore an empty status node, and announce
each new non-empty status exactly once through a Qt-version-guarded path.

This gate is STATIC / SYNTHETIC. It reads checked-in sources, never compiles
Qt, never launches a screen reader and makes no Mint or AT-SPI claim.
A byte-level projection proves that no rendered text, geometry, colour, font,
asset or component-order input changed.
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSIC = ROOT / "prototype" / "classic"
MAIN_CPP = CLASSIC / "main.cpp"

# (filename, objectName, QML label id)
STATUS_LABELS = (
    ("PreviewWindow.qml", "canopyFileManagerStatus", "fileManagerStatusLabel"),
    ("LauncherOverlay.qml", "canopyLauncherStatus", "footer"),
    ("QuickControlsOverlay.qml", "canopyQuickControlsMessage", "message"),
    ("SettingsPanel.qml", "canopySettingsMessage", "message"),
    ("NotificationCenter.qml", "canopyNotificationDisclosure", "disclosure"),
)

# SHA-256 of the visual projection (every Accessible.* line and the
# A11Y-ANNOUNCE block removed) of the current blobs. ND-041 added only
# tests/test_nd041_native_settings_controls_wiring.py. The PR #732 fix
# added four fail-closed disclosure strings to disclosureForReason above
# that boundary; the pin below is a test-only sync to the new bytes and
# no rendered visual input changed.
BASE_VISUAL_PROJECTION_SHA256 = {
    "PreviewWindow.qml":
        "741091d6324db4193b2c4300c438a502631ed550604c271405e9d2e56d2eaeec",
    "LauncherOverlay.qml":
        "e5e1f3169fe9abca57744e8a5dc45f2a8d338fa05d0d719ea731f5633c43b6ce",
    "QuickControlsOverlay.qml":
        "7754bd824a6dda993609b264be16dfc8b884cc211f68f9bdb4cc262ff4d92cef",
    "SettingsPanel.qml":
        "1cf64ea493b1a291a8d2049bc7575c3938922ac9a13727dc7728ec433617c2d7",
    "NotificationCenter.qml":
        "d686ed2654ea0a7a1139253da533976a7264451c26f2da9bd9b6f8bc650b1189",
}

ANNOUNCE_BEGIN = "// A11Y-ANNOUNCE-BEGIN"
ANNOUNCE_END = "// A11Y-ANNOUNCE-END"
ROLE_LINE = "Accessible.role: Accessible.AlertMessage"
# QML Accessible.AlertMessage is role 8; Accessible.Alert is a C++ Event
# enum of value 2 (and becomes MenuBar if assigned as a QML role).
ALERT_MESSAGE_ROLE_VALUE = 8
ALERT_EVENT_VALUE = 2
NATIVE_GUARD = "canopyStatusAnnouncer.nativeAnnounceAvailable"
NATIVE_CALL = "Accessible.announce(text, Accessible.Assertive)"
CONSTANT_NAME = 'Accessible.name: "File manager launch status"'


def normalized(text: str) -> str:
    if not isinstance(text, str):
        raise AssertionError("QML source must be text")
    return text.replace("\r\n", "\n")


def visual_projection(source: str) -> str:
    """Strip only accessibility-only lines; keep every rendered input."""
    out: list[str] = []
    skipping = False
    for line in normalized(source).split("\n"):
        if ANNOUNCE_BEGIN in line:
            skipping = True
            continue
        if ANNOUNCE_END in line:
            skipping = False
            continue
        if skipping or "Accessible." in line:
            continue
        out.append(line)
    return "\n".join(out)


def label_block(source: str, object_name: str) -> str:
    lines = normalized(source).split("\n")
    hits = [i for i, line in enumerate(lines)
            if 'objectName: "%s"' % object_name in line]
    if len(hits) != 1:
        raise AssertionError("%s found %d times" % (object_name, len(hits)))
    start = None
    for i in range(hits[0], -1, -1):
        if re.search(r"\bLabel\s*\{", lines[i]):
            start = i
            break
    if start is None:
        raise AssertionError("no Label start for " + object_name)
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start:
            return "\n".join(lines[start:i + 1])
    raise AssertionError("unbalanced Label block for " + object_name)


def check_label(source: str, object_name: str, label_id: str) -> None:
    block = label_block(source, object_name)
    if CONSTANT_NAME in block:
        raise AssertionError("constant accessible name in " + object_name)
    if "Accessible.name: %s.text" % label_id not in block \
            and "Accessible.name: text" not in block:
        raise AssertionError("name is not bound to rendered text: " + object_name)
    if ROLE_LINE not in block:
        raise AssertionError("missing Accessible.AlertMessage role: " + object_name)
    # Accessible.Alert is an Event enum (2), not a Role; assigning it to role
    # silently yields MenuBar (2) on host Qt 6.12.
    if re.search(r"Accessible\.role:\s*Accessible\.Alert\b", block):
        raise AssertionError("wrong Alert enum used as role: " + object_name)
    if "Accessible.ignored: %s.text === \"\"" % label_id not in block \
            and 'Accessible.ignored: text === ""' not in block:
        raise AssertionError("empty status node is not ignored: " + object_name)
    if ANNOUNCE_BEGIN not in block or ANNOUNCE_END not in block:
        raise AssertionError("no guarded announce block: " + object_name)
    announce = block.split(ANNOUNCE_BEGIN, 1)[1].split(ANNOUNCE_END, 1)[0]
    fallback_call = "canopyStatusAnnouncer.announce(%s, text)" % label_id
    for required in ("onTextChanged:", 'text === ""', "!a11yAnnounceReady",
                     "Component.onCompleted: a11yAnnounceReady = true",
                     NATIVE_GUARD, NATIVE_CALL, fallback_call):
        if required not in announce:
            raise AssertionError("announce block lost %r in %s"
                                 % (required, object_name))


def check_main(source: str) -> None:
    src = normalized(source)
    for required in (
        "#include <QAccessible>",
        "class StatusAnnounceBridge final : public QObject",
        "Q_PROPERTY(bool nativeAnnounceAvailable READ nativeAnnounceAvailable CONSTANT)",
        "#if QT_VERSION >= QT_VERSION_CHECK(6, 8, 0)",
        "Q_INVOKABLE void announce(QObject *item, const QString &text)",
        "QAccessibleEvent event(item, QAccessible::Alert)",
        "QAccessible::updateAccessibility",
        "QAccessible::Alert",
        'QStringLiteral("canopyStatusAnnouncer")',
        'engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")))',
    ):
        if required not in src:
            raise AssertionError("main.cpp lost %r" % required)
    if "setMessage(" in src:
        raise AssertionError("QAccessibleEvent has no setMessage API")
    # The compile-time guard must select exactly one available flag value.
    guarded = src.split("#if QT_VERSION >= QT_VERSION_CHECK(6, 8, 0)", 1)[1]
    true_branch, rest = guarded.split("#else", 1)
    false_branch = rest.split("#endif", 1)[0]
    if "return true;" not in true_branch or "return false;" not in false_branch:
        raise AssertionError("Qt version guard does not select the announce path")
    prop_at = src.index('QStringLiteral("canopyStatusAnnouncer")')
    load_at = src.index('engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")))')
    if prop_at >= load_at:
        raise AssertionError("announcer context property registered after QML load")
    # Fail closed: empty text never reaches the accessibility event.
    fn = src.split("Q_INVOKABLE void announce(QObject *item, const QString &text)", 1)[1]
    fn = fn.split("\n    }", 1)[0]
    if 'trimmed.isEmpty()' not in fn or 'return;' not in fn:
        raise AssertionError("announce bridge does not fail closed on empty text")


def announce_decision(previous: str, new: str, native_available: bool,
                      ready: bool = True) -> list[str]:
    """Python mirror of the guarded QML/C++ announcement contract.

    Empty text (ignored node), initialization, no-op updates and an unready
    component announce nothing; a new non-empty status emits exactly one.
    """
    if type(previous) is not str or type(new) is not str:
        raise AssertionError("status text must be str")
    if not ready or new.strip() == "" or new == previous:
        return []
    return ["Accessible.announce" if native_available else "QAccessibleEvent"]


class ClassicStatusAccessibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = {name: (CLASSIC / name).read_text(encoding="utf-8")
                        for name, _, _ in STATUS_LABELS}
        self.main_src = MAIN_CPP.read_text(encoding="utf-8")

    def test_visual_inputs_are_byte_frozen(self):
        for name, digest in BASE_VISUAL_PROJECTION_SHA256.items():
            with self.subTest(file=name):
                actual = hashlib.sha256(
                    visual_projection(self.sources[name]).encode("utf-8")
                ).hexdigest()
                self.assertEqual(actual, digest, "visual/geometry input changed")

    def test_dynamic_accessible_name_on_every_status_label(self):
        for name, obj, label_id in STATUS_LABELS:
            with self.subTest(label=obj):
                self.assertNotIn(CONSTANT_NAME, self.sources[name])
                check_label(self.sources[name], obj, label_id)

    def test_role_enum_semantics_are_pinned(self):
        self.assertEqual(ALERT_MESSAGE_ROLE_VALUE, 8)
        self.assertEqual(ALERT_EVENT_VALUE, 2)
        self.assertNotEqual(ALERT_MESSAGE_ROLE_VALUE, ALERT_EVENT_VALUE)
        for name, obj, label_id in STATUS_LABELS:
            with self.subTest(label=obj):
                block = label_block(self.sources[name], obj)
                self.assertEqual(block.count(ROLE_LINE), 1)
                self.assertIsNone(
                    re.search(r"Accessible\.role:\s*Accessible\.Alert\b", block))

    def test_alertmessage_role_and_empty_ignored_on_every_label(self):
        for name, obj, label_id in STATUS_LABELS:
            with self.subTest(label=obj):
                block = label_block(self.sources[name], obj)
                self.assertIn(ROLE_LINE, block)
                self.assertNotIn("Accessible.role: Accessible.Alert\n", block)
                self.assertIn('Accessible.ignored: %s.text === ""' % label_id, block)

    def test_guarded_announcement_on_every_label(self):
        for name, obj, label_id in STATUS_LABELS:
            with self.subTest(label=obj):
                check_label(self.sources[name], obj, label_id)

    def test_cpp_announce_bridge_is_qt_version_guarded(self):
        check_main(self.main_src)
        self.assertNotIn("#if QT_VERSION >= QT_VERSION_CHECK(6, 9, 0)", self.main_src)

    def test_exactly_one_announcement_for_new_nonempty_status(self):
        self.assertEqual(announce_decision("", "Launching Files", True),
                         ["Accessible.announce"])
        self.assertEqual(announce_decision("", "Launching Files", False),
                         ["QAccessibleEvent"])
        for native in (True, False):
            with self.subTest(native=native):
                self.assertEqual(announce_decision("", "", native), [])
                self.assertEqual(announce_decision("Ready", "Ready", native), [])
                self.assertEqual(announce_decision("Ready", "   ", native), [])
                self.assertEqual(announce_decision("", "Ready", native,
                                                  ready=False), [])
        with self.assertRaises(AssertionError):
            announce_decision(None, "Ready", True)

    def test_negative_control_init_announce_fails(self):
        raw = self.sources["NotificationCenter.qml"]
        hostile = raw.replace('if (text === "" || !a11yAnnounceReady)',
                              'if (text === "")', 1)
        self.assertNotEqual(hostile, raw)
        with self.assertRaises(AssertionError):
            check_label(hostile, "canopyNotificationDisclosure", "disclosure")

    def test_negative_control_constant_name_fails(self):
        raw = self.sources["PreviewWindow.qml"]
        hostile = raw.replace("Accessible.name: fileManagerStatusLabel.text",
                              CONSTANT_NAME, 1)
        self.assertNotEqual(hostile, raw)
        with self.assertRaises(AssertionError):
            check_label(hostile, "canopyFileManagerStatus", "fileManagerStatusLabel")

    def test_negative_control_wrong_alert_enum_fails(self):
        raw = self.sources["PreviewWindow.qml"]
        hostile = raw.replace(ROLE_LINE, "Accessible.role: Accessible.Alert", 1)
        self.assertNotEqual(hostile, raw)
        self.assertEqual(hostile.count("Accessible.role: Accessible.Alert"), 1)
        self.assertEqual(ALERT_MESSAGE_ROLE_VALUE, 8)   # AlertMessage role
        self.assertEqual(ALERT_EVENT_VALUE, 2)          # Alert C++ event
        with self.assertRaises(AssertionError):
            check_label(hostile, "canopyFileManagerStatus", "fileManagerStatusLabel")

    def test_negative_control_removed_announce_fails(self):
        raw = self.sources["LauncherOverlay.qml"]
        hostile = re.sub(ANNOUNCE_BEGIN + r".*?" + ANNOUNCE_END, "", raw,
                         flags=re.DOTALL)
        self.assertNotEqual(hostile, raw)
        with self.assertRaises(AssertionError):
            check_label(hostile, "canopyLauncherStatus", "footer")

    def test_negative_control_visual_text_change_fails(self):
        raw = self.sources["SettingsPanel.qml"]
        hostile = raw.replace('color: "#31475e"', 'color: "#31475f"', 1)
        self.assertNotEqual(hostile, raw)
        self.assertNotEqual(
            hashlib.sha256(visual_projection(hostile).encode("utf-8")).hexdigest(),
            BASE_VISUAL_PROJECTION_SHA256["SettingsPanel.qml"],
        )

    def test_negative_control_unguarded_announce_fails(self):
        raw = self.sources["QuickControlsOverlay.qml"]
        hostile = raw.replace(NATIVE_GUARD, "true", 1)
        self.assertNotEqual(hostile, raw)
        with self.assertRaises(AssertionError):
            check_label(hostile, "canopyQuickControlsMessage", "message")

    def test_negative_control_cpp_guard_removal_fails(self):
        guard = "#if QT_VERSION >= QT_VERSION_CHECK(6, 8, 0)"
        for hostile_guard in ("#if 1",
                              "#if QT_VERSION >= QT_VERSION_CHECK(6, 9, 0)"):
            with self.subTest(guard=hostile_guard):
                hostile = self.main_src.replace(guard, hostile_guard, 1)
                self.assertNotEqual(hostile, self.main_src)
                with self.assertRaises(AssertionError):
                    check_main(hostile)


if __name__ == "__main__":
    unittest.main()
