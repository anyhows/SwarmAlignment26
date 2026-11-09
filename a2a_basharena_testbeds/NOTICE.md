# Provenance and adaptations

This directory packages the BashArena-derived A2A environments developed in the
adjacent SDK workspace into an independent experiment runner. The task lifecycle
and Adaption integration conventions were informed by `../a2a_testbed`.

- `runtime/upstream/43141659.json` and `29328278.json` contain pinned BashArena
  task records. Their dataset revision, hashes, adaptations, and CC BY-SA 4.0
  attribution are documented in `runtime/upstream/NOTICE.md` and `manifest.json`.
- The original Flask sources are loaded unchanged, with local synthetic fixture
  settings. Original host setup scripts and full benchmark evaluation are not run.
- `vendor/a2a-sdk/` contains unchanged SDK source, project metadata, and its
  Apache 2.0 license at commit `28f8a62f25d46067ae846329a42a60c820fa927e`.
- The runtime package, container integration, model decision wrapper, observer,
  trial scenarios, and metrics are adaptations/new code. They implement selected
  task slices, not all original CLI, ownership, concurrency, or scoring requirements.

No real credentials are fixtures. `.env`, generated state, logs, results, and
virtualenvs are excluded from the Docker context or kept outside this directory.
