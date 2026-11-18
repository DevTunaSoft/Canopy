# One-script Canopy Windows setup — current capabilities

The entry point is `Canopy-Setup.ps1` at the repository root. It uses Git to fetch or safely fast-forward the reviewed development branch, then invokes the existing host preflight and VM scripts. It is **not** a finished unattended OS installer: independent checksum authentication, guest OS installation, login, SSH enrollment, screenshots and performance tests are still not automated.

Run `.\Canopy-Setup.ps1` for safe host readiness. To provision the VM, pass `-CreateVM -IsoPath <local Mint ISO> -IsoSha256 <independently authenticated 64-digit SHA256>`. Only on a brand-new disposable VM and after validating Mint/VirtualBox compatibility, add `-ConfigureUnattended -PasswordFile <protected password file> -StartVM` to attempt VirtualBox unattended setup and start the VM.

**Safety:** No VM changes by default. The script refuses dirty or unexpected existing Git checkouts, unexpected VM names and missing consent. It does not overwrite an existing VM or disk. GitHub CI only runs the argument self-test; no Windows host or Mint guest has been exercised.

This is a transitional single entry point, not fulfillment of the entire autonomous VM test-lab requirement.

## Download the ISO automatically

Supply a direct HTTPS `.iso` download URL from a trusted Linux Mint mirror using `-IsoUrl` instead of `-IsoPath`. The launcher downloads into `%LOCALAPPDATA%\\CanopyTestLab\\downloads`, checks the complete SHA256 against the independently verified hash supplied with `-IsoSha256`, and only then renames the temporary file to a reusable ISO. A failed or interrupted download is not accepted; an existing ISO with a different checksum is never overwritten. Example:

```powershell
.\\Canopy-Setup.ps1 -CreateVM -IsoUrl 'https://YOUR-TRUSTED-MINT-MIRROR/path/linuxmint-cinnamon.iso' -IsoSha256 'YOUR_VERIFIED_64_DIGIT_SHA256'
```

The URL and checksum shown above are placeholders, not valid release metadata. Retrieve the exact URL and authenticate the release checksum from the official Linux Mint verification instructions. The script does **not yet automatically discover and cryptographically authenticate** release metadata or verify its GPG signature; this is a deliberate fail-closed boundary. This mode provisions VM hardware but does not install Mint unless separately opted in.
