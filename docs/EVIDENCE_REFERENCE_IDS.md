# Private evidence reference IDs

ND-050 replaced operator host paths in public docs/config with repo-relative
identifiers. Identifiers below are **not** repository files: private artifacts
remain outside the public tree. `sha256` is computed from the artifact bytes on
the operator's private tree at remediation time; `NOT_ON_DISK` means the
historical artifact was absent and no digest is invented. Historical SHA-256
claims already printed in the citing document remain authoritative for those
older captures. No host account name or absolute host path is published.

| Repo-relative evidence ID | SHA-256 (artifact bytes) |
|---|---|
| `<repo-root>` | n/a (repository tree, not a private artifact) |
| `private-evidence/downloads/Canopy_Tux_Transparent_Icons.zip` | `d84916fbe66f05821167c73b3fa5bde1a039547fb6f5d7969c666b1f2457415d` |
| `private-evidence/scratch/canopy-645-closure/full-discover.log` | `bb42b0225a3aa7b34ad6718b9e368cf4d896a0b37ce47b75251b7560e851e995` |
| `private-evidence/scratch/canopy-classic-release` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-classic-release-9cf39eb` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-docs-dcb41bd-suite.log` | `652fa17a90d05bbfcc31bfae0e0efd984bd964c50cc2f03f2b918193445afb4a` |
| `private-evidence/scratch/canopy-docs-dcb41bd/foundation.txt` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| `private-evidence/scratch/canopy-pin-base-9cf39eb` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-pin-fix-9cf39eb` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-qc-compile-a3327fb` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-qc-harness` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-qc-host-build` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy-qc-host-build/.qt/.qmlls.build.ini` | `ee19f17c548e9f9ebf083c90ae93a7aff1735397dd585204ee48a3dafda6d9e1` |
| `private-evidence/scratch/canopy-wallpaper-build/canopy-classic-spike.exe` | `39fd61d014945f8d041b66c4e4b34d754e6fce942cece7c4b61b14c3bcaa6b3a` |
| `private-evidence/scratch/canopy_integrator.lock` | `c0d580f884b0d63a5d6fd6fb3ad1525de430748d94a39c58f98d06476f37d903` |
| `private-evidence/scratch/canopy_integrator.py` | `782822f9d3280d8e4b550d84f5f97003e838de373dfa191c85f3953f74df1a38` |
| `private-evidence/scratch/canopy_integrator_restart.log` | `a09e6690454195b1cc88a75d4f79b045d0cc95d9e07414623b7fe5301e2a610c` |
| `private-evidence/scratch/canopy_launcher_catalog_build/canopy-classic-spike.exe` | `8250e8a44733cf3c781ec7ccdfe8ad529ee6513127c7859b144cb2e9884008a0` |
| `private-evidence/scratch/canopy_launcher_targeted_evidence.txt` | `7638bd5159caa2c1e7dc1cd397b34b9d19fe87666e1957eaf81b112154942407` |
| `private-evidence/scratch/canopy_master_supplemental_directive_20261126.md` | `f3ec49fba9317c01354dbd34cf1c5cfedb2625b604f25117c720ae0f44781eae` |
| `private-evidence/scratch/canopy_owner_icons_build/canopy-classic-spike.exe` | `085a9ea0bfb795993b8e589701940c81bac745332c44870ea60ccbbceed95f28` |
| `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-1200x750.png` | `f404ef3ff52cef7d31a344672a27ea503f481ef45343b2b4299b14c197b3b8c3` |
| `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-1920x1080.png` | `2837b41d18e6dfc83f5965bbe6faaebae5e3ba272fdc2f3424a34c601352fd63` |
| `private-evidence/scratch/canopy_owner_icons_evidence/final/owner-icons-760x500.png` | `2afbb80123d4070362e8401afda20aad4304f57be111a57a526f6aef2c1c8ba6` |
| `private-evidence/scratch/canopy_perf_clean_128c973` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy_pr626_docs_tests_128c973.txt` | `826b21837bb7667e186a93856dca3c9dc3b8f0e9af3ea130a764f9b6f7062bdf` |
| `private-evidence/scratch/canopy_pr626_foundation_128c973.txt` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| `private-evidence/scratch/canopy_pr626_refresh_128c973` | `NOT_ON_DISK` |
| `private-evidence/scratch/canopy_quick_status_af97e11` | `NOT_ON_DISK` |
| `private-evidence/scratch/consolidated-compiled-84684a0/evidence` | `NOT_ON_DISK` |
| `private-evidence/scratch/consolidated-compiled-84684a0/gate.log` | `cd6eab1665a53e5dc0f6edcb5a2747bd0d250d526737bc2a57ce3414546e3efd` |
| `private-evidence/scratch/consolidated-compiled-84684a0/ledger.md` | `70dceab351eb3199bcf180faf4ea65311d3e2c6e4b80c04cf9c3627cda503494` |
| `private-evidence/scratch/cperf-build-ce408f4` | `NOT_ON_DISK` |
| `private-evidence/scratch/cperf-results-ce408f4.json` | `NOT_ON_DISK` |
| `private-evidence/scratch/cperf-wt-ce408f4` | `NOT_ON_DISK` |
| `private-evidence/scratch/final_docs_gates_dd079d4/docs_tests.log` | `c140739e4828a64432e9b03e912798daa40a22a06ab3e689ce77139fa593b15c` |
| `private-evidence/scratch/final_docs_gates_dd079d4/foundation.log` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| `private-evidence/scratch/final_git_tree_provenance_84684a0.json` | `2dd4e2d19b34f3b1ed0ed92ff0100c953b2b4084b174fc076b2356b6960066c6` |
| `private-evidence/scratch/final_suite_20fb694.json` | `1ee77b94b6c48c11e70242d4d117e539943fa15708cee31ebbabd2d88e219388` |
| `private-evidence/scratch/final_suite_20fb694_artifacts/full.log` | `c974a9032bb4b764315abb7f4bc3de707a29e9adc25eeea765ce60f8681d2316` |
| `private-evidence/scratch/final_suite_20fb694_rerun.json` | `2f3a70d9bd848b247b834557720fae64aa1526c9fa3473e60ee5ec2524fa27da` |
| `private-evidence/scratch/final_suite_20fb694_rerun_artifacts/full.log` | `fe659f5d62bf23330d193b43ef9a5cf45f8a18da7992ba434d45d850bfe52670` |
| `private-evidence/scratch/final_suite_84684a0.json` | `2efec701f7711ebc001b0d7a551d57abf21873e93c78a151cb1ba1ea9c9dc3b8` |
| `private-evidence/scratch/final_suite_84684a0_artifacts/full.log` | `72bb1ea46b04cd605883b7fa83a009e5fc4eba1d780fa81646289432855bbee6` |
| `private-evidence/scratch/final_suite_independent_verification_84684a0.json` | `afb1d085b9ea9a6f8f49927548a98f805c67b8a51853a76b6e75cb3b88ef351a` |
| `private-evidence/scratch/int-queue-635/final_qa_report_af97e11.md` | `7db322e2781ebe574f426fb827a542a7a39b2afd1acd4f4c6a25f5479729f97d` |
| `private-evidence/scratch/int-queue-635/v2-foundation.log` | `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad` |
| `private-evidence/scratch/int-queue-635/v2-full.log` | `b274d360caa2b026ea8446073c549976b77fd2b2a5dd1c08427be72987345b94` |
| `private-evidence/scratch/master_directive_20261126/evidence/quick_controls_status` | `NOT_ON_DISK` |
| `private-evidence/scratch/mint-evidence` | `NOT_ON_DISK` |
| `private-evidence/scratch/mint_acceptance_8269ec9/host-evidence/report.json` | `a30aeb9ccc83f84bfe51ec5237cd0f5655a6119bfc4911f84012f5a3119752db` |
| `private-evidence/scratch/pe004-dock-pin` | `NOT_ON_DISK` |
| `private-evidence/scratch/pe099_wt_60809ae` | `NOT_ON_DISK` |
| `private-evidence/scratch/perf_cli_rerun_20fb694.log` | `bc9b6104b24eaf1be191837ce9b12421f064bc5baa170865f63984fd1f8e03f3` |
| `private-evidence/scratch/stale_docs_gates_af97e11` | `NOT_ON_DISK` |
| `private-evidence/scratch/v3port-evidence/v3port_evidence_manifest.json` | `ebb0a467a708633390aaf287ae8a73105d326b8b1fb4634ac3b06f88a6516748` |
| `private-evidence/scratch/wc-c-final-paired/results.json` | `NOT_ON_DISK` |
| `private-evidence/scratch/wc-c-paired/results.json` | `NOT_ON_DISK` |
| `private-evidence/scratch/wc-c-paired2/results.json` | `NOT_ON_DISK` |
| `private-evidence/scratch/wc-c-paired3/results.json` | `NOT_ON_DISK` |
| `private-evidence/scratch/ws2-evidence/ws2_evidence_manifest.json` | `NOT_ON_DISK` |
| `private-evidence/temp/canopy-repro-stage` | `NOT_ON_DISK` |
| `private-evidence/temp/clock-evidence-9a37427/SHA256SUMS.txt` | `24dc9879a4e9adcabc85c4ced0fbcedd171574852442507a3d4e8c1b62b48ab8` |
| `private-evidence/temp/docklaunch-b3d2552/tests/test_classic_remaining_dock_integration.py` | `NOT_ON_DISK` |
| `private-evidence/temp/docklaunch-build` | `NOT_ON_DISK` |
| `private-evidence/temp/docklaunch-build/.qt/.qmlls.build.ini` | `f13e726273bb780c0e94ebf8db4b4e260340861f089e42545604ac419da2780f` |
| `private-evidence/temp/pe053-network-c6de241` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp3d94mi1f/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp4nzblsb9/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp694j7ndp/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp7_7pk3xx/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp7fbew8p6/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp8q7cmaiu/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmp_62msgj_/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmpdjizd4f0/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmpiby3geiy/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmpndbf7x3m/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmppu9kd1vk/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/temp/tmpsuheolv5/cli-plan.json` | `NOT_ON_DISK` |
| `private-evidence/terminal-output/out-1795645104-14640-3bb0.log` | `52081a66e24bc51edb4733ed652ecd77547edf28c5a3fb101d517aac6b10cddc` |
| `scratch/master_directive_20261126/evidence/wallpaper_change_validation` | `NOT_ON_DISK` |

Worktree/config defaults use these IDs or `CANOPY_PRIVATE_SCRATCH` /
`REPO` environment overrides; no private host path is required to run tests.
