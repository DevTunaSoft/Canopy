"""CI discovery mirror for tools.qa.mint_acceptance_gate_type_tests.

Foundation runs ``python -m unittest discover -s tests`` and does not scan
``tools/qa``. This module only re-exports the three boundary regression tests;
all assertions remain in the owned tools/qa test module.
"""
from tools.qa.mint_acceptance_gate_type_tests import (  # noqa: F401
    MintAcceptanceGateTypeTests,
)

__all__ = ["MintAcceptanceGateTypeTests"]


if __name__ == "__main__":
    import unittest

    unittest.main()
