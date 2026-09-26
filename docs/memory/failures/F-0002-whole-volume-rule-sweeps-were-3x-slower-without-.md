---
id: F-0002
type: failure
title: Whole-volume rule sweeps were 3x slower without memoized per-volume derived data
status: active
scope: project
components: rules
triggers: 
evidence: citememo/rules.py
verified_at: 2026-09-26@bbd070e
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: a3dea05969478fff
created: 2026-09-26
source: unknown
---

Attempted: recompute cap_end_year/volume_min and scan case names per classify call.
Error signature: tests/test_rules.py took 52 s.
Root cause: O(n) rescans of VolumesMetadata and CasesMetadata per citation.
Fix: RuleContext.index() memoizes the volume index and a by-name index (34 s).
Lesson: derive per-volume data once per context, not per citation.
Early check: time a 20-citation memo; expect < 3 s offline.