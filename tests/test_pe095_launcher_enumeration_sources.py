"""PE-095 / PE-023: bounded launcher enumeration source-contract tests.

Pure-contract only. No filesystem enumeration, process launch, timer, network
or real desktop is used by these tests; the only reads are of the module's own
source text for the negative no-I/O contract.

Scope boundary: this file tests ``launcher_enumeration_sources`` only. It does
not import or exercise PR #694's native catalog refresh bridge or PR #696's
compiled-boundary characterization tests.
"""
from __future__ import annotations

import builtins
from collections.abc import Mapping
import os
import pathlib
import subprocess
import threading
import time
import unittest
from unittest import mock

from canopy_features.launcher import launcher_enumeration_sources as les


# Leading-slash paths are absolute on both POSIX and Windows (ntpath.isabs
# accepts a rooted path without a drive), so these fixtures run on CI too.
BASE = "/synthetic/xdg/applications"
ALT = "/synthetic/other/applications"


def _descriptor(role=les.ROLE_EXPLICIT, path=BASE, **extra):
    data = {"role": role, "path": path}
    data.update(extra)
    return data


class _BadMapping(Mapping):
    """A Mapping whose keys()/getitem disagree, to prove KeyError translation."""

    def __init__(self, data):
        self._data = data

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        raise KeyError(key)


class _HostileGetitemMapping(Mapping):
    """Valid keys(), hostile __getitem__: reaches the value-read guard."""

    def __init__(self, exc_type):
        self._data = {"role": les.ROLE_EXPLICIT, "path": BASE}
        self._exc_type = exc_type

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        raise self._exc_type("hostile unreadable descriptor: do not echo")


class _HostileKeysMapping(Mapping):
    """Readable items, hostile keys(): reaches the key-read guard."""

    def __init__(self, exc_type):
        self._data = {"role": les.ROLE_EXPLICIT, "path": BASE}
        self._exc_type = exc_type

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        raise self._exc_type("hostile unreadable keys: do not echo")


class DescribeEnumerationSourcesTests(unittest.TestCase):
    # ---- happy path -----------------------------------------------------
    def test_happy_path_canonical_order_and_claims(self):
        snap = les.describe_enumeration_sources([
            _descriptor(les.ROLE_EXPLICIT, ALT, max_entries=32),
            _descriptor(les.ROLE_XDG_DATA_HOME, BASE, max_entries=16),
        ])
        self.assertEqual(
            [d.role for d in snap.sources],
            [les.ROLE_EXPLICIT, les.ROLE_XDG_DATA_HOME])
        self.assertEqual([d.path for d in snap.sources], [ALT, BASE])
        self.assertEqual([d.max_entries for d in snap.sources], [32, 16])
        self.assertEqual(snap.max_total_entries, les.MAX_TOTAL_ENTRIES)
        self.assertEqual(snap.claims, les.FIXED_CLAIMS)
        self.assertIsInstance(snap.sources, tuple)

    def test_to_dict_reports_counts_only_and_echoes_no_path(self):
        snap = les.describe_enumeration_sources([
            _descriptor(path="/secret/root/applications")])
        data = snap.to_dict()
        self.assertEqual(data["source_count"], 1)
        self.assertEqual(data["per_source_max_entries"],
                         (les.MAX_ENTRIES_PER_SOURCE,))
        self.assertEqual(data["claims"], list(les.FIXED_CLAIMS))
        self.assertNotIn("secret", repr(data))
        self.assertNotIn("applications", repr(data))

    def test_to_paths_is_ordered_and_immutable(self):
        snap = les.describe_enumeration_sources([
            _descriptor(les.ROLE_XDG_DATA_DIRS, ALT),
            _descriptor(les.ROLE_EXPLICIT, BASE),
        ])
        paths = snap.to_paths()
        self.assertIsInstance(paths, tuple)
        self.assertEqual(paths, (
            (les.ROLE_EXPLICIT, BASE, les.MAX_ENTRIES_PER_SOURCE),
            (les.ROLE_XDG_DATA_DIRS, ALT, les.MAX_ENTRIES_PER_SOURCE),
        ))

    def test_fixed_claims_cover_all_negative_contracts(self):
        expected = {
            "no_implicit_discovery",
            "no_symlink_follow",
            "no_recursive_walk",
            "no_duplicate_sources",
            "no_unbounded_growth",
            "no_filesystem_io",
            "no_process_launch",
            "no_visual_change",
        }
        self.assertEqual(set(les.FIXED_CLAIMS), expected)
        self.assertEqual(len(les.FIXED_CLAIMS), len(expected))

    # ---- source container type gates -----------------------------------
    def test_rejects_unordered_or_scalar_source_containers(self):
        for bad in ({"hashable-sentinel"}, frozenset({"hashable-sentinel"}),
                    {0: _descriptor()}, "abc", b"abc", None, 7,
                    (d for d in [_descriptor()])):
            with self.subTest(bad=type(bad).__name__), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources(bad)

    def test_rejects_too_many_sources_without_materializing_all(self):
        descriptors = [
            _descriptor(path="/synthetic/d%d/applications" % i)
            for i in range(les.MAX_SOURCES + 1)
        ]
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources(descriptors)

    def test_rejects_duplicate_role_path_pair(self):
        dupe = _descriptor()
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources([dupe, dict(dupe)])

    def test_same_role_distinct_paths_is_allowed(self):
        snap = les.describe_enumeration_sources([
            _descriptor(path=BASE), _descriptor(path=ALT)])
        self.assertEqual(len(snap.sources), 2)

    def test_rejects_unknown_role(self):
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources([_descriptor(role="home")])

    # ---- path gates -----------------------------------------------------
    def test_rejects_relative_path(self):
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources(
                [_descriptor(path="relative/applications")])

    def test_rejects_dotdot_component(self):
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources(
                [_descriptor(path="/synthetic/../outside/applications")])

    def test_rejects_control_and_unsafe_unicode_path(self):
        for path in (BASE + "\n", BASE + "\x7f", BASE + "\ud800",
                     BASE + "\u2028"):
            with self.subTest(path=repr(path)), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources([_descriptor(path=path)])

    def test_rejects_wrong_type_and_oversized_path(self):
        for path in (7, b"/x/applications", BASE * 40):
            with self.subTest(path=type(path).__name__), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources([_descriptor(path=path)])

    # ---- descriptor gates -----------------------------------------------
    def test_rejects_bad_descriptor_containers(self):
        for desc in (BASE, b"x", 7, None, [les.ROLE_EXPLICIT, BASE]):
            with self.subTest(desc=type(desc).__name__), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources([desc])

    def test_rejects_unknown_or_missing_descriptor_keys(self):
        for desc in (
            {"role": les.ROLE_EXPLICIT, "path": BASE, "extra": 1},
            {"role": les.ROLE_EXPLICIT},
            {"path": BASE},
            {7: les.ROLE_EXPLICIT, "path": BASE},
        ):
            with self.subTest(desc=sorted(map(str, desc))), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources([desc])

    def test_unreadable_mapping_raises_domain_error(self):
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources([_BadMapping(
                {"role": les.ROLE_EXPLICIT, "path": BASE})])

    def test_hostile_getitem_exceptions_raise_domain_error(self):
        # Controls: each fixture exposes valid keys(), so the old narrow
        # KeyError/TypeError/IndexError guard cannot reject it before
        # __getitem__ is reached. All four must fail closed with no echo.
        for exc_type in (OSError, ValueError, RuntimeError):
            with self.subTest(exc=exc_type.__name__):
                with self.assertRaises(les.EnumerationSourceError) as ctx:
                    les.describe_enumeration_sources(
                        [_HostileGetitemMapping(exc_type)])
                self.assertIs(type(ctx.exception), les.EnumerationSourceError)
                self.assertNotIn("hostile", str(ctx.exception))

    def test_hostile_keys_exception_raises_domain_error(self):
        with self.assertRaises(les.EnumerationSourceError) as ctx:
            les.describe_enumeration_sources([_HostileKeysMapping(RuntimeError)])
        self.assertIs(type(ctx.exception), les.EnumerationSourceError)
        self.assertNotIn("hostile", str(ctx.exception))

    def test_hardening_still_accepts_well_formed_custom_mapping(self):
        class _GoodMapping(Mapping):
            def __init__(self, data):
                self._data = data

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

            def __getitem__(self, key):
                return self._data[key]

        snap = les.describe_enumeration_sources([_GoodMapping(
            {"role": les.ROLE_EXPLICIT, "path": BASE, "max_entries": 8})])
        self.assertEqual(len(snap.sources), 1)
        self.assertEqual(snap.sources[0].max_entries, 8)

    def test_rejects_bad_max_entries_values(self):
        for value in (True, 0, -1, 1.5, "8", None,
                      les.MAX_ENTRIES_PER_SOURCE + 1):
            with self.subTest(value=repr(value)), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources(
                    [_descriptor(max_entries=value)])

    # ---- bounds and cross-field consistency -----------------------------
    def test_rejects_wrong_type_and_oversized_bounds(self):
        for kwargs in (
            {"max_sources": True},
            {"max_sources": les.MAX_SOURCES + 1},
            {"max_total_entries": 0},
            {"max_total_entries": les.MAX_TOTAL_ENTRIES + 1},
            {"max_path_chars": 1.0},
            {"max_path_chars": les.MAX_PATH_CHARS + 1},
            {"max_entries_per_source": False},
            {"max_entries_per_source": les.MAX_ENTRIES_PER_SOURCE + 1},
        ):
            with self.subTest(kwargs=kwargs), \
                    self.assertRaises(les.EnumerationSourceError):
                les.describe_enumeration_sources([_descriptor()], **kwargs)

    def test_caller_may_tighten_bounds(self):
        snap = les.describe_enumeration_sources(
            [_descriptor(max_entries=4)], max_sources=1,
            max_total_entries=8, max_path_chars=len(BASE),
            max_entries_per_source=4)
        self.assertEqual(snap.max_total_entries, 8)
        self.assertEqual(snap.sources[0].max_entries, 4)

    def test_rejects_sum_over_max_total_entries(self):
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources(
                [_descriptor(path=BASE, max_entries=6),
                 _descriptor(path=ALT, max_entries=6)],
                max_total_entries=10)

    def test_rejection_is_atomic_no_partial_snapshot(self):
        good = _descriptor()
        bad = _descriptor(path="relative/applications")
        with self.assertRaises(les.EnumerationSourceError):
            les.describe_enumeration_sources([good, bad])

    # ---- no side effects / scope boundary -------------------------------
    def test_no_filesystem_process_timer_or_network_side_effects(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("forbidden side effect during contract call")

        with mock.patch.object(os, "scandir", forbidden), \
                mock.patch.object(os, "open", forbidden), \
                mock.patch.object(builtins, "open", forbidden), \
                mock.patch.object(subprocess, "Popen", forbidden), \
                mock.patch.object(time, "sleep", forbidden), \
                mock.patch.object(threading, "Timer", forbidden):
            snap = les.describe_enumeration_sources([_descriptor()])
        self.assertEqual(len(snap.sources), 1)

    def test_source_contract_does_not_reference_pr694_or_pr696_paths(self):
        src = pathlib.Path(les.__file__).read_text(encoding="utf-8")
        self.assertNotIn("native_catalog_refresh", src)
        self.assertNotIn("scandir", src)
        self.assertNotIn("subprocess", src)
        self.assertNotIn("QTimer", src)


if __name__ == "__main__":
    unittest.main()
