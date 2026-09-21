# Configuration architecture

## Boundary

Application code consumes immutable `GlobalSettings` and `ProjectSettings`
objects from `csttool.configuration`. INI and JSON are persistence formats, not
the runtime API. `ConfigParser` remains available on managers only as a
temporary compatibility view for external callers.

## Models

- `GlobalSettings` owns base directories, the selected CST backend, the current
  project pointer, and optional Superfish settings.
- `ProjectSettings` owns project metadata, result/temp paths, the prepared CST
  identity, parameter/post-processing files, fixed Mesh settings, execution
  flags, and persisted task state.
- Nested frozen dataclasses keep related values together and prevent accidental
  mutation during a run.

Every persisted document carries `config.schema_version`. Files without that
section are treated as legacy schema 1 and normalized to the current schema on
save. A file newer than the running application is rejected instead of being
silently rewritten.

Canonical schema 3 uses lowercase snake_case throughout:

- global INI: `[config]`, `[paths]`, `[cst]`, `[project]`, `[superfish]`;
- project INI: `[config]`, `[project]`, `[paths]`, `[cst]`, `[execution]`,
  `[artifacts]`, `[mesh]`, `[task]`.

Paths, CST identity, execution policy, generated artifacts, Mesh policy and
runtime state therefore have separate ownership. Legacy names such as
`CSTFilename`, `UseMpi` and the misspelled `UseRemoteCalculaton` are accepted
only by the migration reader and are never emitted. New project identities use
SHA-256; legacy MD5 values remain readable with their inferred algorithm.

## Persistence

`read_ini`, `write_ini_atomic`, `read_json`, and `write_json_atomic` form the
serialization boundary. Writes are made to a temporary file in the destination
directory and published with `os.replace`, so a crash cannot expose a partially
written configuration.

INI is retained for small human-edited scalar configuration. JSON is retained
for structured parameter lists, post-processing definitions, manifests and
checkpoints. CSV remains the tabular result/export format. This keeps each
format aligned with its data shape without adding a TOML writer dependency.

## Lifecycle

`GlobalConfigManager` and `ProjectConfigManager` coordinate discovery,
preprocessing, validation, recovery, and status transitions. They synchronize
their compatibility `conf` view at persistence boundaries. `CSTManager` reads
typed settings directly when available.

Historical names `GlobalConfmanager` and `ProjectConfmanager` remain aliases so
existing integrations can migrate without a flag day. New code must use the
PEP 8 names and typed `settings` properties.

Field-by-field purpose, units, mutability and lifecycle notes are documented in
`configuration-reference.md`; annotated templates live under `config/`.
