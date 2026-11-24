"""CI discovery mirror for tools.qa.mint_smoke_direct_invocation_tests.

Foundation runs ``python -m unittest discover -s tests`` and does not scan
``tools/qa``. This module only re-exports the three process-level regression
tests so CI executes the same tests already run explicitly by Agent C.
No test logic is duplicated here; no VM, Qt binary or guest is required.
"""
from tools.qa.mint_smoke_direct_invocation_tests import (  # noqa: F401
    MintSmokeDirectInvocationTests,
)
