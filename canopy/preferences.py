"""Validated, unprivileged Canopy preferences and cosmetic feature resolution."""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
import fcntl
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
    classic_pins: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Preferences":
        if not isinstance(data, dict):
            raise ValueError("Unknown preference fields")
        version = data.get("version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("Unsupported settings version")
        fields = {"version", "layout", "profile", "auto_mode", "overrides"}
        if version == 2:
            fields.add("classic_pins")
        if set(data) - fields:
            raise ValueError("Unknown preference fields")
        if type(data.get("auto_mode", True)) is not bool:
            raise ValueError("Invalid auto_mode")
        raw = data.get("overrides", {})
        if not isinstance(raw, dict) or set(raw) - FEATURES:
            raise ValueError("Invalid feature overrides")
        pins = data.get("classic_pins")
        if pins is not None:
            if not isinstance(pins, list) or len(pins) > 64:
                raise ValueError("Select no more than 64 pinned applications")
            invalid_id = any(
                not isinstance(pin, str)
                or not pin.endswith(".desktop")
                or len(pin) > 255
                or not pin.isprintable()
                for pin in pins
            )
            if invalid_id or len(pins) != len(set(pins)):
                raise ValueError("Invalid Classic dock pins")
        return cls(layout=Layout(data.get("layout", "classic")),
                   profile=Profile(data.get("profile", "balanced")),
                   auto_mode=data.get("auto_mode", True),
                   overrides={key: Override(raw.get(key, "auto")) for key in FEATURES},
                   classic_pins=list(pins) if pins is not None else None)

    def to_dict(self) -> dict:
        return {"version": 2, "layout": self.layout.value, "profile": self.profile.value,
                "auto_mode": self.auto_mode,
                "overrides": {k: self.overrides[k].value for k in sorted(FEATURES)},
                "classic_pins": self.classic_pins}

def user_settings_path() -> Path:
    """Locate settings using the XDG config directory rules."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", ""))
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "canopy" / "settings.json"


def load(path: Path) -> Preferences:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return Preferences.from_dict(json.load(stream))
    except FileNotFoundError:
        return Preferences()

@contextmanager
def _settings_lock(path: Path):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + '.lock')
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def save(path: Path, preferences: Preferences) -> None:
    """Serialize writers and atomically replace unprivileged settings."""
    validated = Preferences.from_dict(preferences.to_dict())
    with _settings_lock(path):
        _save_unlocked(Path(path), validated)


def update_classic_pins(path: Path, expected_pins: list[str] | None,
                        pins: list[str]) -> Preferences:
    """Preserve concurrent settings edits and reject a stale dock editor."""
    with _settings_lock(path):
        current = load(path)
        if current.classic_pins != expected_pins:
            raise ValueError('Dock pins changed elsewhere; reopen the editor')
        updated = replace(current, classic_pins=list(pins))
        validated = Preferences.from_dict(updated.to_dict())
        _save_unlocked(Path(path), validated)
        return validated


def _save_unlocked(path: Path, preferences: Preferences) -> None:
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".canopy-", delete=False) as stream:
            temp_name = stream.name
            os.chmod(temp_name, 0o600)
            json.dump(preferences.to_dict(), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
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
