# Second Brain — Architecture

The system separates immutable raw history, episodic session logs, active wiki knowledge, continuity memory, and routing indexes. The shared engine lives under `.second-brain/`; Claude Code, Codex, and OpenCode are connected through global adapters so the vault remains independent of any one vendor.

## Core rules

1. `raw/` is immutable.
2. Preserve provenance for durable claims.
3. Surface contradictions.
4. Update canonical pages instead of creating avoidable duplicates.
5. Archive instead of silently deleting.
6. Keep project-local files authoritative for project-specific facts.
7. Never store secrets.

---

_Authored and maintained by [Doğan Koç](https://github.com/dogankoc)._
