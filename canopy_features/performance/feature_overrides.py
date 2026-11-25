"""Offline validator for resource-profile feature-override precedence.

Models Canopy's planned five performance profiles plus Auto Mode and the
per-feature overrides described in docs/LACOS_VISION.md. This is a pure,
bounded calculation: no Qt, no threads, no polling, no I/O and no services.
It does not configure a running shell or prove desktop behavior; wiring it
into the compiled Qt application is future work.
"""
from dataclasses import dataclass

# Five performance profiles plus Auto Mode (docs/LACOS_VISION.md).
PROFILES = ("powersaver", "battery", "balanced", "performance", "maximum", "auto")

# Resource-using shell features a profile may toggle. Booleans only.
FEATURES = (
    "blur_effects", "wallpaper_animation", "dock_animation",
    "search_indexing", "live_wallpaper",
)

# Precedence from lowest to highest. A later scope overrides an earlier one.
SCOPES = ("baseline", "profile", "user")

FEATURE_DEFAULTS = {feature: False for feature in FEATURES}


class OverrideError(ValueError):
    """Invalid profile/feature/scope/value, or an ambiguous override conflict."""


@dataclass(frozen=True)
class FeatureOverride:
    """One declarative override.

    ``profile`` is required only for scope="profile"; for "baseline" and
    "user" it must be None.
    """
    scope: str
    feature: str
    value: bool
    profile: object = None


class ProfileFeatureResolver:
    """Validate overrides once, then resolve effective feature values.

    Construction is the single trust boundary: every override is checked and
    same-scope conflicts fail closed. Resolution is a pure lookup with fixed
    precedence baseline < profile < user. No state is mutated after init.
    """

    def __init__(self, overrides=()):
        if type(overrides) not in (list, tuple):
            raise OverrideError("overrides must be a list or tuple")
        self._baseline = {}
        self._profile = {}
        self._user = {}
        seen = {}
        for override in overrides:
            if not isinstance(override, FeatureOverride):
                raise OverrideError("override entries must be FeatureOverride")
            scope = override.scope
            feature = override.feature
            value = override.value
            profile = override.profile
            if type(scope) is not str or scope not in SCOPES:
                raise OverrideError("invalid override scope")
            if type(feature) is not str or feature not in FEATURES:
                raise OverrideError("invalid override feature")
            # bool is an int subclass; require an exact bool, never 1/0.
            if type(value) is not bool:
                raise OverrideError("override value must be a bool")
            if scope == "profile":
                self._check_profile(profile)
                key = (scope, profile, feature)
            else:
                if profile is not None:
                    raise OverrideError("scope does not accept a profile")
                key = (scope, None, feature)
            if key in seen:
                if seen[key] != value:
                    raise OverrideError("conflicting override at same scope")
                continue
            seen[key] = value
            if scope == "baseline":
                self._baseline[feature] = value
            elif scope == "user":
                self._user[feature] = value
            else:
                self._profile[(profile, feature)] = value

    @staticmethod
    def _check_profile(profile):
        if type(profile) is not str or profile not in PROFILES:
            raise OverrideError("invalid resource profile")

    def resolve(self, profile, feature):
        """Return the effective bool for one profile/feature pair."""
        self._check_profile(profile)
        if type(feature) is not str or feature not in FEATURES:
            raise OverrideError("invalid override feature")
        value = self._baseline.get(feature, FEATURE_DEFAULTS[feature])
        profile_value = self._profile.get((profile, feature))
        if profile_value is not None:
            value = profile_value
        if feature in self._user:
            value = self._user[feature]
        return value

    def effective(self, profile):
        """Return a fresh dict of all effective features for a profile."""
        self._check_profile(profile)
        return {feature: self.resolve(profile, feature) for feature in FEATURES}
