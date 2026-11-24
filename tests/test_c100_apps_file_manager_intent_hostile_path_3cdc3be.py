"""Hostile-but-bounded wrong-type path/home values must fail closed.

``form_file_manager_intent`` documents that every refusal is a stable
``IntentRejected`` reason. A caller-supplied ``os.PathLike`` whose
``__fspath__`` raises, or a ``str`` subclass whose ``strip`` raises, is a
bounded bad input: it must never leak a raw built-in exception across the
composition boundary, and it must never yield an intent that claims safety.

Pure/offline: a temporary host directory stands in for the home scope. No Qt,
desktop, process launch or network access is involved.
"""

from pathlib import Path
import tempfile
import unittest

from canopy_features.apps.file_manager_intent import (
    REASON_HOME_UNAVAILABLE,
    REASON_INVALID_PATH,
    FileManagerIntent,
    IntentRejected,
    form_file_manager_intent,
)


class FailingPathLike:
    """Bounded os.PathLike: one read attempt, then raises the seeded error."""

    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        raise self.exc


class BytesPathLike:
    """Bounded os.PathLike whose fspath returns a wrong-type bytes value."""

    def __init__(self):
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        return b"/home/somewhere"


class FailingStr(str):
    """str subclass with a hostile, bounded ``strip`` override."""

    exc: BaseException | None
    wrong_type: bool
    calls: int

    def __new__(cls, value, exc=None, wrong_type=False):
        obj = super().__new__(cls, value)
        obj.exc = exc
        obj.wrong_type = wrong_type
        obj.calls = 0
        return obj

    def strip(self, chars=None):  # type: ignore[override]
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        if self.wrong_type:
            return 123  # type: ignore[return-value]
        return str(self)


class HostilePathFailClosedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="canopy-intent-hostile-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()

    def assert_invalid_path(self, value, **kwargs):
        with self.assertRaises(IntentRejected) as caught:
            form_file_manager_intent(value, home=self.home, **kwargs)
        self.assertEqual(caught.exception.reason, REASON_INVALID_PATH)

    def test_fspath_value_error_is_invalid_path_not_raw_exception(self):
        hostile = FailingPathLike(ValueError("boom"))
        self.assert_invalid_path(hostile)
        self.assertLessEqual(hostile.calls, 2)

    def test_fspath_runtime_error_is_invalid_path_not_raw_exception(self):
        hostile = FailingPathLike(RuntimeError("boom"))
        self.assert_invalid_path(hostile)
        self.assertLessEqual(hostile.calls, 2)

    def test_fspath_os_error_is_invalid_path_not_raw_exception(self):
        hostile = FailingPathLike(OSError("boom"))
        self.assert_invalid_path(hostile)
        self.assertLessEqual(hostile.calls, 2)

    def test_fspath_generic_exception_is_invalid_path_not_raw_exception(self):
        hostile = FailingPathLike(Exception("boom"))
        self.assert_invalid_path(hostile)
        self.assertLessEqual(hostile.calls, 2)

    def test_str_strip_failure_is_invalid_path_not_raw_exception(self):
        hostile = FailingStr("docs", ValueError("boom"))
        self.assert_invalid_path(hostile)
        self.assertEqual(hostile.calls, 1)

    def test_str_strip_wrong_type_is_invalid_path(self):
        hostile = FailingStr("docs", wrong_type=True)
        self.assert_invalid_path(hostile)
        self.assertEqual(hostile.calls, 1)

    def test_bytes_from_fspath_is_invalid_path(self):
        hostile = BytesPathLike()
        self.assert_invalid_path(hostile)
        self.assertLessEqual(hostile.calls, 2)

    def test_no_intent_is_returned_for_unreadable_path(self):
        for exc in (ValueError("boom"), RuntimeError("boom"),
                    OSError("boom"), Exception("boom")):
            with self.subTest(exc=type(exc).__name__):
                try:
                    result = form_file_manager_intent(
                        FailingPathLike(exc), home=self.home)
                except IntentRejected:
                    continue
                self.fail("unreadable path yielded an intent: " + repr(result))

    def test_hostile_home_generic_exception_is_home_unavailable(self):
        with self.assertRaises(IntentRejected) as caught:
            form_file_manager_intent(home=FailingPathLike(Exception("boom")))
        self.assertEqual(caught.exception.reason, REASON_HOME_UNAVAILABLE)

    def test_well_formed_path_still_yields_safe_intent(self):
        docs = self.home / "Documents"
        docs.mkdir()
        intent = form_file_manager_intent(docs, home=self.home)
        self.assertIsInstance(intent, FileManagerIntent)
        self.assertEqual(intent.directory, str(docs))
        self.assertEqual(intent.uri, docs.as_uri())


if __name__ == "__main__":
    unittest.main()
