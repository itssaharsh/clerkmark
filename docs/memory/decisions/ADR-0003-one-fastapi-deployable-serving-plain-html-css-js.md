---
id: ADR-0003
type: decision
title: One FastAPI deployable serving plain HTML/CSS/JS; no front-end framework
status: active
scope: project
components: main, web
triggers: 
evidence: ARCHITECTURE.md#Components
verified_at: 2026-09-26@e81940d
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: b54953e47d7a2a0a
created: 2026-09-26
source: unknown
---

Context: one page (memo, eval, how-it-works), 24 hours, Vercel zero-config FastAPI needs 'app' in main.py; eyecite is Python-only.
Decision: FastAPI + static files; vanilla JS; no build step.
Alternatives rejected: Next.js + Python API (two deployables, more config); Streamlit (cannot meet the UI spec).
Consequences: UI state lives in app.js; templates are string-free (textContent) to avoid injection.
Revisit when: routes or SSR are needed.