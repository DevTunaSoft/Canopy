"""Unified LacOS Software Center presentation wiring.

Pure, bounded and read-only. Consumes a pinned snapshot projected from the
bounded source capability manifest of PR #753 (head 616ce171) without importing
or modifying that unmerged PR. No installation, no guest execution, no service.
"""

from .center import (  # noqa: F401
    ECOSYSTEM_IDS,
    FORBIDDEN_CAPABILITIES,
    SoftwareCenterError,
    SoftwareCenterView,
    build_center_view,
    presentation_lines,
    view_dict,
)

__all__ = (
    "ECOSYSTEM_IDS",
    "FORBIDDEN_CAPABILITIES",
    "SoftwareCenterError",
    "SoftwareCenterView",
    "build_center_view",
    "presentation_lines",
    "view_dict",
)
