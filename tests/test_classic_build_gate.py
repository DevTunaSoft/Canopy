"""CI-visible mirror of tools.build.tests.test_classic_build_gate.

Foundation CI runs ``unittest discover -s tests``; this module keeps the
source-pin regression cases visible there without duplicating test logic.
"""

from tools.build.tests.test_classic_build_gate import (  # noqa: F401
    GateRunMixin,
    GreenTests,
    NegativeControlTests,
    PinContractTests,
    RealEvidenceTests,
)
