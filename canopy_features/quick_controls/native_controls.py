"""Bounded native quick controls for KDE Plasma / FreeDesktop hosts.

This is the planning and verdict layer for the three M3 control domains
(brightness, network, power). It reuses *upstream* services only:

- ``org.kde.Solid.PowerManagement`` / ``Actions.BrightnessControl`` (KDE
  PowerDevil) for display brightness;
- ``org.freedesktop.NetworkManager`` for a connectivity recheck;
- ``org.freedesktop.login1.Manager`` for read-only power capability queries.

It creates no bus connection, daemon, service file, thread, timer, socket or
subprocess, reads no environment, device, credential or clock, and never
executes a command. A trusted host supplies bounded probe facts and executes
only an exact :class:`CommandPlan` returned here. Privileged host transitions
(suspend, hibernate, power-off, reboot, lock, logout) are permanently refused,
as in the pre-existing session-control contracts.

Execution labels are truthful and independent of availability:

- ``NOT_RUN`` — no host command was performed; either no trusted probe was
  supplied or the capability/device does not exist.
- ``BLOCKED`` — the host capability exists but policy or permission refused it
  before any state change (for example NetworkManager ``PermissionDenied`` or
  logind ``AccessDenied``).
- ``PASS`` — only a trusted host that actually completed a returned plan may
  record it, via :func:`NativeControls.host_result`; the planner never claims
  it by itself.

Fixed reason codes and disclosures come from the existing
``canopy_features.system.quick_controls_state`` vocabulary. No event topic,
wire field, UI token, protocol version, shell string or executable path is
introduced.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from types import MappingProxyType
from typing import Optional

from canopy_features.system import quick_controls_state as _qcs

__all__ = [
    "NATIVE_DOMAINS", "ACTIONS", "PRIVILEGED_TRANSITIONS",
    "EXECUTION_PASS", "EXECUTION_NOT_RUN", "EXECUTION_BLOCKED",
    "EXECUTION_LABELS", "PLAN_KEYS", "MAX_DELTA", "MAX_BRIGHTNESS",
    "MAX_SOURCE_BYTES", "PERMISSION_TOKENS", "POWER_TOKENS",
    "NativeControlsError", "CommandPlan", "ProbeFacts", "ControlVerdict",
    "NativeControls",
]


NATIVE_DOMAINS = ("brightness", "network", "power")
ACTIONS = MappingProxyType({
    "brightness": "brightness-step",
    "network": "recheck-connectivity",
    "power": "query-power-capability",
})
PRIVILEGED_TRANSITIONS = frozenset({
    "suspend", "hibernate", "poweroff", "reboot",
})

EXECUTION_PASS = _qcs.EXECUTION_PASS
EXECUTION_NOT_RUN = _qcs.EXECUTION_NOT_RUN
EXECUTION_BLOCKED = _qcs.EXECUTION_BLOCKED
EXECUTION_LABELS = _qcs.EXECUTION_LABELS

# Bounds are hard ceilings: callers may supply smaller values, never larger.
MAX_DELTA = 100
MAX_BRIGHTNESS = 65535
MAX_SOURCE_BYTES = 64
MAX_NETWORK_STATE = 200
MAX_CONNECTIVITY = 10
_SOURCE = re.compile(r"[a-z0-9_.:-]{0,64}\Z")

# Enumerated values returned by GetPermissions / Can* methods. Any other
# string is rejected rather than guessed or rendered into a disclosure.
PERMISSION_TOKENS = frozenset({"yes", "no", "auth", "unknown"})
POWER_TOKENS = frozenset({"yes", "no", "challenge", "na", "unknown"})

# A plan is chosen by a fixed key; service, path, interface, method and bus
# are derived here. Callers never supply D-Bus addresses, object paths,
# method names, shell text or executables.
_PLANS = MappingProxyType({
    "set-brightness": (
        "session", "org.kde.Solid.PowerManagement",
        "/org/kde/Solid/PowerManagement/Actions/BrightnessControl",
        "org.kde.Solid.PowerManagement.Actions.BrightnessControl",
        "setBrightness",
    ),
    "recheck-connectivity": (
        "system", "org.freedesktop.NetworkManager",
        "/org/freedesktop/NetworkManager",
        "org.freedesktop.NetworkManager", "CheckConnectivity",
    ),
    "query-power-capability": (
        "system", "org.freedesktop.login1",
        "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager", "CanSuspend",
    ),
})
PLAN_KEYS = frozenset(_PLANS)


class NativeControlsError(ValueError):
    """Invalid, unbounded, contradictory or untrusted native-control input."""


@dataclass(frozen=True)
class CommandPlan:
    """One exact upstream D-Bus call; never executed by this module."""

    plan_key: str
    args: tuple

    def __post_init__(self):
        if type(self.plan_key) is not str or self.plan_key not in PLAN_KEYS:
            raise NativeControlsError("unsupported command plan")
        if type(self.args) is not tuple or len(self.args) > 2:
            raise NativeControlsError("command arguments must be a small tuple")
        for value in self.args:
            if type(value) is not int:
                raise NativeControlsError("command arguments must be integers")
            if not 0 <= value <= MAX_BRIGHTNESS:
                raise NativeControlsError("command argument exceeds its bound")
        if self.plan_key == "set-brightness":
            if len(self.args) != 1:
                raise NativeControlsError("brightness plan needs one value")
        elif self.args:
            raise NativeControlsError("this plan takes no arguments")

    @property
    def bus(self):
        return _PLANS[self.plan_key][0]

    @property
    def service(self):
        return _PLANS[self.plan_key][1]

    @property
    def object_path(self):
        return _PLANS[self.plan_key][2]

    @property
    def interface(self):
        return _PLANS[self.plan_key][3]

    @property
    def method(self):
        return _PLANS[self.plan_key][4]

    def to_dict(self):
        """Fresh mapping; no argv, command, executable or credential field."""
        return {
            "plan_key": self.plan_key,
            "bus": self.bus,
            "service": self.service,
            "object_path": self.object_path,
            "interface": self.interface,
            "method": self.method,
            "args": tuple(self.args),
            "executed": False,
        }


@dataclass(frozen=True)
class ProbeFacts:
    """Bounded host capability facts. ``None`` means not trusted/probed.

    Every field is an already-normalised token or a small integer. Host error
    strings, object paths and free text are deliberately not accepted: the
    exact observed text belongs in evidence, not in a UI disclosure.
    """

    source: str = "host-probe"
    brightness_supported: Optional[bool] = None
    backlight_device: Optional[bool] = None
    brightness_value: Optional[int] = None
    brightness_max: Optional[int] = None
    connectivity_check_available: Optional[bool] = None
    network_control_permission: Optional[str] = None
    network_state: Optional[int] = None
    connectivity: Optional[int] = None
    power_can_suspend: Optional[str] = None
    power_list_jobs_allowed: Optional[bool] = None

    def __post_init__(self):
        if type(self.source) is not str:
            raise NativeControlsError("probe source must be a string")
        try:
            size = len(self.source.encode("utf-8", "strict"))
        except UnicodeError:
            raise NativeControlsError("invalid probe source encoding") from None
        if not 1 <= size <= MAX_SOURCE_BYTES or not _SOURCE.fullmatch(self.source):
            raise NativeControlsError("invalid probe source")
        for name in ("brightness_supported", "backlight_device",
                     "connectivity_check_available", "power_list_jobs_allowed"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise NativeControlsError(name + " must be a bool or None")
        for name, limit in (("brightness_value", None),
                            ("brightness_max", MAX_BRIGHTNESS),
                            ("network_state", MAX_NETWORK_STATE),
                            ("connectivity", MAX_CONNECTIVITY)):
            value = getattr(self, name)
            if value is not None and type(value) is not int:
                raise NativeControlsError(name + " must be an int or None")
            if value is not None and not 0 <= value:
                raise NativeControlsError(name + " must not be negative")
            if limit is not None and value is not None and value > limit:
                raise NativeControlsError(name + " exceeds its bound")
        if (self.brightness_value is not None
                and self.brightness_max is not None
                and self.brightness_value > self.brightness_max):
            raise NativeControlsError("brightness exceeds its maximum")
        if (self.network_control_permission is not None
                and self.network_control_permission not in PERMISSION_TOKENS):
            raise NativeControlsError("unsupported network permission token")
        if (self.power_can_suspend is not None
                and self.power_can_suspend not in POWER_TOKENS):
            raise NativeControlsError("unsupported power capability token")


@dataclass(frozen=True)
class ControlVerdict:
    """Bounded, immutable verdict for one native control domain."""

    domain: str
    action: str
    execution: str
    reason: str
    plan: Optional[CommandPlan] = None

    def __post_init__(self):
        if type(self.domain) is not str or self.domain not in NATIVE_DOMAINS:
            raise NativeControlsError("invalid native control domain")
        if type(self.action) is not str or not self.action \
                or len(self.action.encode("utf-8", "strict")) > 64:
            raise NativeControlsError("invalid native control action")
        if type(self.execution) is not str \
                or self.execution not in EXECUTION_LABELS:
            raise NativeControlsError("invalid execution label")
        if type(self.reason) is not str or self.reason not in _qcs.DISCLOSURES:
            raise NativeControlsError("invalid control reason")
        if self.plan is not None and type(self.plan) is not CommandPlan:
            raise NativeControlsError("invalid command plan")
        if self.execution == EXECUTION_PASS and (self.plan is None
                                                 or self.reason != _qcs.REASON_OK):
            raise NativeControlsError("PASS requires a completed trusted plan")

    @property
    def label(self):
        return EXECUTION_LABELS[self.execution] + " — " + \
            _qcs.DISCLOSURES[self.reason]

    @property
    def disclosure(self):
        return _qcs.DISCLOSURES[self.reason]

    @property
    def availability(self):
        if self.plan is None or self.execution == EXECUTION_BLOCKED:
            return _qcs.UNAVAILABLE
        return _qcs.AVAILABLE

    def to_dict(self):
        return {
            "domain": self.domain,
            "action": self.action,
            "execution": self.execution,
            "execution_label": EXECUTION_LABELS[self.execution],
            "label": self.label,
            "reason": self.reason,
            "disclosure": self.disclosure,
            "availability": self.availability,
            "plan": self.plan.to_dict() if self.plan is not None else None,
            "executed": False,
        }


class NativeControls:
    """Pure planner; no I/O, execution, polling or retained mutable state."""

    @staticmethod
    def _verdict(domain, action, execution, reason, plan=None):
        return ControlVerdict(domain, action, execution, reason, plan)

    @classmethod
    def brightness_step(cls, delta, facts):
        """Plan a bounded relative brightness step; no absolute target input."""
        if type(facts) is not ProbeFacts:
            raise NativeControlsError("brightness needs trusted probe facts")
        if type(delta) is not int or not -MAX_DELTA <= delta <= MAX_DELTA:
            raise NativeControlsError("brightness delta exceeds its bound")
        action = "brightness-up" if delta > 0 else "brightness-down"
        if delta == 0:
            return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CHANGE)
        if (facts.brightness_supported is None
                or facts.backlight_device is None):
            return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CAPABILITY_PROBE)
        if not facts.brightness_supported or not facts.backlight_device:
            return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_CAPABILITY_ABSENT)
        if facts.brightness_value is None or facts.brightness_max is None:
            return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CAPABILITY_PROBE)
        maximum = facts.brightness_max
        target = min(max(facts.brightness_value + delta, 0), maximum)
        if target == facts.brightness_value:
            return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CHANGE)
        return cls._verdict("brightness", action, EXECUTION_NOT_RUN,
                            _qcs.REASON_OK, CommandPlan("set-brightness",
                                                        (target,)))

    @classmethod
    def network_recheck(cls, facts):
        """Plan one NetworkManager connectivity recheck, if policy allows it."""
        if type(facts) is not ProbeFacts:
            raise NativeControlsError("network needs trusted probe facts")
        action = ACTIONS["network"]
        if (facts.connectivity_check_available is None
                or facts.network_control_permission is None):
            return cls._verdict("network", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CAPABILITY_PROBE)
        # An explicit policy denial is BLOCKED even when the connectivity check
        # itself is also unavailable: that is the observed host condition.
        if facts.network_control_permission in ("auth", "no"):
            return cls._verdict("network", action, EXECUTION_BLOCKED,
                                _qcs.REASON_CAPABILITY_DENIED)
        if not facts.connectivity_check_available \
                or facts.network_control_permission == "unknown":
            return cls._verdict("network", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_CAPABILITY_ABSENT)
        return cls._verdict("network", action, EXECUTION_NOT_RUN,
                            _qcs.REASON_OK,
                            CommandPlan("recheck-connectivity", ()))

    @classmethod
    def power_capability(cls, facts):
        """Plan a read-only logind capability query; never a state transition."""
        if type(facts) is not ProbeFacts:
            raise NativeControlsError("power needs trusted probe facts")
        action = ACTIONS["power"]
        if facts.power_can_suspend is None \
                or facts.power_list_jobs_allowed is None:
            return cls._verdict("power", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_NO_CAPABILITY_PROBE)
        if facts.power_can_suspend in ("na", "no"):
            return cls._verdict("power", action, EXECUTION_NOT_RUN,
                                _qcs.REASON_CAPABILITY_ABSENT)
        if facts.power_can_suspend == "challenge" \
                or not facts.power_list_jobs_allowed:
            return cls._verdict("power", action, EXECUTION_BLOCKED,
                                _qcs.REASON_CAPABILITY_DENIED)
        return cls._verdict("power", action, EXECUTION_NOT_RUN,
                            _qcs.REASON_OK,
                            CommandPlan("query-power-capability", ()))

    @classmethod
    def refuse_transition(cls, action):
        """Privileged transitions are refused independently of any probe."""
        if type(action) is not str or action not in PRIVILEGED_TRANSITIONS:
            raise NativeControlsError("unsupported privileged transition")
        domain = "power"
        return cls._verdict(domain, action, EXECUTION_NOT_RUN,
                            _qcs.REASON_PRIVILEGED_HOST_CHANGE)

    @classmethod
    def host_result(cls, verdict, execution, *, succeeded=False):
        """Fold a trusted host execution result into an existing verdict.

        ``PASS`` is accepted only when the verdict already offered a plan,
        no capability gate was denied and the host reports success. A denied
        or absent capability plan cannot be promoted by a hostile caller.
        """
        if type(verdict) is not ControlVerdict:
            raise NativeControlsError("host result needs a ControlVerdict")
        if type(execution) is not str or execution not in EXECUTION_LABELS \
                or type(succeeded) is not bool:
            raise NativeControlsError("invalid host execution result")
        if execution == EXECUTION_PASS:
            if not succeeded or verdict.plan is None \
                    or verdict.reason != _qcs.REASON_OK:
                raise NativeControlsError("PASS is not proven by this result")
            return replace(verdict, execution=EXECUTION_PASS)
        if execution == EXECUTION_BLOCKED:
            if succeeded or verdict.plan is None:
                raise NativeControlsError("BLOCKED needs an unexecuted plan")
            return replace(verdict, execution=EXECUTION_BLOCKED,
                           reason=_qcs.REASON_CAPABILITY_DENIED)
        if succeeded:
            raise NativeControlsError("NOT_RUN cannot report success")
        if verdict.reason == _qcs.REASON_OK:
            return replace(verdict, reason=_qcs.REASON_NO_CAPABILITY_PROBE)
        return replace(verdict, execution=EXECUTION_NOT_RUN)

    @classmethod
    def session_execution(cls, decision):
        """Read-only NOT_RUN label for an existing privileged session decision."""
        from canopy_features.system.session_controls_native import NativeDecision
        if type(decision) is not NativeDecision:
            raise NativeControlsError("session decision has the wrong type")
        return decision.execution_label
