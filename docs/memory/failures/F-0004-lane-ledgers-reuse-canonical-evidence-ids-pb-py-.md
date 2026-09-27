---
id: F-0004
type: failure
title: Lane ledgers reuse canonical evidence ids: pb.py report inside a lane resolves ids against the lane, and lane logs overwrite canonical .prod-build/logs/E00nn.log
status: active
scope: global-candidate
components: prod-build
triggers: 
evidence: .prod-build/reports/T10.md
verified_at: 2026-09-27@87a02da
relates: 
supersedes: 
helpful: 0
harmful: 0
cite_hash: e3b0c44298fc1c14
created: 2026-09-27
source: unknown
---

Attempted: run parallel lanes with PB_LEDGER=.prod-build/evidence.<lane>.jsonl in one working tree.
Error signature: 'ERROR [bugs found and fixed] cites E0019, which is not in the ledger' from pb.py report inside a lane verify; lane E-ids restart at E0001 and their logs land in the shared logs/ dir.
Root cause: pb.py numbers evidence per ledger file but writes logs to one directory; report/verify steps inherit PB_LEDGER.
Fix: run pb.py report and canonical verify with env -u PB_LEDGER from the orchestrator; cite only canonical ids in DELIVERY.md; treat lane runs as scratch.
Lesson: in parallel lanes, either give each lane its own PB_LOGS dir or accept that lane logs are scratch and re-run canonical verify in the main tree before task done.
Early check: grep 'E0001' across evidence.*.jsonl to see the collision.