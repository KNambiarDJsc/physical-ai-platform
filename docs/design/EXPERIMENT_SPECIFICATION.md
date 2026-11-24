# Experiment specification

The canonical execution contract is pap.experiment-spec/1 in services/api/app/experiments/spec.py. Version creation validates scenario inputs and pins the host identity and scenario definition. Approval references the checksum of that immutable version. Edited parameters require a new version and review.

The guided editor, code import and any future canvas should call the same validation and version-creation API. A draft can be edited. An approved version is read-only. Keep actor permissions and the current approval or trial state in service records so those changes do not mutate the spec checksum. Compilation into device workflows is the worker-facing representation.

A plan missing a catalog scenario, parameter schema or independent observation needs review. It must never generate a shell command. Record failed capture and absent measurements so OpenMHS can return unknown.
