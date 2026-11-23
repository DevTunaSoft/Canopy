"""Expose the tools/qa Mint smoke type guards to standard test discovery.

The authoritative tests remain in ``tools/qa/mint_smoke_type_guard_tests.py``.
This thin import makes them visible to ``python -m unittest discover -s tests``
without duplicating assertions or touching CI configuration.
"""
from __future__ import annotations

import unittest

from tools.qa.mint_smoke_type_guard_tests import MintSmokeTypeGuardTests

__all__ = ["MintSmokeTypeGuardTests"]


if __name__ == "__main__":
    unittest.main()
