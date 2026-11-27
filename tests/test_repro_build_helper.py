"""CI-visible mirror of tools.build.tests.test_repro_build_helper.

Foundation CI runs ``unittest discover -s tests``; this module keeps the
reproducibility-helper regression cases visible there without duplicating any
test logic.
"""

from tools.build.tests.test_repro_build_helper import (  # noqa: F401
    EolContractTests,
    StageContractTests,
    TimestampInputTests,
)
