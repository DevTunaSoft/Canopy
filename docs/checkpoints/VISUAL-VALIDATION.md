# Independent track B — PNG evidence validation

`scripts/validate_visual.py` checks that Canopy's two isolated Xvfb image artifacts have valid PNG signature/chunk CRCs, a complete IEND and structurally correct size metadata. It rejects mislabeled roles, unexpected filenames, mismatched dimensions and oversized images. This is an inexpensive, standard-library verification gate; it **does not compare screenshots to approved images, assess appearance or guarantee screenshot privacy**.

Run on a trusted isolated screenshot directory:
```bash
python3 scripts/validate_visual.py --directory test-results/visual
```

This track does not edit UI, memory instrumentation or Mint worker approval code, allowing isolated development. Tests use synthetic PNGs, not Mint output. After safe integration, add this check to GTK CI after capture and prior to artifact upload, then review images manually or establish validated visual baselines. No Mint VM or Cinnamon verification completed.
