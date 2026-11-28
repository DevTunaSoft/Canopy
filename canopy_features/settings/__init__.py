"""Fail-closed Classic settings contracts.

This package contains host-side preference contracts only. It creates no
daemon, performs no privileged writes and invents no host event topic.
"""

from .persisted_preferences import (
    KEYS,
    PreferenceView,
    PersistedPreferences,
    PersistedPreferencesError,
    view_for_key,
)
from .shell_pack_selection import (
    BUILTIN_IDS,
    BUILTIN_PACKS,
    INCLUDED_TIER,
    PAID_TIERS,
    SHARED_CORE_SERVICES,
    PackIdentity,
    PackSwitchLedger,
    SelectionSnapshot,
    ShellPackSelectionError,
    inventory_snapshot,
    is_builtin,
    shared_core_snapshot,
    validate_future_pack,
    validate_pack_id,
)

__all__ = [
    "KEYS",
    "PreferenceView",
    "PersistedPreferences",
    "PersistedPreferencesError",
    "view_for_key",
    "BUILTIN_IDS",
    "BUILTIN_PACKS",
    "INCLUDED_TIER",
    "PAID_TIERS",
    "SHARED_CORE_SERVICES",
    "PackIdentity",
    "PackSwitchLedger",
    "SelectionSnapshot",
    "ShellPackSelectionError",
    "inventory_snapshot",
    "is_builtin",
    "shared_core_snapshot",
    "validate_future_pack",
    "validate_pack_id",
]
