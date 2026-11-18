# Independent track B — PNG evidence validation

`scripts/validate_visual.py` checks that Canopy's two isolated Xvfb image artifacts have valid PNG signature/chunk CRCs, a complete IEND and structurally correct size metadata. It rejects mislabeled roles, unexpected filenames, mismatched dimensions and oversized images. This is an inexpensive, standard-library verification gate; it **does not compare screenshots to approved images, assess appearance or guarantee screenshot privacy**.

Run on a trusted isolated screenshot directory:
```bash
python3 scripts/validate_visual.py --directory test-results/visual
```

This track does not edit UI, memory instrumentation or Mint worker approval code, allowing isolated development. Tests use synthetic PNGs, not Mint output. After safe integration, add this check to GTK CI after capture and prior to artifact upload, then review images manually or establish validated visual baselines. No Mint VM or Cinnamon verification completed.


## 2026-11-18 — CI integration checkpoint

The existing Linux GTK/Xvfb workflow now runs `scripts/validate_visual.py` immediately after `scripts/capture_classic.py`. A corrupt screenshot, missing window, CRC failure or mismatched dimensions will cause the GTK job to fail; the artifact-upload step remains `if: always()` to retain diagnostic files. This is **structural validation**, not pixel/visual correctness or Linux Mint session acceptance. Future work: review real rendered screenshot content, establish approved baselines and add perceptual comparisons with explicit tolerance before calling the visual design verified. No full-screen capture or host access is added.

GitHub CI results must be verified against the latest branch SHA. No Mint VM exists yet.
