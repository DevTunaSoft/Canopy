"""Regression tests for fatal Qt/QML diagnostic detection."""
import unittest

from tools.qt_smoke import qml_diagnostics


class QmlDiagnosticTests(unittest.TestCase):
    def test_detects_binding_failure(self):
        log = b'qrc:/Canopy/Classic/Main.qml:180:25: Unable to assign [undefined] to QColor\n'
        self.assertEqual(len(qml_diagnostics(log)), 1)

    def test_detects_reference_and_binding_loop(self):
        log = (
            b'qrc:/Main.qml:13: ReferenceError: missingName is not defined\n'
            b'qrc:/Main.qml:20: Binding loop detected for property "width"\n'
        )
        self.assertEqual(len(qml_diagnostics(log)), 2)

    def test_ignores_normal_startup_output(self):
        self.assertEqual(qml_diagnostics(b'CANOPY_CLASSIC_WINDOW_READY\n'), [])
        self.assertEqual(qml_diagnostics(b'Qt warning: software backend selected\n'), [])


if __name__ == "__main__":
    unittest.main()
