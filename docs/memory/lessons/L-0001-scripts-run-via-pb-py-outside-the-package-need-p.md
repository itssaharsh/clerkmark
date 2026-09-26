---
id: L-0001
type: lesson
title: Scripts run via pb.py outside the package need PYTHONPATH=.
status: active
scope: project
components: scripts, tests
triggers: 
evidence: .prod-build/reports/T02.md
verified_at: 2026-09-26@bbd070e
relates: 
supersedes: 
helpful: 1
harmful: 0
cite_hash: e3b0c44298fc1c14
created: 2026-09-26
source: unknown
---

When: running a Python script or one-off check that imports citememo from outside a pytest run.
Do: prefix with PYTHONPATH=. (the venv does not install citememo as a package).
Because: E0003 in the T02 lane failed with ModuleNotFoundError until PYTHONPATH was set.