"""PE-036 focused gate: Return/Space activation of Files rows (QA-005-002).

Offline source-contract test over the checked-in QML. It does not compile Qt,
dispatch real key events, launch a screen reader or claim Mint acceptance.
Both keys must delegate to one shared directory-row activation helper; each
path has its own positive test and its own negative control, so a missing
handler cannot be masked by the other key.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "prototype" / "classic" / "PreviewWindow.qml"

RETURN_HEADER = "Keys.onReturnPressed: function(event) {"
SPACE_HEADER = "Keys.onSpacePressed: function(event) {"
SHARED_HEADER = "function activateFocusedFileRow(event) {"
CALL = "activateFocusedFileRow(event)"
NAVIGATE = "preview.navigate(currentItem.path)"
ACCEPT = "event.accepted = true"
GUARD = "if (currentItem && currentItem.isDir) {"

# Frozen rendering inputs: PE-036 adds key handling only, never pixels.
FROZEN_ROW_LINES = (
    'objectName: "canopyFileList"',
    "focus: visible",
    "model: fileModel",
    'objectName: "canopyFileRow"',
    "required property string name",
    "required property string path",
    "required property bool isDir",
    "MouseArea {",
)


def normalized(text: str) -> str:
    if not isinstance(text, str):
        raise AssertionError("QML source must be text")
    return text.replace("\r\n", "\n")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block(lines: list[str], start_index: int) -> list[str]:
    base = _indent(lines[start_index])
    end = start_index + 1
    while end < len(lines):
        candidate = lines[end]
        if candidate.strip() and not candidate.lstrip().startswith("//") \
                and _indent(candidate) <= base:
            break
        end += 1
    return lines[start_index:end]


def file_list_block(source: str) -> list[str]:
    lines = normalized(source).split("\n")
    for index, line in enumerate(lines):
        if "ListView {" not in line:
            continue
        block = _block(lines, index)
        if "id: fileList" in "\n".join(block):
            return block
    raise AssertionError("fileList declaration not found")


def _unique_block(source: str, header: str, label: str) -> list[str]:
    block = file_list_block(source)
    matches = [index for index, line in enumerate(block) if header in line]
    if len(matches) != 1:
        raise AssertionError("%s handler count is %d, expected 1"
                             % (label, len(matches)))
    return _block(block, matches[0])


def activation_block(source: str, key: str) -> list[str]:
    if key not in ("Return", "Space"):
        raise AssertionError("unknown activation key: " + key)
    header = RETURN_HEADER if key == "Return" else SPACE_HEADER
    return _unique_block(source, header, "file-list " + key + " activation")


def shared_block(source: str) -> list[str]:
    return _unique_block(source, SHARED_HEADER, "shared file-row activation")


def check_activation_path(source: str, key: str) -> bool:
    """Fail closed unless one key reaches the shared directory activation."""
    handler = normalized("\n".join(activation_block(source, key)))
    prefix = "file-list %s activation" % key
    if handler.count(CALL) != 1:
        raise AssertionError(prefix + " does not delegate to the shared path")
    body = normalized("\n".join(shared_block(source)))
    if GUARD not in body:
        raise AssertionError("shared activation does not guard on a directory")
    if NAVIGATE not in body:
        raise AssertionError("shared activation does not navigate the row")
    if ACCEPT not in body:
        raise AssertionError("shared activation does not accept the key event")
    if body.index(GUARD) >= body.index(NAVIGATE):
        raise AssertionError("shared activation navigates outside the guard")
    if body.index(NAVIGATE) >= body.index(ACCEPT):
        raise AssertionError("shared activation accepts before navigating")
    return True


def check_contract(source: str) -> bool:
    """Both paths, the shared action and the old keys must all survive."""
    check_activation_path(source, "Return")
    check_activation_path(source, "Space")
    file_text = normalized("\n".join(file_list_block(source)))
    if "Keys.onPressed: function(event) {" not in file_text:
        raise AssertionError("existing Backspace/Escape contract lost")
    for key in ("Return", "Space"):
        if key not in file_text:
            raise AssertionError("keyboard activation key omitted: " + key)
    lines = normalized(source).split("\n")
    for frozen in FROZEN_ROW_LINES:
        if sum(1 for line in lines if line.strip() == frozen) != 1:
            raise AssertionError("frozen file-row rendering input changed: "
                                 + frozen)
    if not any("preview.navigate(path)" in line for line in lines):
        raise AssertionError("pointer activation contract lost")
    return True


def _mutate(source: str, block: list[str], old: str, new: str) -> str:
    """Mutate only one block and prove the mutation applied."""
    text = "\n".join(block)
    if text.count(old) != 1:
        raise AssertionError("mutation target not unique: " + old)
    mutated = source.replace(text, text.replace(old, new, 1), 1)
    if mutated == source:
        raise AssertionError("mutation did not apply")
    return mutated


class FileRowKeyboardActivationTests(unittest.TestCase):
    def setUp(self):
        self.source = normalized(PREVIEW.read_text(encoding="utf-8"))

    def test_checked_in_qml_supports_both_activation_paths(self):
        self.assertTrue(check_contract(self.source))

    def test_return_activates_the_focused_directory_row(self):
        self.assertTrue(check_activation_path(self.source, "Return"))

    def test_space_activates_the_focused_directory_row(self):
        self.assertTrue(check_activation_path(self.source, "Space"))

    def test_negative_control_return_handler_removed_fails(self):
        hostile = self.source.replace(RETURN_HEADER + "\n", "", 1)
        self.assertNotEqual(hostile, self.source, "mutation did not apply")
        with self.assertRaisesRegex(AssertionError,
                                    "Return activation handler count"):
            activation_block(hostile, "Return")

    def test_negative_control_space_handler_removed_fails(self):
        hostile = self.source.replace(SPACE_HEADER + "\n", "", 1)
        self.assertNotEqual(hostile, self.source, "mutation did not apply")
        with self.assertRaisesRegex(AssertionError,
                                    "Space activation handler count"):
            activation_block(hostile, "Space")

    def test_negative_control_return_path_not_delegated_fails(self):
        hostile = _mutate(self.source, activation_block(self.source, "Return"),
                          CALL, "noop(event)")
        with self.assertRaisesRegex(AssertionError,
                                    "Return activation does not delegate"):
            check_activation_path(hostile, "Return")

    def test_negative_control_space_path_not_delegated_fails(self):
        hostile = _mutate(self.source, activation_block(self.source, "Space"),
                          CALL, "noop(event)")
        with self.assertRaisesRegex(AssertionError,
                                    "Space activation does not delegate"):
            check_activation_path(hostile, "Space")

    def test_negative_control_shared_navigation_removed_fails(self):
        hostile = _mutate(self.source, shared_block(self.source),
                          NAVIGATE, "noop()")
        with self.assertRaisesRegex(AssertionError,
                                    "shared activation does not navigate"):
            check_activation_path(hostile, "Space")

    def test_negative_control_shared_event_not_accepted_fails(self):
        hostile = _mutate(self.source, shared_block(self.source),
                          ACCEPT, "noop()")
        with self.assertRaisesRegex(AssertionError,
                                    "shared activation does not accept"):
            check_activation_path(hostile, "Return")


if __name__ == "__main__":
    unittest.main()
