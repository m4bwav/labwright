# Handoff: labwright

State (2026-11-15): 0.1.0 built. lw.py with hosts, status, where, pick, place, doctor; unit tests and leak test pass; first real run against the owner's registry found both hosts up and idle with no drift (notes in the sidecar). Repository private.

Next:
1. Skill-on runs of the 12 behaviour cases and 4 decoys (TESTS.md), compared with the bare baseline on steps and tokens.
2. Install the plugin locally and check triggering.
3. Decide public release (fresh history is clean: no sidecar term was ever committed).
4. Later: let the idle watcher and the text-offload skill read the registry.
