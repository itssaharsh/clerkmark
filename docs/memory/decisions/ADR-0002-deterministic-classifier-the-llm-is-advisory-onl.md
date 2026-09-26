---
id: ADR-0002
type: decision
title: Deterministic classifier; the LLM is advisory only and off by default
status: active
scope: project
components: rules, advisory
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

Context: the product promise is a rule a judge can read; Princeton (arXiv 2606.21155) found weaker models treat absence from CourtListener as evidence of hallucination.
Decision: rules.classify is pure Python over fetched metadata; classes never depend on a model; the optional Anthropic call only adds an advisory verdict on verified rows with a quote.
Alternatives rejected: LLM-judged classification (unexplainable, mislabels real cases); no LLM at all (loses the 'supports the proposition' triage).
Consequences: misrepresented propositions (42% of Charlotin cases) get only advisory coverage; say so in the UI.
Revisit when: a labelled test set shows the advisory verdict is reliable enough to promote.