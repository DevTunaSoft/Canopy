from pathlib import Path
import unittest

SCRIPT=(Path(__file__).resolve().parents[1]/"scripts/Enable-CanopyGuestCinnamon.sh").read_text()

class GuestAutoLoginContracts(unittest.TestCase):
    def test_restricted_virtualbox_only(self):
        for value in ("--enable","canopy-test","virtualbox",
                      "ID=linuxmint","cinnamon.desktop","70-canopy-testlab.conf"):
            self.assertIn(value,SCRIPT)
        self.assertIn("Refuse to alter login",SCRIPT)
    def test_no_auto_reboot_or_passwordless_sudo(self):
        for unsafe in ("sudo reboot","systemctl reboot","NOPASSWD","chmod 777",
                       "sudo -S","rm -rf","PasswordAuthentication yes"):
            self.assertNotIn(unsafe,SCRIPT)

if __name__=="__main__":
    unittest.main()
