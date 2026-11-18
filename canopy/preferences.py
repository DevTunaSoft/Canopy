"""Validated, unprivileged Canopy preferences and cosmetic feature resolution."""
from dataclasses import dataclass, field
from enum import Enum
import json
import os
from pathlib import Path
import tempfile

class Profile(str, Enum):
    ULTRA_LITE = "ultra_lite"
    EFFICIENT = "efficient"
    BALANCED = "balanced"
    ENHANCED = "enhanced"
    ULTIMATE = "ultimate"

class Override(str, Enum):
    AUTO = "auto"
    ON = "on"
    OFF = "off"

class Layout(str, Enum):
    CLASSIC = "classic"
    MODERN = "modern"

FEATURES = frozenset({"animations", "transparency", "dock_magnification"})

@dataclass
class Preferences:
    layout: Layout = Layout.CLASSIC
    profile: Profile = Profile.BALANCED
    auto_mode: bool = True
    overrides: dict[str, Override] = field(default_factory=lambda: {k: Override.AUTO for k in FEATURES})

    @classmethod
    def from_dict(cls, data: dict) -> "Preferences":
        if not isinstance(data, dict) or set(data) - {"version", "layout", "profile", "auto_mode", "overrides"}:
            raise ValueError("Unknown preference fields")
        if data.get("version", 1) != 1 or type(data.get("auto_mode", True)) is not bool:
            raise ValueError("Unsupported version or invalid auto_mode")
        raw = data.get("overrides", {})
        if not isinstance(raw, dict) or set(raw) - FEATURES:
            raise ValueError("Invalid feature overrides")
        return cls(layout=Layout(data.get("layout", "classic")),
                   profile=Profile(data.get("profile", "balanced")),
                   auto_mode=data.get("auto_mode", True),
                   overrides={key: Override(raw.get(key, "auto")) for key in FEATURES})

    def to_dict(self) -> dict:
        return {"version": 1, "layout": self.layout.value, "profile": self.profile.value,
                "auto_mode": self.auto_mode,
                "overrides": {k: self.overrides[k].value for k in sorted(FEATURES)}}

def load(path: Path) -> Preferences:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return Preferences.from_dict(json.load(stream))
    except FileNotFoundError:
        return Preferences()

def save(path: Path, preferences: Preferences) -> None:
    """Atomic, user-owned file replacement; no privileged operations."""
    path = Path(path)
    validated = Preferences.from_dict(preferences.to_dict())
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".canopy-", delete=False) as stream:
            temp_name = stream.name
            os.chmod(temp_name, 0o600)
            json.dump(validated.to_dict(), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)

def effective_features(preferences: Preferences, *, battery_saver: bool = False,
                       memory_pressure: bool = False, reduced_motion: bool = False) -> dict[str, bool]:
    """Resolve optional effects; accessibility overrides cosmetic settings."""
    level = {Profile.ULTRA_LITE: 0, Profile.EFFICIENT: 1,
             Profile.BALANCED: 2, Profile.ENHANCED: 3, Profile.ULTIMATE: 4}[preferences.profile]
    if preferences.auto_mode and (battery_saver or memory_pressure):
        level = min(level, 1 if battery_saver else 0)
    thresholds = {"animations": 2, "transparency": 3, "dock_magnification": 4}
    result = {}
    for name, threshold in thresholds.items():
        override = preferences.overrides[name]
        result[name] = (level >= threshold if override is Override.AUTO else override is Override.ON)
    if reduced_motion:
        result["animations"] = False
        result["dock_magnification"] = False
    return result
