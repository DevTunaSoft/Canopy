# scratch/lacos_app_isolation

Synthetic-only artifacts for the LacOS P1 app-isolation contract.

- `fixtures/` — 19 deterministic fixture files and `SHA256SUMS`. Three
  positive requests (`F001`–`F003`), fourteen negative decisions (`F010`–
  `F023`) and two hostile raw documents (`F024`, `F025`). No real guest data.
- `evidence/evidence_synthetic.json` — verifier output labelled
  `SYNTHETIC`; real guest is `BLOCKED` / `NOT_RUN`.
- `evidence/evidence_synthetic.json.sha256` — LF-only SHA-256 sidecar.

Regenerate with:

```sh
python tools/lacos_app_isolation/generate_fixtures.py
python tools/lacos_app_isolation/run_contract_checks.py
```

The verifier writes only inside this directory. No sandbox, portal, systemd
unit, compositor or application is started.
