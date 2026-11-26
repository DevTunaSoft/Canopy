# License and redistribution notices (alpha package)

Status at integration pin `90dd463dc96d70bae00cfe4b2391784a86fb0b12`: the
repository contains **no top-level LICENSE, COPYING or NOTICE file**. This
package therefore makes **no claim** that Canopy source, compiled artifacts or
documentation may be redistributed under any particular license. The owner
must supply an authoritative license notice before any public release or
artifact publication. Until then this tarball is an internal engineering
candidate only.

Component notices:

- Package scripts (`alphactl.py`, `build_package.py`) are original project
  code written for this workstream and use only the Python 3 standard
  library (PSF License). They add no third-party Python dependency.
- Qt is **not bundled**. The compiled candidate, when present, expects Qt
  libraries provided by the target system; those libraries are governed by
  their own Qt licenses (LGPLv3 or GPLv3 as applicable to the build). No Qt
  runtime is copied into this tarball and no Qt license grant is implied.
- Canopy's approved iconography and wallpapers are deliberately **not
  packaged** by this alpha. No visual asset is edited, regenerated or
  redistributed by this workstream.
- No fonts, sounds, themes, proprietary artwork or trademarks are included.
- `CHECKSUMS.sha256` and `MANIFEST.json` are integrity metadata only; they
  are not signatures and do not establish provenance or a license grant.

No warranty is given. Alpha status means unverified on native Linux Mint;
see `docs/ALPHA_PACKAGE_DESIGN.md` for the full limitations list.
