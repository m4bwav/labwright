# Placement

`lw.py place --size GB [--role R]` lists every store of every (matching) host with free space, free after the download, and `ok` when that stays at or above `floor_gb`.

- Local stores are measured with disk usage on the real path; resolve junctions and symlinks in the registry (record the target, not the link).
- Remote stores use the registry's `free_gb` with its `free_checked` date; `ok: null` means unknown, so measure before downloading.
- The answer only places; it never downloads. Before any new model: licence and gating check, a dry run of the download, and the pinned revision.
