---
id: ADR-0001
type: decision
title: Caselaw Access Project static files as the primary corpus; CourtListener optional
status: active
scope: project
components: cap, memo
triggers: 
evidence: ARCHITECTURE.md#Key-decisions
verified_at: 2026-09-26@e81940d
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: ae638f7d585646ce
created: 2026-09-26
source: unknown
---

Context: every citation must be resolved without an account; CourtListener v4 returns 401 without a token (verified 2026-09-26) and new accounts have an unstated rate limit.
Decision: resolve reporters, volumes, cases and opinion text from static.case.law (no auth; 401 reporters; F.3d to vol 935, U.S. to 572, F. Supp. 2d to 999); CourtListener only as an optional second pass when COURTLISTENER_TOKEN is set.
Alternatives rejected: CourtListener-only (gated; demo could fail on a token); Westlaw/Lexis (paid, no API for students).
Consequences: recent cases (post ~2019) read 'Not in the free library' unless a token is set; pin cites unverifiable (no page breaks in CAP text).
Revisit when: CAP goes offline or CourtListener offers anonymous lookups.