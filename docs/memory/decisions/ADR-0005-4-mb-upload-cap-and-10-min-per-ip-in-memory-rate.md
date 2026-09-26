---
id: ADR-0005
type: decision
title: 4 MB upload cap and 10/min per-IP in-memory rate limit
status: active
scope: project
components: main, limits
triggers: 
evidence: ARCHITECTURE.md#Failure-boundaries
verified_at: 2026-09-26@e81940d
relates: 
supersedes: 
helpful: 1
harmful: 0
cite_hash: 4c53612711f65dbd
created: 2026-09-26
source: unknown
---

Context: Vercel function request bodies are limited to 4.5 MB; POST /api/memo is a public write endpoint that triggers up to 6 concurrent corpus fetches and optional paid LLM calls.
Decision: reject > 4 MB (too_large), > 200k chars, > 250 citations; 10 memos/min per IP in memory (429 rate_limited); advisory ≤ 20 calls per memo.
Alternatives rejected: Blob client uploads (no need for large PDFs in the demo); Redis rate limiting (no requirement).
Consequences: UI-SPEC's 20 MB string revised to 4 MB.
Revisit when: users need larger filings.