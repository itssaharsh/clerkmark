---
id: ADR-0004
type: decision
title: No database: JSON file cache, committed seed cache, recorded replay
status: active
scope: project
components: cache, seed
triggers: 
evidence: ARCHITECTURE.md#Data-flow
verified_at: 2026-09-26@e81940d
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: c6467ba7e53d9f7e
created: 2026-09-26
source: unknown
---

Context: nothing persists per user; the demo must run offline; Vercel FS is read-only except /tmp.
Decision: two-level cache (memory + JSON files) with a cache-dir fallback chain; the seed's CAP files are committed; a recorded replay.json backs the demo.
Alternatives rejected: SQLite/Postgres (no requirement forces it).
Consequences: cache size (~24 MB) lives in the repo; cache invalidation is manual.
Revisit when: multi-user history is required.