---
id: F-0001
type: failure
title: eyecite 2.7.8 full_span overshoots and metadata.year borrows the next citation's year
status: active
scope: global-candidate
components: extract
triggers: 
evidence: citememo/extract.py
verified_at: 2026-09-26@bbd070e
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: 2eb6b36c70bca5ba
created: 2026-09-26
source: unknown
---

Attempted: use eyecite full_span() and metadata.year as the citation text and year.
Error signature: Floyd's span ran to the next citation; Shaboon and Floyd got year 2019 from a neighbour.
Root cause: eyecite's span/year heuristics read past the parenthetical into the following citation.
Fix: build cite_text from plaintiff/defendant anchors and take the year from a bounded parenthetical window (T03).
Lesson: when a citation's printed text or year matters, bound the window by the next citation's case name.
Early check: assert the seed's 20 cite_texts round-trip from the PDF.