"""Offline tests for credential-free guest SSH command validation.

These tests never open a socket, spawn a shell or contact a guest. Host key
failure, timeout and injection are exercised as construction/validation cases.
"""
import json
import unittest

from canopy_features.mint import ssh_noninteractive as ssh

HOST = "mint-guest.local"


def built(subcommand="preflight", **kwargs):
    return ssh.build_ssh_command(HOST, subcommand, **kwargs)


def without_option(argv, key):
    """Remove every -o <key>=... pair from an argv (test helper)."""
    out = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-o" and i + 1 < len(argv) \
                and argv[i + 1].startswith(key + "="):
            i += 2
            continue
        if token.startswith("-o") and token[2:].startswith(key + "="):
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def with_option(argv, key, value):
    """Replace the value of an -o <key>=... option (test helper)."""
    prefix = key + "="
    out = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-o" and i + 1 < len(argv) \
                and argv[i + 1].startswith(prefix):
            out.extend(("-o", prefix + value))
            i += 2
            continue
        if token.startswith("-o") and token[2:].startswith(prefix):
            out.append("-o" + prefix + value)
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def replace_token(argv, old, new):
    return [new if token == old else token for token in argv]


class BuilderTests(unittest.TestCase):
    def test_build_uses_only_safe_argv_shape(self):
        for sub in ssh.ALLOWED_SUBCOMMANDS:
            with self.subTest(subcommand=sub):
                argv = built(sub)
                self.assertEqual(argv[0], "ssh")
                self.assertIn("BatchMode=yes", argv)
                self.assertIn("StrictHostKeyChecking=yes", argv)
                self.assertIn(
                    "UserKnownHostsFile=" + ssh.KNOWN_HOSTS_PATH, argv)
                self.assertTrue(any(a.startswith("ConnectTimeout=")
                                    for a in argv))
                self.assertEqual(argv[-2:], [ssh.GUEST_SCRIPT, sub])

    def test_builder_rejects_unsafe_host(self):
        for host in ("", "-evil", "a;b", "user@host", "host name",
                     "x" * 300, None, 7):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    ssh.build_ssh_command(host, "preflight")

    def test_builder_rejects_unlisted_subcommand(self):
        for sub in ("", "rm -rf /", "../script", "preflight;id", None):
            with self.subTest(subcommand=sub):
                with self.assertRaises(ValueError):
                    ssh.build_ssh_command(HOST, sub)

    def test_builder_rejects_bad_timeout_and_known_hosts(self):
        for timeout in (0, -1, ssh.MAX_CONNECT_TIMEOUT + 1, "10", True, None):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    ssh.build_ssh_command(HOST, "preflight", timeout=timeout)
        for path in ("/dev/null", "relative/path", "/etc/x;y", None, ""):
            with self.subTest(known_hosts=path):
                with self.assertRaises(ValueError):
                    ssh.build_ssh_command(HOST, "preflight", known_hosts=path)

    def test_timeout_boundary_is_accepted(self):
        argv = built(timeout=ssh.MAX_CONNECT_TIMEOUT)
        self.assertEqual(
            ssh.validate_ssh_command(argv)["connect_timeout_seconds"],
            ssh.MAX_CONNECT_TIMEOUT)


class ValidatorSafeTests(unittest.TestCase):
    def test_safe_roundtrip_for_every_subcommand(self):
        for sub in ssh.ALLOWED_SUBCOMMANDS:
            with self.subTest(subcommand=sub):
                report = ssh.validate_ssh_command(built(sub))
                self.assertEqual(report["status"], "SAFE")
                self.assertEqual(report["reasons"], [])
                self.assertTrue(report["binary_checked"])
                self.assertTrue(report["destination_valid"])
                self.assertTrue(report["non_interactive"])
                self.assertEqual(report["host_key_verification"], "required")
                self.assertEqual(report["connect_timeout_seconds"],
                                 ssh.DEFAULT_TIMEOUT)
                self.assertTrue(report["remote_command_allowed"])
                self.assertTrue(report["credential_free"])

    def test_host_allowlist_is_exact(self):
        self.assertEqual(
            ssh.validate_ssh_command(built(), allowed_hosts={HOST})["status"],
            "SAFE")
        report = ssh.validate_ssh_command(built(), allowed_hosts={"other.local"})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any("allowlist" in r for r in report["reasons"]))

    def test_validation_is_pure_and_deterministic(self):
        first = ssh.validate_ssh_command(built())
        second = ssh.validate_ssh_command(built())
        self.assertEqual(first, second)
        self.assertFalse(hasattr(ssh, "subprocess"))
        self.assertFalse(hasattr(ssh, "socket"))

    def test_malformed_shapes_are_blocked_without_raising(self):
        for argv in (None, "", [], ["ssh"], [1, 2], ["ssh", object()]):
            with self.subTest(argv=argv):
                report = ssh.validate_ssh_command(argv)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertTrue(report["reasons"])

    def test_option_may_be_joined_or_separated(self):
        argv = built()
        joined = []
        i = 0
        while i < len(argv):
            if argv[i] == "-o" and i + 1 < len(argv):
                joined.append("-o" + argv[i + 1])
                i += 2
                continue
            joined.append(argv[i])
            i += 1
        self.assertEqual(ssh.validate_ssh_command(joined)["status"], "SAFE")


class HostKeyTests(unittest.TestCase):
    def test_host_key_failure_cannot_be_bypassed(self):
        base = built()
        variants = {
            "missing": without_option(base, "StrictHostKeyChecking"),
            "no": with_option(base, "StrictHostKeyChecking", "no"),
            "accept_new": with_option(base, "StrictHostKeyChecking",
                                      "accept-new"),
            "off": with_option(base, "StrictHostKeyChecking", "off"),
            "ask": with_option(base, "StrictHostKeyChecking", "ask"),
            "known_hosts_dev_null": with_option(
                base, "UserKnownHostsFile", "/dev/null"),
            "known_hosts_unpinned": without_option(base, "UserKnownHostsFile"),
        }
        for name, argv in variants.items():
            with self.subTest(variant=name):
                report = ssh.validate_ssh_command(argv)
                self.assertEqual(report["status"], "BLOCKED", name)
                self.assertTrue(any("host key" in r.lower()
                                    for r in report["reasons"]), name)
                self.assertNotEqual(report["host_key_verification"], "required")

    def test_safe_construction_keeps_strict_host_key_checking(self):
        self.assertIn("StrictHostKeyChecking=yes", built())
        self.assertEqual(
            ssh.validate_ssh_command(built())["host_key_verification"],
            "required")


class TimeoutTests(unittest.TestCase):
    def test_bad_timeout_is_blocked(self):
        base = built()
        variants = {
            "missing": without_option(base, "ConnectTimeout"),
            "nonnumeric": with_option(base, "ConnectTimeout", "abc"),
            "zero": with_option(base, "ConnectTimeout", "0"),
            "negative": with_option(base, "ConnectTimeout", "-1"),
            "above_bound": with_option(
                base, "ConnectTimeout", str(ssh.MAX_CONNECT_TIMEOUT + 1)),
            "huge": with_option(base, "ConnectTimeout", "999999999"),
        }
        for name, argv in variants.items():
            with self.subTest(variant=name):
                report = ssh.validate_ssh_command(argv)
                self.assertEqual(report["status"], "BLOCKED", name)
                self.assertTrue(any("timeout" in r.lower()
                                    for r in report["reasons"]), name)

    def test_custom_lower_bound_is_enforced(self):
        argv = built(timeout=12)
        self.assertEqual(
            ssh.validate_ssh_command(argv, max_timeout=10)["status"],
            "BLOCKED")
        self.assertEqual(
            ssh.validate_ssh_command(argv, max_timeout=12)["status"],
            "SAFE")


class InjectionTests(unittest.TestCase):
    def test_injection_vectors_are_blocked(self):
        base = built()
        cases = {
            "shell_wrapper": ["sh", "-c", "ssh " + HOST],
            "sshpass": ["sshpass", "-p", "secret"] + base[1:],
            "host_semicolon": replace_token(
                base, HOST, HOST + "; rm -rf /"),
            "host_newline": replace_token(base, HOST, HOST + "\nid"),
            "host_nul": replace_token(base, HOST, HOST + "\0id"),
            "host_dash": replace_token(base, HOST, "-evil-host"),
            "command_semicolon": replace_token(
                base, "preflight", "preflight; rm -rf /"),
            "command_substitution": replace_token(
                base, "preflight", "$(id)"),
            "command_backtick": replace_token(base, "preflight", "`id`"),
            "command_pipe": replace_token(base, "preflight", "preflight|id"),
            "extra_remote_token": base + ["&&", "echo", "pwned"],
            "arbitrary_remote_script": replace_token(
                base, ssh.GUEST_SCRIPT, "/bin/sh"),
        }
        for name, argv in cases.items():
            with self.subTest(vector=name):
                report = ssh.validate_ssh_command(argv)
                self.assertEqual(report["status"], "BLOCKED", name)
                self.assertTrue(report["reasons"])

    def test_credential_and_exec_options_are_blocked(self):
        base = built()
        host_index = base.index(HOST)
        cases = {
            "identity_file": base[:host_index] + ["-i", "/secret/key"]
                             + base[host_index:],
            "config_file": base[:host_index] + ["-F", "/tmp/evil"]
                           + base[host_index:],
            "agent_forward": base[:host_index] + ["-A"] + base[host_index:],
            "proxy_command": base[:host_index]
                             + ["-o", "ProxyCommand=/bin/sh -c id"]
                             + base[host_index:],
            "local_command": base[:host_index]
                             + ["-o", "LocalCommand=id"]
                             + base[host_index:],
            "joined_identity": base[:host_index]
                               + ["-oIdentityFile=/secret/key"]
                               + base[host_index:],
        }
        for name, argv in cases.items():
            with self.subTest(vector=name):
                report = ssh.validate_ssh_command(argv)
                self.assertEqual(report["status"], "BLOCKED", name)
                self.assertFalse(report["credential_free"], name)

    def test_credential_environment_is_blocked_and_never_echoed(self):
        for name in ("SSH_ASKPASS", "SSH_AUTH_SOCK", "CANOPY_SSH_PASSWORD"):
            with self.subTest(env=name):
                report = ssh.validate_ssh_command(built(), env={name: "s3cr3t"})
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["credential_free"])
                serialized = json.dumps(report)
                self.assertNotIn("s3cr3t", serialized)
                self.assertNotIn(name, serialized)
                self.assertNotIn(HOST, serialized)
                self.assertNotIn(ssh.GUEST_SCRIPT, serialized)

    def test_report_never_echoes_argv_tokens(self):
        report = ssh.validate_ssh_command(
            built(), allowed_hosts={"other.local"})
        serialized = json.dumps(report)
        self.assertNotIn(HOST, serialized)
        self.assertNotIn(ssh.GUEST_SCRIPT, serialized)
        self.assertNotIn("BatchMode=yes", serialized)


if __name__ == "__main__":
    unittest.main()
