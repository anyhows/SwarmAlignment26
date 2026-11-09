# BashArena task fixtures

The task records in this directory come from the BashArena dataset published
by Eccentricity / Redwood Research:

- Source: https://huggingface.co/datasets/Eccentricity/bashbench2
- Revision: `13e19f9c2c91e3a55a49f8de7a28c08055f7ede8`
- Task IDs: `43141659` (configuration validation/backup) and `29328278`
  (Jenkins-style plugin management).
- Dataset license: [Creative Commons Attribution-ShareAlike 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

The JSON records retain their original description, Dockerfile, tests, setup
script, API source, requirements, and metadata. `manifest.json` records hashes
of the vendored files and decoded source fields.

This environment loads the API source from those pinned records. The loader
changes its API-key setting to a local fixture value and, for the plugin API,
points the data directory at this environment's seeded repository. The source
itself is retained unchanged. The plugin fixture generator reuses the original
dependency graph and generates smaller deterministic, non-executable mock
content instead of random content. The configuration policy is extracted
unchanged from the original setup script.

The new A2A pipeline is an adaptation, not a complete implementation or
evaluation of every requirement in either original task. These vendored data
records retain the dataset license separately from the SDK's source license.
