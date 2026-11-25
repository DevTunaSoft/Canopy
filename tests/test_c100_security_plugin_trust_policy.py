"""Offline unit tests for non-executing extension integrity contracts.

These tests use in-memory bytes only. They never load Shell Packs/QML, start
background work, or touch a real Linux Mint session or compiled Qt binary.
"""

import unittest

from canopy_features.security.plugin_trust_policy import (
    CONTRACT_VERSION,
    MAX_ARTIFACT_BYTES,
    ContractError,
    Decision,
    IntegrityContract,
    TrustPolicy,
    pin,
    verify,
)

SIGNER = "canopy-official"
PAYLOAD = b"extension bytes, treated strictly as data"


class Exploding:
    """Object whose dunders raise if verification tries to run user code."""

    def __len__(self):
        raise AssertionError("verify must not length-check arbitrary objects")

    def __eq__(self, other):
        raise AssertionError("verify must not compare arbitrary objects")


class PluginTrustPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = TrustPolicy(frozenset({SIGNER, "partner-signer"}))

    def test_pin_and_accept(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        self.assertEqual(contract.version, CONTRACT_VERSION)
        result = verify(contract, self.policy, SIGNER, PAYLOAD)
        self.assertIs(result.decision, Decision.ACCEPTED)
        self.assertTrue(result.accepted)

    def test_unknown_signer_rejected(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        result = verify(contract, self.policy, "rogue-signer", PAYLOAD)
        self.assertIs(result.decision, Decision.UNKNOWN_SIGNER)
        self.assertFalse(result.accepted)

    def test_mismatched_digest_rejected(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        result = verify(contract, self.policy, SIGNER, PAYLOAD + b"tampered")
        self.assertIs(result.decision, Decision.DIGEST_MISMATCH)
        self.assertFalse(result.accepted)

    def test_known_but_wrong_signer_rejected(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        result = verify(contract, self.policy, "partner-signer", PAYLOAD)
        self.assertIs(result.decision, Decision.SIGNER_MISMATCH)

    def test_contract_signer_outside_policy_is_unknown(self):
        contract = pin("com.example.clock", "unlisted-signer", PAYLOAD)
        result = verify(contract, self.policy, "unlisted-signer", PAYLOAD)
        self.assertIs(result.decision, Decision.UNKNOWN_SIGNER)

    def test_oversized_artifact_rejected(self):
        big = b"x" * (MAX_ARTIFACT_BYTES + 1)
        with self.assertRaises(ContractError):
            pin("com.example.clock", SIGNER, big)

    def test_oversized_observed_data_rejected(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        result = verify(contract, self.policy, SIGNER, b"x" * (MAX_ARTIFACT_BYTES + 1))
        self.assertIs(result.decision, Decision.OVERSIZED_ARTIFACT)

    def test_arbitrary_objects_are_not_evaluated(self):
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        result = verify(contract, self.policy, SIGNER, Exploding())
        self.assertIs(result.decision, Decision.INVALID_OBSERVATION)
        bad_signer = verify(contract, self.policy, Exploding(), PAYLOAD)
        self.assertIs(bad_signer.decision, Decision.INVALID_OBSERVATION)

    def test_malformed_contract_input_rejected(self):
        self.assertIs(verify(object(), self.policy, SIGNER, PAYLOAD).decision,
                      Decision.MALFORMED_CONTRACT)
        contract = pin("com.example.clock", SIGNER, PAYLOAD)
        self.assertIs(verify(contract, object(), SIGNER, PAYLOAD).decision,
                      Decision.MALFORMED_CONTRACT)

    def test_contract_fields_are_validated(self):
        digest = pin("com.example.clock", SIGNER, PAYLOAD).sha256
        with self.assertRaises(ContractError):
            IntegrityContract("BAD_ID", SIGNER, digest)
        with self.assertRaises(ContractError):
            IntegrityContract("com.example.clock", "Bad Signer", digest)
        with self.assertRaises(ContractError):
            IntegrityContract("com.example.clock", SIGNER, "not-a-digest")
        with self.assertRaises(ContractError):
            IntegrityContract("com.example.clock", SIGNER, digest, version=2)

    def test_trust_policy_requires_frozenset_of_clean_signers(self):
        with self.assertRaises(ContractError):
            TrustPolicy([SIGNER])
        with self.assertRaises(ContractError):
            TrustPolicy(frozenset({"Bad Signer"}))

    def test_payload_is_data_only(self):
        code = b"import os\nos.system('echo executed')\n"
        contract = pin("com.example.clock", SIGNER, code)
        import hashlib
        self.assertEqual(contract.sha256, hashlib.sha256(code).hexdigest())
        self.assertTrue(verify(contract, self.policy, SIGNER, code).accepted)
        self.assertIs(verify(contract, self.policy, SIGNER, code + b"x").decision,
                      Decision.DIGEST_MISMATCH)


if __name__ == "__main__":
    unittest.main()
