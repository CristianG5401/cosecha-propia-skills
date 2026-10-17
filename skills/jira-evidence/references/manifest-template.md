# <TICKET> evidence

Source: <read-only Jira URL or pasted acceptance criteria>
Prepared: <YYYY-MM-DD>
Scope: <one sentence>

| AC | Evidence | Status | Dependency | Expected proof | Artifact / command / source | Reviewer result |
|---|---|---|---|---|---|---|
| AC-1 | VIDEO | PLANNED | — | <visible outcome> | `raw/AC-1.mp4` → `AC-1.mp4` | — |
| AC-2 | TEST | PLANNED | AC-1 | <technical outcome> | `<exact command>` | — |
| AC-3 | SOURCE | PLANNED | AC-2 | <static outcome> | `<file path and revision>` | — |

## Notes

- Record known limitations here.
- Keep technical test output concise and include enough command context to rerun it.
- `FAIL`, `PARTIAL`, and `BLOCKED` state the observed result and blocker; do not relabel them as `PASS`.

## Compose commands

The exact command behind each `VIDEO` artifact, so it can be rebuilt with a different trim:

```bash
# AC-1
python3 <skill-dir>/scripts/evidence_video.py compose --raw raw/AC-1.mp4 --output AC-1.mp4 ...
```
