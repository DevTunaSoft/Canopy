"""Offline builder and validator for credential-free guest SSH commands.

Canopy needs to run a fixed verification script inside a Linux Mint guest.
This module constructs and validates the argv for that single narrow task.
It never opens a socket, never handles credentials, and never invokes a shell.

The SAFE contract is strict and fail-closed:
  * binary is ``ssh`` (no shell wrapper, no sshpass);
  * ``BatchMode=yes`` so no password or passphrase prompt can appear;
  * ``StrictHostKeyChecking=yes`` pinned to a real known-hosts file;
  * ``ConnectTimeout`` is a positive integer within a bounded maximum;
  * no identity, agent, config-file, proxy or local-command options;
  * destination is a bare validated host, optionally checked against an allowlist;
  * remote command is exactly GUEST_SCRIPT plus one allowlisted subcommand.

The report contains only categorical flags and generic reasons. It never
echoes argv tokens, hosts, paths or environment values.
"""

import os
import re

__all__ = [
    "SSH_BINARY",
    "GUEST_SCRIPT",
    "ALLOWED_SUBCOMMANDS",
    "DEFAULT_TIMEOUT",
    "MAX_CONNECT_TIMEOUT",
    "KNOWN_HOSTS_PATH",
    "build_ssh_command",
    "validate_ssh_command",
]

SSH_BINARY = "ssh"
GUEST_SCRIPT = "/usr/local/bin/canopy-guest-check"
ALLOWED_SUBCOMMANDS = ("preflight", "qt-smoke", "shell-smoke")
DEFAULT_TIMEOUT = 10
MAX_CONNECT_TIMEOUT = 30
KNOWN_HOSTS_PATH = "/etc/ssh/ssh_known_hosts"

_ALLOWED_OPTION_KEYS = frozenset({
    "batchmode", "stricthostkeychecking", "connecttimeout",
    "userknownhostsfile",
})
_FORBIDDEN_OPTION_KEYS = frozenset({
    "identityfile", "identityagent", "certificatefile", "forwardagent",
    "proxycommand", "localcommand", "permitlocalcommand",
})
_CREDENTIAL_ENV = (
    "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SSH_AUTH_SOCK",
    "SSH_PASSWORD", "CANOPY_SSH_PASSWORD",
)

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,253}$")
_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]{1,253}$")
_UNSAFE_CHARS = frozenset(";&|`$()<>*?[]{}!#\\'\";\n\r\t\0")


def _unsafe_token(token):
    """True for non-str, empty, oversized or shell/hostile argv tokens."""
    if not isinstance(token, str) or not token or len(token) > 1024:
        return True
    return any(ord(c) < 32 or ord(c) == 127 or c in _UNSAFE_CHARS
               for c in token)


def build_ssh_command(host, subcommand, *,
                      known_hosts=KNOWN_HOSTS_PATH,
                      timeout=DEFAULT_TIMEOUT):
    """Build the one safe argv shape this component permits.

    Raises ValueError for any input that would break the SAFE contract.
    No command is executed and no credential material is accepted.
    """
    if not isinstance(host, str) or not _HOST_RE.match(host):
        raise ValueError("invalid guest host")
    if subcommand not in ALLOWED_SUBCOMMANDS:
        raise ValueError("subcommand not allowlisted")
    if (isinstance(timeout, bool) or not isinstance(timeout, int)
            or not 1 <= timeout <= MAX_CONNECT_TIMEOUT):
        raise ValueError("connect timeout out of bounds")
    if (not isinstance(known_hosts, str)
            or not _PATH_RE.match(known_hosts)
            or _unsafe_token(known_hosts)
            or known_hosts in ("/dev/null", "/nonexistent")):
        raise ValueError("invalid known-hosts path")
    return [
        SSH_BINARY,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=%d" % timeout,
        "-o", "UserKnownHostsFile=" + known_hosts,
        host, "--", GUEST_SCRIPT, subcommand,
    ]


def _report(reasons, **flags):
    """Build a deterministic, non-sensitive validation report."""
    report = {
        "schema_version": 1,
        "component": "mint_ssh_noninteractive",
        "status": "BLOCKED" if reasons else "SAFE",
        "binary_checked": False,
        "destination_valid": False,
        "non_interactive": False,
        "host_key_verification": "unknown",
        "connect_timeout_seconds": None,
        "remote_command_allowed": False,
        "credential_free": False,
        "reasons": sorted(set(reasons)),
    }
    report.update(flags)
    return report


def _store_option(options, value, reasons):
    if "=" not in value:
        reasons.append("malformed ssh option")
        return
    key, val = value.split("=", 1)
    key = key.lower()
    if key in options:
        reasons.append("duplicate ssh option")
        return
    options[key] = val
    if key in _FORBIDDEN_OPTION_KEYS:
        reasons.append("credential or command execution option not allowed")


def validate_ssh_command(argv, *, allowed_hosts=None,
                         max_timeout=MAX_CONNECT_TIMEOUT, env=None):
    """Validate a proposed SSH argv against the SAFE contract.

    Pure and offline: no subprocess, no network, no filesystem access.
    ``allowed_hosts`` is an optional exact-match container of bare hosts.
    ``env`` is an optional mapping checked for credential sources.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        return _report(["empty or non-sequence argv"])
    if any(_unsafe_token(token) for token in argv):
        return _report(["unsafe character in argv token"])
    if os.path.basename(argv[0]) != SSH_BINARY:
        return _report(["binary is not ssh"], binary_checked=True)

    env = env if isinstance(env, dict) else {}
    if not isinstance(max_timeout, int) or isinstance(max_timeout, bool) \
            or max_timeout < 1:
        max_timeout = MAX_CONNECT_TIMEOUT
    reasons = []

    # Environment credential sources are checked before argv parsing so a
    # caller cannot pass an askpass helper outside the argv list.
    if any(env.get(name) for name in _CREDENTIAL_ENV):
        reasons.append("credential source present in environment")

    options = {}
    positional = []
    remote = []
    i = 1
    ended = False
    while i < len(argv):
        token = argv[i]
        if token == "--" and not ended:
            ended = True
            i += 1
            continue
        if ended:
            remote.append(token)
            i += 1
            continue
        if token == "-o" or (token.startswith("-o") and len(token) > 2):
            if token == "-o":
                if i + 1 >= len(argv):
                    reasons.append("-o without value")
                    break
                _store_option(options, argv[i + 1], reasons)
                i += 2
            else:
                _store_option(options, token[2:], reasons)
                i += 1
        elif token in ("-i", "-F", "-f"):
            reasons.append("identity or config file option not allowed")
            i += 2 if i + 1 < len(argv) else 1
        elif token in ("-A", "-a"):
            reasons.append("agent forwarding option not allowed")
            i += 1
        elif token.startswith("-"):
            reasons.append("unsupported ssh option")
            i += 1
        else:
            positional.append(token)
            i += 1

    for key in options:
        if key not in _ALLOWED_OPTION_KEYS and key not in _FORBIDDEN_OPTION_KEYS:
            reasons.append("unsupported ssh option")

    batch = options.get("batchmode")
    non_interactive = batch == "yes"
    if not non_interactive:
        reasons.append("interactive or credential prompt not disabled")

    known_hosts = options.get("userknownhostsfile")
    known_hosts_bad = (known_hosts is None
                       or known_hosts in ("", "none", "/dev/null"))
    if known_hosts is None:
        reasons.append("host key cannot be verified: known-hosts file not pinned")
    elif known_hosts in ("", "none", "/dev/null"):
        reasons.append("host key cannot be verified: known-hosts file disabled")

    host_key = options.get("stricthostkeychecking")
    if host_key is None:
        host_key_state = "missing"
        reasons.append("host key verification not required")
    elif host_key != "yes":
        host_key_state = "disabled"
        reasons.append("host key verification disabled")
    elif known_hosts_bad:
        # StrictHostKeyChecking=yes cannot verify anything without a file.
        host_key_state = "unverifiable"
    else:
        host_key_state = "required"

    timeout_state = None
    raw_timeout = options.get("connecttimeout")
    if raw_timeout is None or not raw_timeout.isdigit():
        reasons.append("connect timeout missing or invalid")
    else:
        timeout_state = int(raw_timeout)
        if timeout_state < 1:
            reasons.append("connect timeout not positive")
        elif timeout_state > max_timeout:
            reasons.append("connect timeout exceeds bound")

    if positional:
        destination = positional[0]
        remote_command = positional[1:] + remote
        if len(positional) > 1:
            reasons.append("unexpected extra positional token")
    elif remote:
        destination = remote[0]
        remote_command = remote[1:]
    else:
        destination = None
        remote_command = []

    destination_valid = False
    if destination is None:
        reasons.append("no ssh destination")
    elif not _HOST_RE.match(destination):
        reasons.append("invalid ssh destination")
    elif (allowed_hosts is not None
          and (not isinstance(allowed_hosts, (set, frozenset, list, tuple))
               or destination not in allowed_hosts)):
        reasons.append("destination not in allowlist")
    else:
        destination_valid = True

    remote_allowed = (len(remote_command) == 2
                      and remote_command[0] == GUEST_SCRIPT
                      and remote_command[1] in ALLOWED_SUBCOMMANDS)
    if not remote_allowed:
        reasons.append("remote command not allowlisted")

    credential_free = (
        non_interactive
        and not any(key in _FORBIDDEN_OPTION_KEYS for key in options)
        and not any(env.get(name) for name in _CREDENTIAL_ENV)
        and "-i" not in argv and "-F" not in argv and "-f" not in argv
        and "-A" not in argv and "-a" not in argv
    )

    return _report(
        reasons,
        binary_checked=True,
        destination_valid=destination_valid,
        non_interactive=non_interactive,
        host_key_verification=host_key_state,
        connect_timeout_seconds=timeout_state,
        remote_command_allowed=remote_allowed,
        credential_free=credential_free,
    )
