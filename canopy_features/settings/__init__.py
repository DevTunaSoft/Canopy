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

__all__ = [
    "KEYS",
    "PreferenceView",
    "PersistedPreferences",
    "PersistedPreferencesError",
    "view_for_key",
]
