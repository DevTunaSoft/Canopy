"""Offline policy for optional visual effects with hard low-resource defaults.

Pure decision logic: no Qt import, no timers, no threads, no filesystem or
network access. The compiled Classic Qt presentation must call ``resolve()``
and honour its decisions; this module never starts, renders or polls an
effect itself.

Hard policy, unoverridable by any toggle, profile or budget:
  * perpetual (infinite) animation is always disabled
  * always-on blur and live wallpaper are always disabled
  * enabled effect cost never exceeds the effective profile budget
  * a profile is a budget ceiling, and ``minimal`` forces a zero budget

Defaults are hard low-resource: no argument, or profile ``minimal``, yields
budget 0 so every optional effect is off.
"""
from typing import NamedTuple

__all__ = [
    "PolicyError", "Effect", "EFFECTS", "PROFILES", "DEFAULT_PROFILE",
    "MAX_BUDGET", "HARD_RULES", "known_effects", "resolve",
]


class PolicyError(ValueError):
    """Invalid, unknown or unbounded effects-policy input."""


class Effect(NamedTuple):
    name: str
    cost: int
    perpetual: bool
    note: str


# Declared once, in enable-priority order. Fixed set: effects cannot be
# registered at runtime, so input size and cost are bounded by construction.
EFFECTS = (
    Effect("ui_transitions", 1, False, "short one-shot control transitions"),
    Effect("dock_hover_scale", 1, False, "one-shot dock hover scale"),
    Effect("menu_fade", 1, False, "short one-shot menu fade"),
    Effect("window_shadow", 2, False, "static window shadow"),
    Effect("translucency", 3, False, "static translucent surfaces"),
    Effect("always_on_blur", 4, True, "forbidden: constant blur"),
    Effect("live_wallpaper", 5, True, "forbidden: animated wallpaper"),
    Effect("infinite_animation", 5, True, "forbidden: perpetual animation"),
)

PROFILES = {
    "minimal": 0,
    "balanced": 2,
    "high": 5,
}
DEFAULT_PROFILE = "minimal"
MAX_BUDGET = 5

HARD_RULES = (
    "perpetual_animation_disabled",
    "always_on_blur_disabled",
    "live_wallpaper_disabled",
    "profile_budget_is_ceiling",
    "minimal_profile_forces_zero_budget",
)


def known_effects():
    """Return the fixed tuple of effect names this policy understands."""
    return tuple(effect.name for effect in EFFECTS)


def _checked_toggles(toggles):
    if toggles is None:
        return {}
    if type(toggles) is not dict:
        raise PolicyError("effect toggles must be a mapping")
    if len(toggles) > len(EFFECTS):
        raise PolicyError("too many effect toggles")
    known = set(known_effects())
    checked = {}
    for name, value in toggles.items():
        if type(name) is not str or name not in known:
            raise PolicyError("unknown effect: %s" % str(name)[:40])
        if type(value) is not bool:
            raise PolicyError("invalid effect toggle for %s" % name)
        checked[name] = value
    return checked


def _effective_budget(profile, budget):
    if type(profile) is not str or profile not in PROFILES:
        raise PolicyError("unknown performance profile")
    if budget is None:
        value = PROFILES[profile]
    else:
        if type(budget) is not int or not 0 <= budget <= MAX_BUDGET:
            raise PolicyError("invalid effect budget")
        value = budget
    value = min(value, PROFILES[profile])
    if profile == DEFAULT_PROFILE:
        value = 0
    return value


def resolve(toggles=None, profile=DEFAULT_PROFILE, budget=None):
    """Resolve requested effect toggles into bounded, auditable decisions.

    Returns a JSON-serialisable plan. Never grants release approval and
    never proves a running desktop; wiring into the Qt app is future work.
    """
    checked = _checked_toggles(toggles)
    effective_budget = _effective_budget(profile, budget)

    decisions = {}
    denied = {}
    enabled = []
    used = 0
    for effect in EFFECTS:
        name = effect.name
        if effect.perpetual:
            decisions[name] = False
            denied[name] = "perpetual_effect_forbidden"
        elif not checked.get(name, False):
            decisions[name] = False
            denied[name] = "not_requested"
        elif used + effect.cost > effective_budget:
            decisions[name] = False
            denied[name] = "over_budget"
        else:
            decisions[name] = True
            enabled.append(name)
            used += effect.cost

    return {
        "profile": profile,
        "budget": effective_budget,
        "used_budget": used,
        "remaining_budget": effective_budget - used,
        "hard_rules": list(HARD_RULES),
        "decisions": decisions,
        "enabled": enabled,
        "denied": denied,
        "release_approved": False,
        "desktop_proven": False,
    }
