"""CI discovery mirror for tools.qa.mint_guest_preflight_type_tests.

Foundation runs ``python -m unittest discover -s tests`` and does not scan
``tools/qa``. This module only re-exports the five domain-error regression
tests; assertions remain in the owned tools/qa module.
"""
from tools.qa.mint_guest_preflight_type_tests import (  # noqa: F401
    MintPreflightTypeTests,
)

__all__ = ["MintPreflightTypeTests"]


if __name__ == "__main__":
    import unittest

    unittest.main()
