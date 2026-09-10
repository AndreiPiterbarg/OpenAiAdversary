# Frozen host runtime validation

Three tasks were selected before compatibility outcomes: Factory (discovery), Asgiref (held-out A), and Djpress (held-out B). Their exact required test counts are 2, 15, and 68. Each baseline fails every F2P test and passes every P2P test; each gold passes all required tests.

These are new host Python runtimes, not reproductions of the original container environment. `pins.json` binds source commits, frozen test patches, gold patches, prepared checkpoints, repository hashes and dedicated dependency-tree hashes. Paths use the symbolic `HOST_RUNTIME_ROOT`; the unchanged original receipt byte hashes are in `provenance.json`.

Reproduction requires Linux Landlock/seccomp support, the pinned repository checkout and frozen test patch, the recorded dependency versions, and explicit host resource admission. Materialize the two documented Factory links before creating its prepared checkpoint. Install the dedicated pytest launcher with source checkout and `src` preceding installed packages. Relocating a venv changes launcher bytes: create a new runtime pin and repeat baseline/gold gates rather than claiming the original digest.

Run trusted Python preparation with explicit `-I -B`, inspect pristine Git state using a copied index, then run raw artifact transport and guarded baseline/gold commands. Verify repository and venv hashes after each stage. Preserve the exact required-node statuses, command receipts and refused attempts. `guard-validation.json` summarizes the actual successful checks and their resource limits.

Passing these checks establishes host compatibility and the tested guard capabilities. It does not authenticate arbitrary candidate-controlled pytest output or establish a protected clean-solve rate. Old failed runtime arms remain excluded from the successor arm's measurements.
