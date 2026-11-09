# Validation record

Observed on November 8, 2026 (America/Los_Angeles).

- 38 package tests passed, including actual A2A pause/resume and offline Adaption contracts.
- Ruff and ty passed for the packaged source and entry points.
- All four unchanged-input combinations passed on native Python, Docker, and the standalone uv wrapper.
- Every successful trial consumed the reviewed input identities and completed project-scoped teardown.
- No live model requests or changed-input trials were run. The persistent request ledger was not created.
- Docker Engine 29.5.2 used the isolated `colima-swarm-basharena` context; the global context remained `default`.

| Verification | medium/current | medium/snapshot | hard/current | hard/snapshot |
|---|---|---|---|---|
| setup-native | ok | ok | ok | ok |
| setup-docker | ok | ok | ok | ok |
| setup-standalone | ok | ok | ok | ok |

Machine-readable details: [VALIDATION.json](VALIDATION.json).

Local run summaries (ignored artifacts exist in this checkout; a new checkout regenerates them):

- [setup-native](../artifacts/a2a_basharena_testbeds/runs/setup-native/20261108-170937-498d769a/summary.md)
- [setup-docker](../artifacts/a2a_basharena_testbeds/runs/setup-docker/20261108-171354-770b5892/summary.md)
- [setup-standalone](../artifacts/a2a_basharena_testbeds/runs/setup-standalone/20261108-171843-bc309b25/summary.md)

The initial native validation retained an `agent_error` when sequential trials reused ports in TIME_WAIT. The launcher preflight was corrected to use address reuse; all four subsequent native trials passed. That earlier failed run remains under `artifacts/a2a_basharena_testbeds/runs/setup-native/20261108-170818-eaad0870/`.

The tested Docker image ID and resolved package versions are recorded in the Docker trial environment files and VALIDATION.json. API credentials remain necessary to validate live provider behavior. These results establish setup/readiness and unchanged-input behavior only, not an observed TOCTOU outcome.
