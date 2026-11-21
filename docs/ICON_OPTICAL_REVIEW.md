# Canopy Classic icon optical review — diagnostic, not final approval

**Why:** The Qt dock asserts that the eight 54×54 image rectangles are
geometrically centered. That test **does not** establish the illustration
inside each user-approved image looks centered. The owner noticed a visible
imbalance after the geometric test passed.

The original eight source PNGs are opaque 345×333/334 crops. They contain
different internal compositions. Never "fix" this by overwriting or
regenerating the SHA-locked originals.

## Measurable artifact

Use the new dependency-free audit with the **exact original master images**
and the manifest in the Classic Qt draft branch:

\`\`\`sh
python3 tools/audit_approved_icon_optics.py \
  --approved-art-dir /path/to/approved-art \
  --manifest /path/to/classic/prototype/classic/assets/approved/manifest.json \
  --output icon-optics-report.json
\`\`\`

The checker verifies SHA-256 for all eight originals and decodes their RGBA
PNG streams without rewriting files. It computes a center of high-contrast
**grayscale edge energy** inside each source image's central ~91%. Positive
offset means edge detail falls to the right or below the geometric center.

This is a **heuristic**, not object segmentation or a replacement for the
owner's visual judgment. Decorative corners, dark gradients, shadows, Tux,
and foreground shapes affect the result. Do **not** automatically crop,
reposition or recolor artwork from these numbers. Any proposed icon-specific
optical adjustments must be distinct, reproducible derivative previews and
approved by reviewing **actual Qt runtime captures** together with 8-source
SHA evidence. User-facing visual changes remain blocked until review.

A complete acceptance pass should include:

- Original SHA-locked icon manifest and digest evidence.
- The optional refined Terminal candidate clearly identified as a derivative.
- Actual compiled Qt screenshots at 760×500, 1200×750 and 1920×1080,
  with a same-scale zoom of the dock and no substituted wallpaper.
- Per-icon visual bounds and spacing observed in a running Qt scene.
- An explicit human visual decision; clean CI and edge-centroid numbers
  are not sufficient.
- A true Linux Mint guest test separately from the Ubuntu CI renderer.

The audit is independent of the unfinished Qt PR #100 and can be used by
the owner's own reviewers or any other contributor without downloading
private user images into GitHub.
