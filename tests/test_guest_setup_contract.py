"""Guest setup security contract; doesn't run apt on CI."""
from pathlib import Path
import unittest
FILE = Path(__file__).resolve().parents[1]/"scripts/setup-mint-guest.sh"
class GuestSetupContracts(unittest.TestCase):
    def test_unprivileged_dedicated_account(self):
        s=FILE.read_text()
        for part in ('ID=linuxmint','canopy-test','ssh-ed25519','sudo -v',
                     'PasswordAuthentication no','PermitRootLogin no',
                     'sudo /usr/sbin/sshd -t','--no-install-recommends'):
            self.assertIn(part,s)
    def test_no_insecure_remote_access(self):
        s=FILE.read_text()
        for forbidden in ("NOPASSWD","PasswordAuthentication yes","PermitRootLogin yes",
                          "curl | bash","chmod 777","StrictHostKeyChecking=no","0.0.0.0:2222"):
            self.assertNotIn(forbidden,s)
if __name__=="__main__":
    unittest.main()
