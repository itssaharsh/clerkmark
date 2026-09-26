#!/usr/bin/env python3
"""pb.py - deterministic helper for the prod-build skill (stdlib only, Python 3.8+).

It keeps the parts of a build that should not depend on an agent's memory or honesty:
the task graph, the evidence ledger, test-weakening checks, relay intake, project
memory records and the delivery-report check.

  init      create .prod-build/ and docs/memory/ (never overwrites)
  status    one-screen board: tasks, next ready work, recent evidence, memory health
  plan      check | waves | next         validate plan.json and compute parallel lanes
  task      <ID> start|done|skip|block|reopen [--evidence E0001,..] [--note ..]
  run       [--task ID] [--kind K] [--where local|preview|prod] [--expect-fail] -- <cmd>
  verify    <ID>                         run all of a task's verify commands through the ledger
  smoke     <base-url> [--routes / /x]   HTTP + asset check of a running or deployed app
  evidence  add | list | redact          record an observation, list the ledger, scrub a leaked secret
  diffcheck [--base REF | --task ID]     find skipped/deleted tests, loosened configs, secrets
  intake    <ID> [--base REF]            check a relay agent's work before accepting it
  mem       add | find | check | index | mark     project memory in docs/memory/
  report    <file>                       every verification claim must cite passing evidence

Run from anywhere inside the project; the root is the nearest folder holding .prod-build/
or .git (override with --root). Exit codes: 0 ok, 1 check failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

VERSION = "0.1.0"
MODES = ("hackathon", "product", "hybrid")
CHANNELS = ("direct", "relay", "chat")
STATUSES = ("todo", "doing", "done", "skip", "blocked")
KINDS = ("build", "test", "red", "lint", "typecheck", "e2e", "smoke", "security", "deploy",
         "eval", "perf", "migration", "review", "manual", "other")
MEM_TYPES = {  # type -> (id prefix, folder)
    "decision": ("ADR", "decisions"),
    "failure": ("F", "failures"),
    "lesson": ("L", "lessons"),
    "assumption": ("A", "assumptions"),
    "feedback": ("U", "feedback"),
    "pattern": ("P", "patterns"),
}
MEM_STATUSES = ("active", "superseded", "archived", "invalidated")
MEM_REQUIRED = ("id", "type", "title", "status", "scope", "components", "evidence", "verified_at")
CAPS = {"index_lines": 150, "record_lines": 60, "active": 150}
HOT_FILES = re.compile(
    r"(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|"
    r"pyproject\.toml|poetry\.lock|uv\.lock|requirements[^/]*\.txt|go\.mod|go\.sum|Cargo\.(toml|lock)|"
    r"schema\.prisma|drizzle\.config\.[^/]+|tsconfig[^/]*\.json|next\.config\.[^/]+|vite\.config\.[^/]+|"
    r"docker-compose[^/]*\.ya?ml|\.env[^/]*)$|(^|/)(migrations|alembic|supabase/migrations)/|(^|/)\.github/workflows/")
TEST_FILE = re.compile(
    r"(^|/)(tests?|__tests__|spec|e2e)/|\.(test|spec)\.[cm]?[jt]sx?$|_test\.go$|(^|/)test_[^/]+\.py$|_test\.py$|_spec\.rb$")
CONFIG_FILE = re.compile(
    r"(^|/)(\.eslintrc[^/]*|eslint\.config\.[cm]?[jt]s|tsconfig[^/]*\.json|jest\.config\.[^/]+|"
    r"vitest\.config\.[^/]+|playwright\.config\.[^/]+|pytest\.ini|setup\.cfg|tox\.ini|\.coveragerc|"
    r"\.golangci\.ya?ml|biome\.jsonc?|\.prettierrc[^/]*|knip\.jsonc?|\.semgrep[^/]*|\.gitleaks\.toml)$"
    r"|(^|/)\.github/workflows/|(^|/)\.pre-commit-config\.yaml$"
    r"|(^|/)(AGENTS|CLAUDE|GEMINI)\.md$|(^|/)\.claude/(settings[^/]*\.json|agents/|hooks/)|(^|/)\.gemini/settings\.json$")
WEAKENING = [  # (regex on an added line, severity, message)
    (r"\b(describe|it|test|context|suite)\.(skip|only)\s*\(", "error", "focused/skipped JS test"),
    (r"\b(xit|xdescribe|fit|fdescribe|xtest)\s*\(", "error", "focused/skipped JS test"),
    (r"\btest\.fixme\s*\(|\btest\.fail\s*\(", "warn", "Playwright test marked fixme/fail"),
    (r"[{,]\s*skip\s*:\s*(true|[\"'])", "error", "test skipped via options ({ skip: … })"),
    (r"[{,]\s*todo\s*:\s*true", "warn", "test marked todo"),
    (r"@pytest\.mark\.(skip|xfail)|pytest\.skip\s*\(|@unittest\.skip", "error", "skipped Python test"),
    (r"\bt\.Skip(Now|f)?\s*\(", "error", "skipped Go test"),
    (r"#\[ignore\]", "error", "ignored Rust test"),
    (r"@ts-ignore|@ts-nocheck|@ts-expect-error", "warn", "type check suppressed"),
    (r"eslint-disable", "warn", "lint rule disabled"),
    (r"#\s*type:\s*ignore|#\s*noqa|//\s*nolint", "warn", "check suppressed"),
    (r"--no-verify", "error", "git hooks bypassed"),
    (r"\bdebugger\s*;", "warn", "debugger statement"),
    (r"--passWithNoTests|--pass-with-no-tests", "warn", "suite allowed to pass with no tests"),
]
SECRET_PATTERNS = [
    re.compile(r"\b(sk|rk)_(live|test)_[0-9A-Za-z]{16,}"),
    re.compile(r"\bwhsec_[0-9A-Za-z]{16,}"),
    re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_\-]{20,}"),
    re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"),
    re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-(proj-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
SECRET_ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_]*(api[_-]?key|secret|token|passw(or)?d|client[_-]?secret))\b(\s*[:=]\s*[\"']?)([^\s\"'`]{8,})")
DB_URL_PASSWORD = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^:/\s@]+:)([^@\s]{3,})(@)")
URL_SECRET_PARAM = re.compile(r"(?i)([?&#](?:key|token|secret|password|pass|sig|signature|access_token|api_key|apikey|auth)=)[^&\s#\"']+")
ENV_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_KEY|CLIENT_SECRET|WEBHOOK)[A-Z0-9_]*)\s*=\s*[\"']?([^\s\"'#]{8,})")
SECRET_LITERAL = re.compile(
    r"(?i)(api[_-]?key|secret|token|passw(or)?d|client[_-]?secret|private[_-]?key)\w*[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_\-+/=.]{16,})[\"']")
PLACEHOLDER = re.compile(r"(?i)(example|placeholder|dummy|sample|your[_-]|xxxx|changeme|replace[_-]?me|redacted|<[^>]+>|\$\{)")
EVIDENCE_ID = re.compile(r"\bE\d{4,}\b")
NOT_RUN = re.compile(r"(?i)(\bnot run\b|\bnot performed\b|\bnot applicable\b|\bn/a\b|\bnot deployed\b|\bnot verified\b)")
REPORT_SECTIONS = ("built", "architecture", "verification", "deployment", "bugs", "known limitations",
                   "cleanup", "optimization", "memory", "next steps")
CLAIM_SECTIONS = ("verification", "deployment", "bugs")


# ----------------------------------------------------------------------------- utilities

def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return _dt.date.today().isoformat()


def die(msg: str, code: int = 2) -> None:
    print(f"pb: {msg}", file=sys.stderr)
    sys.exit(code)


def find_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    here = Path.cwd().resolve()
    for p in [here, *here.parents]:
        if (p / ".prod-build").is_dir():
            return p
    for p in [here, *here.parents]:
        if (p / ".git").exists():
            return p
    return here


def git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=check)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", "git not found")


def git_info(root: Path) -> dict:
    head = git(root, "rev-parse", "--short", "HEAD")
    if head.returncode != 0:
        return {"sha": None, "dirty": None}
    dirty = git(root, "status", "--porcelain", "--", ".", ":(exclude).prod-build")
    return {"sha": head.stdout.strip(), "dirty": bool(dirty.stdout.strip())}


def tree_hash(root: Path):
    """Content fingerprint of the working tree (tracked + untracked, minus ignored files and .prod-build/).
    Stored with each evidence entry so `task done` can refuse evidence gathered on different code."""
    if git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(td, "index"))

        def g(*a):
            return subprocess.run(["git", *a], cwd=root, env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        g("read-tree", "HEAD")
        g("rm", "-r", "-q", "--cached", "--ignore-unmatch", ".prod-build")
        if g("add", "-A", "--", ".", ":(exclude).prod-build").returncode != 0:
            return None
        w = g("write-tree")
        return w.stdout.strip()[:12] if w.returncode == 0 else None


def redact(text: str) -> str:
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    text = SECRET_ASSIGN.sub(lambda m: m.group(1) + m.group(4) + "[REDACTED]", text)
    text = DB_URL_PASSWORD.sub(lambda m: m.group(1) + "[REDACTED]" + m.group(3), text)
    text = URL_SECRET_PARAM.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


def looks_like_secret(line: str) -> bool:
    """High-precision check used for findings (redact() is deliberately greedy and used for logs)."""
    if PLACEHOLDER.search(line):
        return False
    if any(p.search(line) for p in SECRET_PATTERNS):
        return True
    m = SECRET_LITERAL.search(line)
    if m and len(set(m.group(3))) >= 8:
        return True
    m = ENV_ASSIGN.search(line)
    if m and len(set(m.group(2))) >= 6 and not m.group(2).startswith(("process.env", "os.environ", "$")):
        return True
    m = DB_URL_PASSWORD.search(line)
    return bool(m and not re.search(r"(?i)^(pass(word)?|postgres|root|admin|user)$", m.group(2)))


def norm_path(p: str) -> str:
    p = p.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def has_glob(p: str) -> bool:
    return bool(re.search(r"[*?\[]", p))


def static_prefix(p: str) -> str:
    m = re.search(r"[*?\[]", p)
    if not m:
        return p
    pre = p[: m.start()]
    return pre[: pre.rfind("/") + 1] if "/" in pre else ""


def glob_regex(pattern: str) -> re.Pattern:
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        out.append({"*": "[^/]*", "?": "[^/]"}.get(c, re.escape(c)))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def paths_overlap(a: str, b: str) -> bool:
    """Conservative: True when two write surfaces could touch the same file."""
    a, b = norm_path(a), norm_path(b)
    if not a or not b:
        return False
    if a == b:
        return True
    ga, gb = has_glob(a), has_glob(b)

    def contains(d: str, p: str) -> bool:
        d = d.rstrip("/")
        return p.startswith(d + "/")

    if not ga and not gb:
        return contains(a, b) or contains(b, a)
    if ga and gb:
        pa, pb_ = static_prefix(a), static_prefix(b)
        return pa.startswith(pb_) or pb_.startswith(pa)
    pat, concrete = (a, b) if ga else (b, a)
    if glob_regex(pat).match(concrete):
        return True
    pre = static_prefix(pat)
    return contains(concrete, pre) or (pre != "" and concrete.rstrip("/") + "/" == pre)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}", 1)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pb_dir(root: Path) -> Path:
    return root / ".prod-build"


def mem_dir(root: Path) -> Path:
    return root / "docs" / "memory"


# ----------------------------------------------------------------------------- init

CONTRACT_TMPL = """# Implementation contract - {name}
mode: {mode} | channel: {channel} | created: {date}
Upstream read: <idea package / UI-SPEC.md / DESIGN.md / product brief, or "none">

## 1. Intent
- User and moment of use:
- What they can do:
- What changes after they use it (before -> after):

## 2. Scope
MUST (core product, main workflow, judged/required):
SHOULD (materially improves the main workflow):
COULD (later; not in this build):
WON'T now (hypothetical-future infrastructure, explicitly deferred):

## 3. Core journeys (smallest set that constitutes the product)
J1: user action -> system response -> observable outcome

## 4. Surfaces (only the necessary ones)

## 5. States per journey
| Journey | initial | loading | success | error | empty | partial | retry | disabled | permission-denied | offline/degraded |

## 6. Data
| Entity | Key fields | Relationships | Owner | Persistence | Source of truth | PII/retention |

## 7. Interfaces
| Interface | Purpose | Contract file | Failure mode | Fallback |

## 8. Constraints
Security / privacy / budget / latency / platform / deploy target / deadline / sponsor rules (verbatim) / judging criteria (verbatim + weights):

## 9. Acceptance criteria
AC-1: WHEN <event> THE SYSTEM SHALL <result>. Verify: <command or check>. Priority: must

## 10. Assumptions
A-1 [safe|reversible|blocking]: <claim> - validate by <method>

## 11. Demo script (hackathon/hybrid) or launch checklist (product)
"""

STATE_TMPL = """# Build state - {name}
Updated: {date} | mode: {mode} | channel: {channel} | phase: 0-intake
(Keep this under 60 lines. Overwrite it at every phase boundary and before stopping.)

## Now
- Phase / current task:
- Last good commit:            Last good deploy:

## What worked (with evidence IDs)

## What failed (memory IDs) - do not retry without a new root cause

## Not tried yet / open questions

## Changes that need care (migrations applied, deploys, destructive ops)

## Exact next step
"""

MEM_README = """# Project memory

Decisions, failures, lessons, assumptions, user feedback and working patterns that should change
what the next agent does. Records are hints until verified against the code they cite.
Generated index: INDEX.md. Tooling: `python3 .prod-build/pb.py mem find|add|check|mark`.
Never store secrets, transcripts, logs, or anything the code already says.
"""

AGENTS_BLOCK = """<!-- prod-build:memory-protocol -->
## Build memory protocol
- Before planning or changing a component: read `docs/memory/INDEX.md`; run
  `python3 .prod-build/pb.py mem find --paths <files> --terms <keywords>` and apply what fits.
- On any error: search failures by the error text first (`mem find --terms "<signature>"`); do not retry
  an approach a failure record says failed unless you have a new root cause.
- A record is a hint until its cited files still match (`mem check` flags stale ones).
- Run checks through `python3 .prod-build/pb.py run --task <ID> -- <command>` so results land in the
  evidence ledger; "done" means passing evidence exists, not that code was written.
- Task briefs: `.prod-build/briefs/<ID>.md`. Reports: `.prod-build/reports/<ID>.md`.
<!-- /prod-build:memory-protocol -->
"""


def cmd_init(args, root: Path) -> int:
    d = pb_dir(root)
    created = []
    for sub in ("briefs", "reports", "logs"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("logs/\nevidence.*.jsonl\n", encoding="utf-8")
        created.append(gi)
    name = args.name or root.name
    plan = d / "plan.json"
    if not plan.exists():
        write_json(plan, {"project": name, "mode": args.mode, "channel": args.channel,
                          "base": git_info(root)["sha"], "created": today(), "milestones": [], "tasks": []})
        created.append(plan)
    for fname, tmpl in (("contract.md", CONTRACT_TMPL), ("state.md", STATE_TMPL)):
        f = d / fname
        if not f.exists():
            f.write_text(tmpl.format(name=name, mode=args.mode, channel=args.channel, date=today()),
                         encoding="utf-8")
            created.append(f)
    ev = d / "evidence.jsonl"
    if not ev.exists():
        ev.touch()
        created.append(ev)
    me = Path(__file__).resolve()
    target = d / "pb.py"
    if me != target.resolve() and (not target.exists() or target.read_bytes() != me.read_bytes()):
        shutil.copyfile(me, target)
        created.append(target)
    m = mem_dir(root)
    for _, (_, folder) in MEM_TYPES.items():
        (m / folder).mkdir(parents=True, exist_ok=True)
    (m / "archive").mkdir(parents=True, exist_ok=True)
    if not (m / "README.md").exists():
        (m / "README.md").write_text(MEM_README, encoding="utf-8")
        created.append(m / "README.md")
    write_index(root)
    agents = root / "AGENTS.md"
    text = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if "prod-build:memory-protocol" not in text:
        sep = "\n" if text and not text.endswith("\n") else ""
        header = "" if text else f"# {name}\n\n"
        agents.write_text(text + sep + header + AGENTS_BLOCK, encoding="utf-8")
        created.append(agents)
    gitignore = root / ".gitignore"
    wanted = ["node_modules/", ".env", ".env.*", "!.env.example", ".prod-build/logs/", "dist/", ".next/",
              "__pycache__/", ".venv/", "coverage/", ".claude/worktrees/"]
    if not gitignore.exists():
        gitignore.write_text("\n".join(wanted) + "\n", encoding="utf-8")
        created.append(gitignore)
    else:
        have = gitignore.read_text(encoding="utf-8")
        lacking = [w for w in ("node_modules", ".env") if w not in have]
        if lacking:
            print("note: .gitignore lacks " + ", ".join(lacking) + "; add them before the first `git add`")
    if args.checklists:
        refs = Path(__file__).resolve().parent.parent / "references"
        dest = d / "checklists"
        if refs.is_dir():
            dest.mkdir(exist_ok=True)
            for name in ("security.md", "verification.md", "deploy.md", "ai-products.md"):
                if (refs / name).exists() and not (dest / name).exists():
                    shutil.copyfile(refs / name, dest / name)
                    created.append(dest / name)
        else:
            print("note: --checklists needs the skill's references/ folder next to scripts/; run init from the skill copy")
    claude = root / "CLAUDE.md"
    note = ""
    if not claude.exists():
        claude.write_text("@AGENTS.md\n", encoding="utf-8")
        created.append(claude)
    elif "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
        note = "CLAUDE.md exists without '@AGENTS.md': add that line so Claude Code also reads AGENTS.md."
    if args.checklists:
        asset = Path(__file__).resolve().parent.parent / "assets" / "smoke.spec.ts"
        dest = d / "checklists" / "smoke.spec.ts"
        if asset.exists() and (d / "checklists").is_dir() and not dest.exists():
            shutil.copyfile(asset, dest)
            created.append(dest)
    for c in created:
        print(f"created {c.relative_to(root)}")
    if not args.mode_given:
        print(f"note: mode defaulted to '{args.mode}'; after classifying (Step 1) set \"mode\" in .prod-build/plan.json")
    if not created:
        print("nothing to create; already initialised")
    if note:
        print("note: " + note)
    print("next: fill .prod-build/contract.md, then write tasks into .prod-build/plan.json and run `pb.py plan check`.")
    return 0


# ----------------------------------------------------------------------------- plan

def load_plan(root: Path) -> dict:
    plan = read_json(pb_dir(root) / "plan.json")
    if plan is None:
        die("no .prod-build/plan.json (run `pb.py init`)", 1)
    return plan


def save_plan(root: Path, plan: dict) -> None:
    write_json(pb_dir(root) / "plan.json", plan)


def task_map(plan: dict) -> dict:
    return {t.get("id"): t for t in plan.get("tasks", []) if isinstance(t, dict)}


def find_cycle(tasks: dict):
    color, stack = {}, []

    def visit(n):
        color[n] = 1
        stack.append(n)
        for d in tasks[n].get("deps", []) or []:
            if d not in tasks:
                continue
            if color.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if color.get(d) is None:
                r = visit(d)
                if r:
                    return r
        stack.pop()
        color[n] = 2
        return None

    for n in tasks:
        if color.get(n) is None:
            r = visit(n)
            if r:
                return r
    return None


def layers(tasks: dict) -> list:
    active = {k: v for k, v in tasks.items() if v.get("status") != "skip"}
    indeg = {k: 0 for k in active}
    for k, v in active.items():
        for d in v.get("deps", []) or []:
            if d in active:
                indeg[k] += 1
    out, ready = [], sorted(k for k, n in indeg.items() if n == 0)
    seen = set()
    while ready:
        out.append(ready)
        seen.update(ready)
        nxt = []
        for k, v in active.items():
            if k in seen or k in nxt:
                continue
            if all(d in seen or d not in active for d in (v.get("deps", []) or [])):
                nxt.append(k)
        ready = sorted(nxt)
    return out


def conflict_reasons(a: dict, b: dict) -> list:
    reasons = []
    wa, wb = a.get("writes", []) or [], b.get("writes", []) or []
    for x in wa:
        for y in wb:
            if paths_overlap(x, y):
                reasons.append(f"both write {x if len(x) <= len(y) else y}")
                break
        if reasons:
            break
    hot_a = [x for x in wa if HOT_FILES.search(norm_path(x))]
    hot_b = [y for y in wb if HOT_FILES.search(norm_path(y))]
    if hot_a and hot_b and not reasons:
        reasons.append(f"both touch shared config/lockfile/migrations ({hot_a[0]}, {hot_b[0]})")
    ra, rb = a.get("runtime") or {}, b.get("runtime") or {}
    ports = set(ra.get("ports", []) or []) & set(rb.get("ports", []) or [])
    if ports:
        reasons.append(f"same port {sorted(ports)}")
    if ra.get("db") and ra.get("db") == rb.get("db") and ra.get("db") not in ("none", "in-memory"):
        reasons.append(f"same database '{ra.get('db')}'")
    if "migration" in (a.get("risk") or []) and "migration" in (b.get("risk") or []):
        reasons.append("both change the schema")
    return reasons


def lanes(ids: list, tasks: dict) -> list:
    """Greedy grouping of ids into lanes that may run in parallel with each other."""
    groups = []
    for i in ids:
        placed = False
        for g in groups:
            if not any(conflict_reasons(tasks[i], tasks[j]) for j in g):
                g.append(i)
                placed = True
                break
        if not placed:
            groups.append([i])
    return groups


def check_plan(plan: dict) -> tuple:
    errors, warns = [], []
    mode = plan.get("mode")
    if mode not in MODES:
        errors.append(f"mode must be one of {MODES}, got {mode!r}")
    tasks_list = plan.get("tasks")
    if not isinstance(tasks_list, list):
        return [*errors, "tasks must be a list"], warns
    seen = set()
    for t in tasks_list:
        if not isinstance(t, dict):
            errors.append("every task must be an object")
            continue
        tid = t.get("id", "?")
        if not re.match(r"^T\d{2,3}[a-z]?$", str(tid)):
            errors.append(f"{tid}: id must look like T01, T12 or T07a")
        if tid in seen:
            errors.append(f"{tid}: duplicate id")
        seen.add(tid)
        for field in ("title", "objective"):
            if not str(t.get(field, "")).strip():
                errors.append(f"{tid}: missing {field}")
        if t.get("status", "todo") not in STATUSES:
            errors.append(f"{tid}: status must be one of {STATUSES}")
        if not t.get("verify"):
            errors.append(f"{tid}: no verify commands (how will anyone know it works?)")
        if not t.get("acceptance"):
            errors.append(f"{tid}: no acceptance criteria")
        if not t.get("writes"):
            if not re.search(r"(?i)review|verify|audit|deploy|smoke|qa|gate", f"{t.get('role', '')} {t.get('kind', '')}"):
                warns.append(f"{tid}: empty write surface (set \"kind\": \"review\"|\"deploy\"|\"qa\" if it writes no files)")
        elif len(t.get("writes")) > 15:
            warns.append(f"{tid}: writes {len(t['writes'])} paths; split it (one intent, <=15 files)")
        if not str(t.get("rollback", "")).strip():
            (errors if mode == "product" and "migration" in (t.get("risk") or []) else warns).append(
                f"{tid}: no rollback note")
        if t.get("size") and t.get("size") not in ("S", "M", "L"):
            warns.append(f"{tid}: size should be S, M or L")
        if t.get("size") == "L" and mode == "product":
            warns.append(f"{tid}: size L in product mode; consider splitting")
        if t.get("status") == "skip" and not str(t.get("notes", "")).strip():
            errors.append(f"{tid}: skipped without a reason in notes")
    tasks = task_map(plan)
    if tasks and not suite_items(plan):
        warns.append("no top-level \"suite\" (the full test command): `pb.py verify` can't run the whole suite per task")
    for tid, t in tasks.items():
        for d in t.get("deps", []) or []:
            if d not in tasks:
                errors.append(f"{tid}: depends on unknown task {d}")
    cyc = find_cycle(tasks)
    if cyc:
        errors.append("dependency cycle: " + " -> ".join(cyc))
    active = [t for t in tasks_list if isinstance(t, dict) and t.get("status") != "skip"]
    if len(active) > 12 and not plan.get("milestones"):
        warns.append(f"{len(active)} tasks and no milestones; group into milestones of 3-12 tasks")
    if not cyc and plan.get("parallel", True) is not False:
        for layer in layers(tasks):
            for i, a in enumerate(layer):
                for b in layer[i + 1:]:
                    r = conflict_reasons(tasks[a], tasks[b])
                    if r:
                        warns.append(f"{a} and {b} are unordered but conflict ({'; '.join(r)}): "
                                     "they will run one after the other unless isolated")
    return errors, warns


def check_briefs(root: Path, plan: dict) -> tuple:
    """Each brief must be the brief for ITS task: id + title, the verify path, the report block, a BASE line."""
    errors, warns = [], []
    bdir = pb_dir(root) / "briefs"
    if not bdir.is_dir():
        return errors, warns
    tasks = task_map(plan)
    bodies = {}
    for f in sorted(bdir.glob("*.md")):
        m = re.match(r"^(T\d{2,3}[a-z]?)\b", f.stem)
        if not m or m.group(1) not in tasks:
            continue
        tid, t = m.group(1), tasks[m.group(1)]
        text = f.read_text(encoding="utf-8")
        head = "\n".join(text.splitlines()[:3])
        if tid not in head:
            errors.append(f"briefs/{f.name}: heading doesn't name {tid}")
        if t.get("title") and words(t["title"]) and len(words(t["title"]) & words(text)) < min(2, len(words(t["title"]))):
            warns.append(f"briefs/{f.name}: doesn't mention its task title '{t['title']}'")
        runs_verify = re.search(rf"pb\.py\s+verify\s+{tid}\b", text)
        missing = [v for v in (t.get("verify") or []) if not v.lower().startswith(("observe:", "manual:"))
                   and norm_cmd(v) not in norm_cmd(text)]
        if not runs_verify and missing:
            errors.append(f"briefs/{f.name}: neither `pb.py verify {tid}` nor its verify command(s): " + "; ".join(missing[:3]))
        if "STATUS:" not in text:
            errors.append(f"briefs/{f.name}: no report block (STATUS: …)")
        if not re.search(r"(?i)\bBASE\b", text):
            warns.append(f"briefs/{f.name}: no BASE commit line")
        other = [o for o in re.findall(r"\bT\d{2,3}[a-z]?\b", text) if o != tid and o in tasks]
        if other.count(max(set(other), key=other.count) if other else "") > text.count(tid):
            warns.append(f"briefs/{f.name}: mentions {max(set(other), key=other.count)} more often than {tid}: copied brief?")
        body = re.sub(r"\bT\d{2,3}[a-z]?\b", "Txx", text)
        if body in bodies:
            errors.append(f"briefs/{f.name}: same content as briefs/{bodies[body]}")
        bodies[body] = f.name
    return errors, warns


def cmd_plan(args, root: Path) -> int:
    plan = load_plan(root)
    tasks = task_map(plan)
    if args.action == "check":
        errors, warns = check_plan(plan)
        be, bw = check_briefs(root, plan)
        errors, warns = errors + be, warns + bw
        for w in warns:
            print(f"WARN  {w}")
        for e in errors:
            print(f"ERROR {e}")
        print(f"plan check: {len(errors)} error(s), {len(warns)} warning(s), {len(tasks)} task(s)")
        return 1 if errors or (args.strict and warns) else 0
    if find_cycle(tasks):
        die("plan has a dependency cycle; run `pb.py plan check`", 1)
    serial = plan.get("parallel", True) is False
    if args.action == "waves":
        for n, layer in enumerate(layers(tasks), 1):
            groups = [[i] for i in layer] if serial else lanes(layer, tasks)
            desc = "  then  ".join(" || ".join(g) for g in groups)
            print(f"wave {n}: {desc}")
        path = critical_path(tasks)
        if path:
            print("critical path: " + " -> ".join(path))
        return 0
    if args.action == "next":
        ready = [k for k, t in tasks.items() if t.get("status", "todo") == "todo"
                 and all(tasks.get(d, {}).get("status") in ("done", "skip") for d in (t.get("deps") or []))]
        doing = [k for k, t in tasks.items() if t.get("status") == "doing"]
        if doing:
            print("in progress (re-check exit criteria before trusting): " + ", ".join(sorted(doing)))
        if not ready:
            print("no ready tasks" + ("" if doing else " (all done, blocked, or waiting on deps)"))
            return 0
        groups = [[i] for i in sorted(ready)] if serial else lanes(sorted(ready), tasks)
        print("ready now. Tasks on one line may run in parallel; run the lines one after another:")
        for g in groups:
            print("  " + " || ".join(f"{i} {tasks[i].get('title', '')}" for i in g))
        return 0
    return 2


def critical_path(tasks: dict) -> list:
    weight = {"S": 1, "M": 2, "L": 3}
    order = [i for layer in layers(tasks) for i in layer]
    best, prev = {}, {}
    for i in order:
        w = weight.get(tasks[i].get("size"), 1)
        cands = [(best[d], d) for d in (tasks[i].get("deps") or []) if d in best]
        if cands:
            b, d = max(cands)
            best[i], prev[i] = b + w, d
        else:
            best[i] = w
    if not best:
        return []
    end = max(best, key=lambda k: best[k])
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    return list(reversed(path))


# ----------------------------------------------------------------------------- evidence ledger

def ledger_path(root: Path) -> Path:
    """The canonical ledger, or a local one (PB_LEDGER) for parallel lanes and relay clones."""
    alt = os.environ.get("PB_LEDGER")
    if alt:
        p = Path(alt)
        return p if p.is_absolute() else root / p
    return pb_dir(root) / "evidence.jsonl"


def read_ledger(root: Path) -> list:
    p = ledger_path(root)
    if not p.exists():
        return []
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"id": f"?line{n}", "_corrupt": True})
    return out


def record_hash(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def verify_chain(entries: list) -> list:
    problems, prev = [], ""
    for e in entries:
        if e.get("_corrupt"):
            problems.append(f"{e['id']}: unparseable ledger line")
            continue
        if e.get("prev", "") != prev:
            problems.append(f"{e.get('id')}: chain broken (entry edited, removed or hand-written)")
        if record_hash(e) != e.get("hash"):
            problems.append(f"{e.get('id')}: hash mismatch (entry edited by hand)")
        prev = e.get("hash", "")
    return problems


def append_evidence(root: Path, rec: dict) -> dict:
    pb_dir(root).mkdir(parents=True, exist_ok=True)
    entries = read_ledger(root)
    nums = [int(e["id"][1:]) for e in entries if re.match(r"^E\d+$", str(e.get("id", "")))]
    rec["id"] = f"E{(max(nums) + 1 if nums else 1):04d}"
    rec["ts"] = now_iso()
    rec["agent"] = rec.get("agent") or os.environ.get("PB_AGENT", "unknown")
    rec["prev"] = entries[-1].get("hash", "") if entries else ""
    rec["hash"] = record_hash(rec)
    with ledger_path(root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def shell_command(parts: list) -> list:
    cmd = parts[0] if len(parts) == 1 else (
        subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts))
    if os.name != "nt" and shutil.which("bash"):
        return ["bash", "-o", "pipefail", "-c", cmd], cmd
    return cmd, cmd


def cmd_run(args, root: Path) -> int:
    parts = list(args.command or [])
    if parts and parts[0] == "--":
        parts = parts[1:]
    if not parts:
        die("usage: pb.py run [--task ID] [--kind K] -- <command>")
    runnable, display = shell_command(parts)
    if os.name == "nt" and "|" in display:
        print("pb: warning: cmd.exe has no pipefail; a pipe can hide the real exit code", file=sys.stderr)
    logs = pb_dir(root) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        proc = subprocess.run(runnable, cwd=root, shell=isinstance(runnable, str), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=args.timeout)
        code, output = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        code = 124
        output = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) \
            + f"\n[pb] timed out after {args.timeout}s"
    dur = round(time.time() - start, 2)
    clean = redact(output)
    tail = clean.splitlines()[-args.tail:] if args.tail > 0 else []
    expect = "fail" if args.expect_fail else "pass"
    ok = (code != 0) if args.expect_fail else (code == 0)
    kind = args.kind or ("red" if args.expect_fail else "other")
    rec = append_evidence(root, {
        "task": args.task, "kind": kind, "method": "ran", "cmd": redact(display),
        "cwd": ".", "exit": code, "expect": expect, "ok": ok, "duration_s": dur,
        "git": git_info(root), "tree": tree_hash(root), "where": args.where, "url": args.url, "tail": tail[-20:],
    })
    log = logs / f"{rec['id']}.log"
    log.write_text(f"$ {redact(display)}\n# exit {code} in {dur}s at {rec['ts']}\n\n{clean}", encoding="utf-8")
    for line in tail:
        print(line)
    verdict = "PASS" if ok else "FAIL"
    extra = " (expected failure)" if args.expect_fail else ""
    print(f"[{rec['id']}] {verdict}{extra} exit={code} {dur}s  {rec['cmd']}  -> .prod-build/logs/{log.name}")
    if args.expect_fail:
        return 0 if ok else 1  # RED recorded as expected -> success; an unexpected pass is the failure
    return code


def cmd_evidence(args, root: Path) -> int:
    if args.action == "redact":
        if not args.id or not args.pattern or not args.reason:
            die("usage: pb.py evidence redact --id E0012 --pattern '<regex>' --reason '<why>'")
        entries = read_ledger(root)
        broken = verify_chain(entries)
        if broken:
            die("ledger already fails its chain check (" + broken[0] + "); investigate before redacting", 1)
        rx = re.compile(args.pattern)
        target = next((e for e in entries if e.get("id") == args.id), None)
        if not target:
            die(f"unknown evidence id {args.id}", 1)
        old_hash = target.get("hash", "")
        before = json.dumps(target, sort_keys=True)
        for k in ("cmd", "summary", "url"):
            if isinstance(target.get(k), str):
                target[k] = rx.sub("[REDACTED]", target[k])
        if isinstance(target.get("tail"), list):
            target["tail"] = [rx.sub("[REDACTED]", x) for x in target["tail"]]
        if json.dumps(target, sort_keys=True) == before:
            die(f"pattern not found in {args.id}", 1)
        idx = entries.index(target)
        prev = entries[idx - 1]["hash"] if idx > 0 else ""
        for e in entries[idx:]:
            e["prev"] = prev
            e["hash"] = record_hash(e)
            prev = e["hash"]
        ledger_path(root).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
        log = pb_dir(root) / "logs" / f"{args.id}.log"
        if log.exists():
            log.write_text(rx.sub("[REDACTED]", log.read_text(encoding="utf-8")), encoding="utf-8")
        rec = append_evidence(root, {"task": target.get("task"), "kind": "manual", "method": "observed",
                                     "cmd": None, "summary": f"redacted {args.id} (old hash {old_hash[:16]}): {args.reason}",
                                     "exit": None,
                                     "expect": "pass", "ok": True, "git": git_info(root), "where": "local"})
        print(f"redacted {args.id} and re-chained the ledger; audit entry {rec['id']}. Rotate the secret: "
              "history already committed elsewhere still has it.")
        return 0
    if args.action == "add":
        if not args.summary:
            die("evidence add needs --summary")
        rec = append_evidence(root, {
            "task": args.task, "kind": args.kind or "manual", "method": args.method, "cmd": None,
            "summary": redact(args.summary), "exit": None, "expect": "pass", "ok": not args.failed,
            "git": git_info(root), "tree": tree_hash(root), "where": args.where, "url": args.url, "files": args.file or [],
        })
        print(f"[{rec['id']}] recorded {args.method} evidence: {rec['summary']}")
        return 0
    entries = read_ledger(root)
    if args.task:
        entries = [e for e in entries if e.get("task") == args.task]
    if args.failed:
        entries = [e for e in entries if not e.get("ok")]
    for e in entries[-args.limit:]:
        what = e.get("cmd") or e.get("summary") or ""
        print(f"{e.get('id')} {('ok ' if e.get('ok') else 'FAIL'):4} {e.get('method', ''):8} "
              f"{str(e.get('task') or '-'):5} {e.get('kind', ''):9} {e.get('where', '')}  {what[:90]}")
    problems = verify_chain(read_ledger(root))
    for p in problems:
        print(f"LEDGER {p}")
    return 1 if problems else 0


# ----------------------------------------------------------------------------- smoke

class _Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.urls.append(a["src"])
        elif tag == "link" and a.get("href") and any(
                r in (a.get("rel") or "").lower() for r in ("stylesheet", "icon", "preload", "modulepreload", "manifest")):
            self.urls.append(a["href"])
        elif tag == "img" and a.get("src") and not a["src"].startswith("data:"):
            self.urls.append(a["src"])


ERROR_MARKERS = ("Application error: a client-side exception", "Internal Server Error",
                 "This page could not be found", "An unexpected error has occurred",
                 "Traceback (most recent call last)", "FUNCTION_INVOCATION_FAILED", "DEPLOYMENT_NOT_FOUND")


def fetch(url: str, timeout: float, method: str = "GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "prod-build-smoke/1.0"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2_000_000) if method == "GET" else b""
            return r.status, body, round(time.time() - t, 2), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.read(200_000) if method == "GET" else b"", round(time.time() - t, 2), ""
    except Exception as e:  # noqa: BLE001 - report any network failure as a finding
        return None, str(e).encode(), round(time.time() - t, 2), ""


def cmd_smoke(args, root: Path) -> int:
    base = args.url.rstrip("/")
    findings, lines = [], []
    for route in args.routes:
        url = base + (route if route.startswith("/") else "/" + route)
        status, body, secs, ctype = fetch(url, args.timeout)
        lines.append(f"{status} {secs:>5}s {url}")
        if status is None or status >= 400:
            findings.append(f"{url} -> {status or body.decode('utf-8', 'replace')[:120]}")
            continue
        if secs > args.slow:
            findings.append(f"{url} slow: {secs}s (cold start? warm it before a demo)")
        text = body.decode("utf-8", "replace")
        for marker in ERROR_MARKERS:
            if marker in text:
                findings.append(f"{url} page contains '{marker}'")
        if "html" in ctype or text.lstrip().lower().startswith("<!doctype html"):
            p = _Assets()
            try:
                p.feed(text)
            except Exception:  # noqa: BLE001
                pass
            for ref in dict.fromkeys(p.urls):
                aurl = urllib.parse.urljoin(url, ref)
                if urllib.parse.urlparse(aurl).netloc != urllib.parse.urlparse(base).netloc and not args.external:
                    continue
                st, _, _, _ = fetch(aurl, args.timeout, "HEAD")
                if st in (405, 501):
                    st, _, _, _ = fetch(aurl, args.timeout)
                if st is None or st >= 400:
                    findings.append(f"asset {aurl} -> {st}")
    for l in lines:
        print(l)
    for f in findings:
        print(f"FINDING {f}")
    ok = not findings
    rec = append_evidence(root, {
        "task": args.task, "kind": "smoke", "method": "ran",
        "cmd": f"pb.py smoke {args.url} --routes " + " ".join(args.routes),
        "exit": 0 if ok else 1, "expect": "pass", "ok": ok, "git": git_info(root), "tree": tree_hash(root), "where": args.where,
        "url": base, "tail": (lines + [f"FINDING {f}" for f in findings])[-20:],
    })
    print(f"[{rec['id']}] {'PASS' if ok else 'FAIL'} smoke {base} ({len(args.routes)} route(s), {len(findings)} finding(s)). "
          "Console errors need a browser check; record it with `pb.py evidence add --method observed`.")
    return 0 if ok else 1


# ----------------------------------------------------------------------------- tasks

def norm_cmd(cmd: str) -> str:
    """Normalise a command for matching: squash spaces and unify the pb.py spelling. VAR=val prefixes are
    significant (a run that only passes with an extra variable is a different check), so they are kept."""
    c = re.sub(r"\s+", " ", redact(cmd or "")).strip()
    c = re.sub(r"(^|&&\s*|;\s*)(?:python3?|py)\s+(?:\./)?(?:\.prod-build/|\S*/)?pb\.py\b", r"\1pb.py", c)
    return c.strip("'\" ")


def pass_evidence(e: dict) -> bool:
    """Evidence that shows something WORKS: passed, expected to pass, and ran or was observed."""
    return bool(e.get("ok")) and e.get("expect", "pass") == "pass" and e.get("method") in ("ran", "observed")


def suite_items(plan: dict) -> list:
    s = plan.get("suite") or []
    return [s] if isinstance(s, str) else list(s)


def verify_items(t: dict, plan: dict) -> list:
    items = list(t.get("verify") or [])
    if t.get("suite", True) is not False:
        items += [x for x in suite_items(plan) if norm_cmd(x) not in {norm_cmd(i) for i in items}]
    return items


def evidence_num(e: dict) -> int:
    m = re.match(r"^E(\d+)$", str(e.get("id", "")))
    return int(m.group(1)) if m else 0


def words(text: str) -> set:
    stop = {"with", "that", "this", "from", "into", "have", "been", "were", "they", "then", "than", "when", "what"}
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 4 and w not in stop}


def match_observations(items: list, observed: list) -> dict:
    """Assign each observe: item its own observed entry (best word overlap, each entry used once)."""
    out, used = {}, set()
    for item in items:
        want = words(item.split(":", 1)[1] if ":" in item else item)
        best, best_score = None, -1
        for e in reversed(observed):
            if e["id"] in used:
                continue
            score = len(want & words(e.get("summary", "")))
            if score > best_score:
                best, best_score = e, score
        need = 1 if len(want) <= 2 else 2
        if best is not None and (best_score >= need or not want):
            out[item] = best
            used.add(best["id"])
    return out


def verify_status(t: dict, entries: list, plan: dict = None) -> tuple:
    """For each verify item: (item, state, latest_entry) with state pass | fail | missing, from the LATEST run
    recorded since the task was (re)started."""
    out = []
    since = int(t.get("started_after") or 0)
    mine = [e for e in entries if e.get("task") == t.get("id") and e.get("expect", "pass") == "pass"
            and evidence_num(e) > since]
    items = verify_items(t, plan or {})
    observe = [v for v in items if v.strip().lower().startswith(("observe:", "manual:"))]
    matched = match_observations(observe, [e for e in mine if e.get("method") == "observed"])
    for v in items:
        if v in observe:
            e = matched.get(v)
            out.append((v, "missing" if not e else ("pass" if e.get("ok") else "fail"), e))
            continue
        runs = [e for e in mine if e.get("cmd") and norm_cmd(e["cmd"]) == norm_cmd(v)]
        out.append((v, "missing" if not runs else ("pass" if runs[-1].get("ok") else "fail"), runs[-1] if runs else None))
    return out


def cmd_task(args, root: Path) -> int:
    plan = load_plan(root)
    tasks = task_map(plan)
    t = tasks.get(args.id)
    if not t:
        die(f"unknown task {args.id}", 1)
    note = (args.note or "").strip()
    stamp = f"{today()} {args.action}"
    if args.action in ("skip", "block", "reopen") and not note:
        die(f"`task {args.id} {args.action}` needs --note with the reason")
    if args.action == "start":
        blockers = [d for d in (t.get("deps") or []) if tasks.get(d, {}).get("status") not in ("done", "skip")]
        if blockers and not args.force:
            die(f"{args.id} depends on unfinished {', '.join(blockers)} (use --force to override)", 1)
        gi = git_info(root)
        if gi["dirty"]:
            print("WARN  uncommitted changes outside .prod-build/: commit the plan/briefs first so BASE is meaningful")
        t["status"] = "doing"
        t["base"] = gi["sha"]
        if not plan.get("base"):
            plan["base"] = gi["sha"]
        t["started_after"] = max([evidence_num(e) for e in read_ledger(root)] or [0])
        print(f"{args.id} BASE {gi['sha']} (put this in the brief; intake diffs from here). "
              f"Only evidence after E{t['started_after']:04d} counts toward done.")
    elif args.action == "done":
        entries = read_ledger(root)
        ledger = {e.get("id"): e for e in entries}
        ids = [x.strip() for x in (args.evidence or "").split(",") if x.strip()]
        missing = [i for i in ids if i not in ledger]
        if missing:
            die(f"unknown evidence id(s): {', '.join(missing)}", 1)
        for_task = [e for e in entries if e.get("task") == args.id]
        pool = [ledger[i] for i in ids] or for_task
        passing = [e for e in pool if pass_evidence(e)]
        states = verify_status(t, entries, plan)
        failing = [v for v, st, _ in states if st == "fail"]
        unmatched = [v for v, st, _ in states if st == "missing"]
        now_tree = tree_hash(root)
        stale = [f"{v} ({e['id']})" for v, st, e in states
                 if st == "pass" and e and e.get("tree") and now_tree and e["tree"] != now_tree
                 and not v.strip().lower().startswith(("observe:", "manual:"))]
        problems = []
        if stale:
            problems.append("code changed since the passing run of: " + "; ".join(stale) + f" (re-run `pb.py verify {args.id}`)")
        if not passing and not [e for _, st, e in states if st == "pass"]:
            problems.append("no passing evidence (RED/expected-failure runs don't count)")
        if failing:
            problems.append("latest run FAILED for: " + "; ".join(failing))
        if unmatched:
            problems.append("never run: " + "; ".join(unmatched) + f" (`pb.py verify {args.id}` runs every item exactly as written)")
        if problems and not args.force:
            die(f"{args.id} not done: " + " | ".join(problems) + ". Fix and re-run, or --force --note '<why>'.", 1)
        if args.force and not note:
            die("--force needs --note explaining why the evidence is missing")
        latest = [e["id"] for _, st, e in states if st == "pass" and e]
        t["status"] = "done"
        t["evidence"] = sorted(set(latest + [ledger[i]["id"] for i in ids if pass_evidence(ledger[i])]))
        if any(e.get("method") == "reported" for e in pool):
            print("WARN  some evidence is only 'reported' by an agent; re-run the checks yourself before release")
    elif args.action == "skip":
        t["status"] = "skip"
    elif args.action == "block":
        t["status"] = "blocked"
    elif args.action == "reopen":
        t["status"] = "todo"
    if note or args.force:
        t["notes"] = (str(t.get("notes", "")).rstrip() + f"\n[{stamp}] {note}").strip()
    save_plan(root, plan)
    print(f"{args.id} -> {t['status']}")
    return 0


def cmd_verify(args, root: Path) -> int:
    """Run every verify command of a task through the ledger, exactly as written in the plan."""
    plan = load_plan(root)
    t = task_map(plan).get(args.id)
    if not t:
        die(f"unknown task {args.id}", 1)
    worst = 0
    if not suite_items(plan):
        print("note: plan.json has no \"suite\" (the full test command); only the task's own checks will run")
    for v in verify_items(t, plan):
        if v.strip().lower().startswith(("observe:", "manual:")):
            print(f"SKIP  {v}  (record it with `pb.py evidence add --task {args.id} --method observed --summary ...`)")
            continue
        ns = argparse.Namespace(command=[v], task=args.id, kind=None, where=args.where, url=None,
                                expect_fail=False, timeout=args.timeout, tail=args.tail)
        code = cmd_run(ns, root)
        worst = worst or (1 if code else 0)
        if code and not args.keep_going:
            print(f"stopped at the first failure (use --keep-going to run the rest)")
            break
    return worst


# ----------------------------------------------------------------------------- diffcheck / intake

SKIP_DIRS = re.compile(r"(^|/)(node_modules|\.venv|venv|env|dist|build|\.next|\.nuxt|\.svelte-kit|coverage|"
                       r"__pycache__|\.pytest_cache|target|vendor|\.turbo|\.cache|\.git)/")


def untracked(root: Path) -> list:
    files = [f for f in git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines() if f.strip()]
    return [f for f in files if not SKIP_DIRS.search(f)]


def changed_files(root: Path, base: str) -> list:
    out = git(root, "diff", "--name-status", "--no-renames", base)
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0][0], norm_path(parts[-1])))
    for f in untracked(root):
        if not f.startswith(".prod-build/logs/"):
            rows.append(("A", norm_path(f)))
    return rows


def added_lines(root: Path, base: str) -> list:
    out = git(root, "diff", "--no-color", "-U0", "--no-renames", base).stdout
    rows, cur, ln = [], None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = norm_path(line[6:]) if line[4:6] == "b/" else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and cur:
            rows.append((cur, ln, line[1:]))
            ln += 1
    for f in untracked(root)[:2000]:
        p = root / f
        if f.startswith(".prod-build/") or not p.is_file() or p.stat().st_size > 1_000_000:
            continue
        try:
            for n, text in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                rows.append((norm_path(f), n, text))
        except (UnicodeDecodeError, OSError):
            continue
    return rows


def removed_assertions(root: Path, base: str) -> dict:
    out = git(root, "diff", "--no-color", "-U0", "--no-renames", base).stdout
    per, cur = {}, None
    for line in out.splitlines():
        if line.startswith("--- "):
            cur = norm_path(line[6:]) if line[4:6] == "a/" else None
        elif line.startswith("+++ "):
            continue
        elif cur and TEST_FILE.search(cur) and re.search(r"\b(expect|assert\w*|should)\b", line[1:] if line[:1] in "+-" else ""):
            if line.startswith("-"):
                per[cur] = per.get(cur, 0) + 1
            elif line.startswith("+"):
                per[cur] = per.get(cur, 0) - 1
    return {k: v for k, v in per.items() if v > 0}


ENV_FILE = re.compile(r"(^|/)\.env(\.[A-Za-z0-9_-]+)?$")
ENV_TEMPLATE = re.compile(r"\.(example|sample|template|dist|defaults)$")


def diff_findings(root: Path, base: str) -> list:
    if git(root, "rev-parse", "--verify", base + "^{commit}").returncode != 0:
        die(f"unknown git ref {base!r}", 1)
    found = []
    if not (root / ".gitignore").exists() and (root / "node_modules").is_dir():
        found.append(("warn", ".gitignore", 0, "missing .gitignore while node_modules/ exists: it could get committed"))
    for status, path in changed_files(root, base):
        if path.startswith(".prod-build/"):
            continue
        if status == "D" and TEST_FILE.search(path):
            found.append(("error", path, 0, "test file deleted"))
        elif CONFIG_FILE.search(path):
            found.append(("warn", path, 0, "lint/test/type/CI/agent config changed: justify it in the report"))
        if status != "D" and ENV_FILE.search(path) and not ENV_TEMPLATE.search(path):
            tracked = git(root, "ls-files", "--error-unmatch", path).returncode == 0
            if tracked:
                found.append(("error", path, 0, "env file is tracked by git: untrack it, add it to .gitignore, rotate its secrets"))
    for path, ln, text in added_lines(root, base):
        if path.startswith(".prod-build/"):
            continue  # the helper, plan, briefs and ledger are orchestration files, not product code
        if not path.startswith("docs/memory/"):
            for rx, sev, msg in WEAKENING:
                if re.search(rx, text):
                    found.append((sev, path, ln, msg))
        if not path.endswith((".lock", "lock.json", "lock.yaml")) and looks_like_secret(text):
            in_tests = bool(TEST_FILE.search(path) or re.search(r"(^|/)(fixtures?|__fixtures__|testdata)/", path))
            found.append(("warn" if in_tests else "error", path, ln,
                          "possible secret added" + (" in test code (use an obvious fake)" if in_tests else
                                                     " (rotate it if it is real)")))
        if TEST_FILE.search(path) and re.search(r"\b(expect|assert)\w*\s*\(\s*(true|1)\s*\)", text):
            found.append(("warn", path, ln, "tautological assertion"))
    for path, n in removed_assertions(root, base).items():
        found.append(("warn", path, 0, f"{n} more assertion line(s) removed than added"))
    old_pkg = git(root, "show", f"{base}:package.json")
    if old_pkg.returncode == 0 and (root / "package.json").exists():
        try:
            before = json.loads(old_pkg.stdout).get("scripts") or {}
            after = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
            for k, v in before.items():
                if re.match(r"^(test|lint|typecheck|type-check|check|verify|build|e2e)(:|$)", k) and after.get(k) != v:
                    found.append(("error", "package.json", 0,
                                  f"script '{k}' changed ({v!r} -> {after.get(k)!r}): a changed check can fake a pass"))
        except (json.JSONDecodeError, AttributeError):
            pass
    old_plan = git(root, "show", f"{base}:.prod-build/plan.json")
    if old_plan.returncode == 0 and (pb_dir(root) / "plan.json").exists():
        try:
            before = task_map(json.loads(old_plan.stdout))
            after = task_map(load_plan(root))
            for tid, t in before.items():
                a = after.get(tid)
                if a is None:
                    found.append(("error", ".prod-build/plan.json", 0, f"{tid} removed from the plan"))
                    continue
                for field in ("acceptance", "verify", "writes"):
                    if t.get(field) != a.get(field):
                        found.append(("warn", ".prod-build/plan.json", 0,
                                      f"{tid}.{field} changed since {base[:10]} (executors may only change status/notes)"))
        except json.JSONDecodeError:
            pass
    return found


def report_base(root: Path, tid: str):
    report = pb_dir(root) / "reports" / f"{tid}.md"
    if report.exists():
        m = re.search(r"(?im)^\s*COMMITS:\s*([0-9a-f]{6,40})\s*\.\.", report.read_text(encoding="utf-8"))
        if m and git(root, "rev-parse", "--verify", m.group(1) + "^{commit}").returncode == 0:
            return m.group(1)
    return None


def pick_base(root: Path, plan: dict, tid, explicit):
    if explicit:
        return explicit
    t = task_map(plan).get(tid) if tid else None
    return (t or {}).get("base") or (report_base(root, tid) if tid else None) or plan.get("base") or "HEAD"


def cmd_diffcheck(args, root: Path) -> int:
    plan = read_json(pb_dir(root) / "plan.json") or {}
    base = pick_base(root, plan, args.task, args.base)
    found = diff_findings(root, base)
    for sev, path, ln, msg in found:
        loc = f"{path}:{ln}" if ln else path
        print(f"{sev.upper():5} {loc}  {msg}")
    errors = sum(1 for f in found if f[0] == "error")
    print(f"diffcheck vs {base}: {errors} error(s), {len(found) - errors} warning(s)")
    return 1 if errors else 0


def cmd_intake(args, root: Path) -> int:
    plan = load_plan(root)
    t = task_map(plan).get(args.id)
    if not t:
        die(f"unknown task {args.id}", 1)
    base = pick_base(root, plan, args.id, args.base)
    problems, notes = [], []
    if base == "HEAD":
        problems.append(f"no BASE recorded for {args.id}: run `pb.py task {args.id} start` before dispatching, "
                        "or pass --base <commit the work started from>")
    report = pb_dir(root) / "reports" / f"{args.id}.md"
    status = None
    if report.exists():
        m = re.search(r"(?im)^\s*STATUS:\s*([A-Z_]+)", report.read_text(encoding="utf-8"))
        status = m.group(1) if m else None
        if not status:
            problems.append(f"{report.relative_to(root)} has no 'STATUS:' line")
    else:
        problems.append(f"no report at .prod-build/reports/{args.id}.md")
    if status in ("BLOCKED", "NEEDS_CONTEXT"):
        notes.append(f"agent reports {status}: answer the blocker before anything else")
    anc = git(root, "merge-base", "--is-ancestor", base, "HEAD")
    if anc.returncode == 1:
        problems.append(f"base {base} is not an ancestor of HEAD (work started from the wrong commit)")
    found = diff_findings(root, base)
    for sev, path, ln, msg in found:
        (problems if sev == "error" else notes).append(f"{path}{':' + str(ln) if ln else ''} {msg}")
    writes = t.get("writes") or []
    if writes:
        allowed = writes + [".prod-build/**", "docs/memory/**"]
        stray = [p for _, p in changed_files(root, base) if not any(paths_overlap(p, w) for w in allowed)]
        if stray:
            notes.append("changed outside the task's write surface: " + ", ".join(stray[:12]))
    ledger = read_ledger(root)
    problems += [f"ledger: {c}" for c in verify_chain(ledger)]
    states = verify_status(t, ledger, plan)
    if not any(pass_evidence(e) for e in ledger if e.get("task") == args.id):
        problems.append(f"no passing evidence recorded for {args.id} (RED runs don't count)")
    for v, st, _ in states:
        if st != "pass":
            notes.append(f"verify '{v}': {st}")
    for p in problems:
        print(f"PROBLEM {p}")
    for n in notes:
        print(f"NOTE    {n}")
    verdict = "REJECT" if problems else "RE-VERIFY"
    print(f"intake {args.id} vs {base}: {verdict}. Re-run the checks yourself (`pb.py verify {args.id}`) "
          f"before `pb.py task {args.id} done`.")
    return 1 if problems else 0


# ----------------------------------------------------------------------------- memory

def parse_record(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = text[end + 4:]
    meta["_path"] = path
    meta["_body"] = body
    meta["_lines"] = text.count("\n") + 1
    return meta


def split_list(v: str) -> list:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def all_records(root: Path, include_archive: bool = True) -> list:
    m = mem_dir(root)
    recs = []
    folders = [f for _, f in MEM_TYPES.values()] + (["archive"] if include_archive else [])
    for folder in folders:
        d = m / folder
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                recs.append(parse_record(p))
    return recs


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48] or "record"


BODIES = {
    "decision": "## Context\n\n## Decision\n\n## Alternatives rejected (and why)\n\n## Consequences\n\n## Revisit when\n",
    "failure": ("## Attempted\n\n## Failure (exact error signature)\n\n## Root cause (verified, not guessed)\n\n"
                "## Fix (commit / evidence IDs)\n\n## Lesson\nWhen <situation>, do <action>, because <reason>.\n\n"
                "## Early check\n<the cheapest check that would have caught this>\n"),
    "lesson": "When <situation>, do <action>, because <reason>.\n\nDon't apply when: <boundary>\n\nSource: <F-id or URL (date)>\n",
    "assumption": "## Claim\n\n## Risk if wrong\n\n## Validate by\n\n## Status\nopen\n",
    "feedback": "## What the user said (quote)\n\n## Context\n\n## Decision\naccepted | rejected | pending\n\n## Implication (incl. do-not-propose)\n",
    "pattern": "## Task type\n\n## Approach / agent / prompt shape\n\n## Outcome\n\n## Use when\n",
}


def cmd_mem(args, root: Path) -> int:
    act = args.action
    if act == "add":
        if args.type not in MEM_TYPES:
            die(f"type must be one of {', '.join(MEM_TYPES)}")
        if not args.title:
            die("mem add needs --title")
        prefix, folder = MEM_TYPES[args.type]
        recs = all_records(root)
        nums = [int(r["id"].split("-")[-1]) for r in recs if str(r.get("id", "")).startswith(prefix + "-")
                and r["id"].split("-")[-1].isdigit()]
        rid = f"{prefix}-{(max(nums) + 1 if nums else 1):04d}"
        similar = [r for r in recs if r.get("type") == args.type and r.get("status") == "active"
                   and difflib.SequenceMatcher(None, r.get("title", "").lower(), args.title.lower()).ratio() >= 0.8]
        if similar and not args.force:
            die(f"similar active record exists: {similar[0]['id']} '{similar[0].get('title')}'. "
                "Update it (or mark it superseded) instead; --force to add anyway", 1)
        gi = git_info(root)
        meta = {
            "id": rid, "type": args.type, "title": args.title.replace("\n", " "), "status": "active",
            "scope": args.scope, "components": ", ".join(split_list(args.components)),
            "triggers": ", ".join(split_list(args.triggers)), "evidence": ", ".join(split_list(args.evidence)),
            "verified_at": f"{today()}@{gi['sha'] or 'nogit'}", "relates": ", ".join(split_list(args.relates)),
            "supersedes": args.supersedes or "", "helpful": "0", "harmful": "0",
            "cite_hash": cite_hash(root, split_list(args.evidence)),
            "created": today(), "source": args.source or os.environ.get("PB_AGENT", "unknown"),
        }
        d = mem_dir(root) / folder
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{rid}-{slugify(args.title)}.md"
        body = args.body.replace("\\n", "\n") if args.body else BODIES[args.type]
        path.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n" + body,
                        encoding="utf-8")
        if args.supersedes:
            mark(root, args.supersedes, "superseded", by=rid)
        write_index(root)
        print(f"created {path.relative_to(root)} ({rid}); fill in the body, keep it under {CAPS['record_lines']} lines")
        if not meta["evidence"]:
            print("WARN  no --evidence: cite a file (path#L10-40), commit:sha or test:cmd so it can be re-verified")
        return 0
    if act == "find":
        return mem_find(root, args)
    if act == "check":
        return mem_check(root)
    if act == "index":
        write_index(root)
        print("wrote docs/memory/INDEX.md")
        return 0
    if act == "mark":
        return mark(root, args.id, args.how, by=args.by)
    return 2


def citations(rec_or_list) -> list:
    """File citations as (path, anchor) pairs; skips commit:, test:, url:, evidence ids and the ledger itself."""
    raw = split_list(rec_or_list.get("evidence", "")) if isinstance(rec_or_list, dict) else rec_or_list
    out = []
    for c in raw:
        if re.match(r"^(commit|test|url|http|https):", c) or re.match(r"^E\d{4,}$", c):
            continue
        path, _, anchor = c.partition("#")
        path = norm_path(path)
        if path and not path.startswith(".prod-build/"):
            out.append((path, anchor))
    return out


def cited_paths(rec: dict) -> list:
    return [p for p, _ in citations(rec)]


def md_section(text: str, anchor: str):
    """Text of the markdown section whose heading matches the anchor (by text or slug), or None."""
    want = slugify(anchor)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m and (slugify(m.group(2)) == want or m.group(2).strip().lower() == anchor.strip().lower()):
            level, body = len(m.group(1)), []
            for nxt in lines[i + 1:]:
                n = re.match(r"^(#{1,6})\s", nxt)
                if n and len(n.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return None


def cite_hash(root: Path, rec_or_list) -> str:
    h = hashlib.sha256()
    for path, anchor in citations(rec_or_list):
        f = root / path
        if not f.is_file():
            h.update(f"missing:{path}".encode())
            continue
        data = f.read_bytes()
        if anchor and path.lower().endswith(".md") and not re.match(r"^L\d", anchor):
            sec = md_section(data.decode("utf-8", "replace"), anchor)
            data = (sec if sec is not None else f"missing-section:{anchor}").encode()
        h.update(path.encode() + b"\0" + data)
    return h.hexdigest()[:16]


def staleness(root: Path, rec: dict) -> str:
    cites = citations(rec)
    if not cites:
        return "uncited"
    if any(not (root / p).exists() for p, _ in cites):
        return "dead-citation"
    for p, a in cites:
        if a and p.lower().endswith(".md") and not re.match(r"^L\d", a):
            if md_section((root / p).read_text(encoding="utf-8", errors="replace"), a) is None:
                return "dead-citation"
    if rec.get("cite_hash") and rec.get("cite_hash") != cite_hash(root, rec):
        return "needs-verify"
    return "fresh"


def mem_find(root: Path, args) -> int:
    paths = [norm_path(p) for p in split_list(args.paths)]
    terms = [t.lower() for t in split_list(args.terms)]
    segs = {s.lower() for p in paths for s in re.split(r"[/._\-]", p) if len(s) > 2}
    scored = []
    for r in all_records(root, include_archive=False):
        if r.get("status") != "active" or (args.type and r.get("type") != args.type):
            continue
        comps = {c.lower() for c in split_list(r.get("components", ""))}
        trig = " ".join(split_list(r.get("triggers", ""))).lower()
        text = (r.get("title", "") + " " + r["_body"]).lower()
        score = 3 * len(comps & segs)
        score += sum(3 for c in comps if any(c in p.lower() for p in paths))
        score += sum(2 for t in terms if t in trig)
        score += sum(min(text.count(t), 3) for t in terms)
        score += sum(2 for cp in cited_paths(r) for p in paths if paths_overlap(cp, p) or cp.startswith(p))
        if score >= args.min_score or (not paths and not terms):
            h, hm = int(r.get("helpful", "0") or 0), int(r.get("harmful", "0") or 0)
            scored.append((score + h - 2 * hm, r))
    scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    if not scored:
        print("no matching memory")
        return 0
    for score, r in scored[: args.limit]:
        gist = next((l.strip() for l in r["_body"].splitlines()
                     if l.strip() and not l.startswith("#") and not l.startswith("<")), "")
        st = staleness(root, r)
        flag = "" if st == "fresh" else f" [{st}]"
        print(f"{r.get('id')} ({r.get('type')}, score {score}){flag} {r.get('title')}\n    {gist[:160]}\n    "
              f"{r['_path'].relative_to(root)}")
    return 0


def mem_check(root: Path) -> int:
    errors, warns = [], []
    recs = all_records(root)
    ids = {}
    for r in recs:
        rid = r.get("id") or r["_path"].name
        missing = [k for k in MEM_REQUIRED if k not in r]
        if missing:
            errors.append(f"{rid}: missing field(s) {', '.join(missing)}")
        if rid in ids:
            errors.append(f"{rid}: duplicate id ({ids[rid].name}, {r['_path'].name})")
        ids[rid] = r["_path"]
        if r.get("type") not in MEM_TYPES:
            errors.append(f"{rid}: unknown type {r.get('type')!r}")
        if r.get("status") not in MEM_STATUSES:
            errors.append(f"{rid}: unknown status {r.get('status')!r}")
        if r["_lines"] > CAPS["record_lines"]:
            warns.append(f"{rid}: {r['_lines']} lines (cap {CAPS['record_lines']}); condense it")
        if any(looks_like_secret(l) for l in r["_body"].splitlines()):
            errors.append(f"{rid}: looks like it contains a secret")
        if r.get("status") == "active":
            st = staleness(root, r)
            if st != "fresh":
                warns.append(f"{rid}: {st}" + (f" (re-read the cited code, then `pb.py mem mark {rid} verified`)"
                                                 if st == "needs-verify" else
                                                 (" (cite a file, path#L10-40 or ARCHITECTURE.md#Section)"
                                                  if st == "uncited" else "")))
            if int(r.get("harmful", "0") or 0) >= 2 and int(r.get("harmful", "0") or 0) > int(r.get("helpful", "0") or 0):
                warns.append(f"{rid}: marked harmful more than helpful; archive or rewrite it")
            if not r.get("cite_hash") and cited_paths(r):
                warns.append(f"{rid}: no content hash yet; after checking it, run `pb.py mem mark {rid} verified`")
            if "<situation>" in r["_body"] or "<reason>" in r["_body"]:
                warns.append(f"{rid}: template placeholders still in the body")
    for r in recs:
        for rel in split_list(r.get("relates", "")) + split_list(r.get("supersedes", "")):
            if rel not in ids:
                warns.append(f"{r.get('id')}: refers to unknown record {rel}")
    active = [r for r in recs if r.get("status") == "active"]
    if len(active) > CAPS["active"]:
        warns.append(f"{len(active)} active records (cap {CAPS['active']}); archive stale or merge similar ones")
    by_type = {}
    for r in active:
        by_type.setdefault(r.get("type"), []).append(r)
    for rs in by_type.values():
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                if difflib.SequenceMatcher(None, a.get("title", "").lower(), b.get("title", "").lower()).ratio() >= 0.8:
                    warns.append(f"{a.get('id')} and {b.get('id')} look like duplicates; merge them")
    idx = mem_dir(root) / "INDEX.md"
    if idx.exists() and idx.read_text(encoding="utf-8").count("\n") > CAPS["index_lines"]:
        warns.append(f"INDEX.md over {CAPS['index_lines']} lines")
    for w in warns:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"mem check: {len(recs)} record(s), {len(active)} active, {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


def mark(root: Path, rid: str, how: str, by: str | None = None) -> int:
    target = next((r for r in all_records(root) if r.get("id") == rid), None)
    if not target:
        die(f"unknown memory record {rid}", 1)
    path = target["_path"]
    text = path.read_text(encoding="utf-8")

    def setf(t, key, val):
        if re.search(rf"(?m)^{key}:.*$", t[: t.find('\n---', 3) + 1]):
            return re.sub(rf"(?m)^{key}:.*$", f"{key}: {val}", t, count=1)
        return t.replace("\n---", f"\n{key}: {val}\n---", 1)

    if how in ("helpful", "harmful"):
        text = setf(text, how, str(int(target.get(how, "0") or 0) + 1))
    elif how == "verified":
        text = setf(text, "verified_at", f"{today()}@{git_info(root)['sha'] or 'nogit'}")
        text = setf(text, "cite_hash", cite_hash(root, target))
    elif how in ("superseded", "archived", "invalidated"):
        text = setf(text, "status", how)
        if by:
            text = setf(text, "superseded_by", by)
    else:
        die(f"unknown mark {how!r}")
    path.write_text(text, encoding="utf-8")
    if how in ("superseded", "archived", "invalidated"):
        dest = mem_dir(root) / "archive" / path.name
        path.replace(dest)
    write_index(root)
    print(f"{rid}: {how}" + (f" by {by}" if by else ""))
    return 0


def write_index(root: Path) -> None:
    m = mem_dir(root)
    m.mkdir(parents=True, exist_ok=True)
    recs = [r for r in all_records(root, include_archive=False) if r.get("status") == "active"]
    order = {t: i for i, t in enumerate(MEM_TYPES)}
    recs.sort(key=lambda r: (order.get(r.get("type"), 9), r.get("id", "")))
    archived = len(all_records(root)) - len(all_records(root, include_archive=False))
    rows = recs[: CAPS["index_lines"] - 12]
    lines = ["# Memory index", "",
             "Generated by `pb.py mem index`; do not edit by hand. Records are hints until their cited code is re-checked.",
             f"Active: {len(recs)} | archived/superseded: {archived} | search: `python3 .prod-build/pb.py mem find --paths .. --terms ..`",
             "", "| ID | Type | Components | Title | File |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.get('id')} | {r.get('type')} | {r.get('components', '')} | {r.get('title', '')} | "
                     f"{r['_path'].relative_to(m).as_posix()} |")
    if len(recs) > len(rows):
        lines.append(f"\n{len(recs) - len(rows)} more active records: use `mem find`.")
    (m / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- report

def cmd_report(args, root: Path) -> int:
    path = Path(args.file)
    if not path.is_absolute():
        path = (Path.cwd() / path) if (Path.cwd() / path).exists() else root / path
    if not path.exists():
        die(f"no report at {path}", 1)
    text = path.read_text(encoding="utf-8")
    ledger = {e.get("id"): e for e in read_ledger(root)}
    errors, warns = [], []
    sections, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.*)$", line)
        if m:
            cur = m.group(1).strip().lower().replace("optimisation", "optimization")
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    for req in REPORT_SECTIONS:
        if not any(k.startswith(req) or req in k for k in sections):
            errors.append(f"missing section '{req}'")
    for name, lines in sections.items():
        if not any(name.startswith(c) for c in CLAIM_SECTIONS):
            continue
        for line in lines:
            if not re.match(r"^\s*([-*]|\d+[.)])\s+\S", line):
                continue
            ids = EVIDENCE_ID.findall(line)
            if not ids and name.startswith("bugs") and re.search(r"(?i)\bnone\b", line):
                warns.append(f"[{name}] 'none' without evidence: cite the bug-hunt/review evidence id")
                continue
            if not ids and not NOT_RUN.search(line):
                errors.append(f"[{name}] claim without evidence id or 'not run': {line.strip()[:110]}")
            if name.startswith("deployment") and ids and not NOT_RUN.search(line):
                if not any((ledger.get(i) or {}).get("where") in ("preview", "prod") for i in ids):
                    errors.append(f"[{name}] deployment claim cites only local evidence: {line.strip()[:90]}")
            for i in ids:
                e = ledger.get(i)
                if e and e.get("expect") == "fail" and not re.search(r"(?i)\b(red|fail\w*|expected)\b", line):
                    errors.append(f"[{name}] cites {i}, a RED (expected-failure) run, as if it proved a pass")
                    continue
                if not e:
                    errors.append(f"[{name}] cites {i}, which is not in the ledger")
                elif not e.get("ok") and not re.search(r"(?i)\b(fail\w*|red|expected|broke\w*|regress\w*)\b", line):
                    errors.append(f"[{name}] cites {i}, which did not pass: {line.strip()[:90]}")
                elif e.get("method") == "reported":
                    warns.append(f"[{name}] {i} is an agent-reported result, not re-run by the orchestrator")
    mem_ids = re.findall(r"\b(ADR|F|L|A|U|P)-\d{4}\b", "\n".join(sections.get("memory", [])))
    known = {r.get("id") for r in all_records(root)}
    for prefix_num in re.findall(r"\b(?:ADR|F|L|A|U|P)-\d{4}\b", "\n".join(
            l for k, v in sections.items() if k.startswith("memory") for l in v)):
        if prefix_num not in known:
            warns.append(f"[memory] {prefix_num} not found in docs/memory")
    if not mem_ids and not any("none" in l.lower() for k, v in sections.items() if k.startswith("memory") for l in v):
        warns.append("[memory] no memory IDs listed (write 'none' if nothing was worth keeping)")
    chain = verify_chain(list(read_ledger(root)))
    errors += [f"ledger: {c}" for c in chain]
    for w in warns:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"report check: {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


# ----------------------------------------------------------------------------- status

def cmd_status(args, root: Path) -> int:
    plan = read_json(pb_dir(root) / "plan.json")
    if plan is None:
        print("no .prod-build/plan.json here; run `pb.py init --mode <mode>`")
        return 1
    tasks = task_map(plan)
    print(f"{plan.get('project')} | mode {plan.get('mode')} | channel {plan.get('channel')} | base {plan.get('base')}")
    counts = {s: 0 for s in STATUSES}
    for t in tasks.values():
        counts[t.get("status", "todo")] = counts.get(t.get("status", "todo"), 0) + 1
    print("tasks: " + "  ".join(f"{k} {v}" for k, v in counts.items()))
    for t in tasks.values():
        if t.get("status") in ("doing", "blocked"):
            last = str(t.get("notes", "")).strip().splitlines()[-1:] or [""]
            print(f"  {t['id']} [{t['status']}] {t.get('title')}  {last[0][:80]}")
    if not find_cycle(tasks):
        ready = [k for k, t in tasks.items() if t.get("status", "todo") == "todo"
                 and all(tasks.get(d, {}).get("status") in ("done", "skip") for d in (t.get("deps") or []))]
        if ready:
            print("ready: " + ", ".join(sorted(ready)))
    ledger = read_ledger(root)
    fails = [e for e in ledger if not e.get("ok")]
    print(f"evidence: {len(ledger)} entries, {len(fails)} failing" + (f", last {ledger[-1].get('id')}" if ledger else ""))
    for e in ledger[-3:]:
        print(f"  {e.get('id')} {'ok' if e.get('ok') else 'FAIL'} {(e.get('cmd') or e.get('summary') or '')[:80]}")
    chain = verify_chain(ledger)
    if chain:
        print(f"LEDGER PROBLEM: {chain[0]}")
    recs = [r for r in all_records(root, include_archive=False) if r.get("status") == "active"]
    stale = [r.get("id") for r in recs if staleness(root, r) in ("needs-verify", "dead-citation")]
    by = {}
    for r in recs:
        by[r.get("type")] = by.get(r.get("type"), 0) + 1
    print("memory: " + (", ".join(f"{k} {v}" for k, v in by.items()) or "empty") +
          (f" | stale: {', '.join(stale[:8])}" if stale else ""))
    return 0


# ----------------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pb.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", help="project root (default: nearest folder with .prod-build/ or .git)")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.add_argument("--mode", choices=MODES)
    s.add_argument("--channel", choices=CHANNELS, default="direct")
    s.add_argument("--name")
    s.add_argument("--checklists", action="store_true",
                   help="relay: copy the security/verification/deploy/AI checklists into .prod-build/checklists/")

    sub.add_parser("status")

    s = sub.add_parser("plan")
    s.add_argument("action", choices=("check", "waves", "next"))
    s.add_argument("--strict", action="store_true", help="treat warnings as failures")

    s = sub.add_parser("task")
    s.add_argument("id")
    s.add_argument("action", choices=("start", "done", "skip", "block", "reopen"))
    s.add_argument("--note")
    s.add_argument("--evidence", help="comma-separated evidence ids")
    s.add_argument("--force", action="store_true")
    s.add_argument("--strict", action="store_true", help="require evidence for every verify command")

    s = sub.add_parser("run")
    s.add_argument("--task")
    s.add_argument("--kind", choices=KINDS)
    s.add_argument("--where", default="local", choices=("local", "ci", "preview", "prod"))
    s.add_argument("--url")
    s.add_argument("--expect-fail", action="store_true", help="RED proof: the command is expected to fail")
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--tail", type=int, default=30, help="lines of output to print (full log is saved)")
    s.add_argument("command", nargs=argparse.REMAINDER)

    s = sub.add_parser("verify", help="run every verify command of a task through the ledger")
    s.add_argument("id")
    s.add_argument("--where", default="local", choices=("local", "ci", "preview", "prod"))
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--tail", type=int, default=15)
    s.add_argument("--keep-going", action="store_true", help="run the remaining commands after a failure")

    s = sub.add_parser("smoke")
    s.add_argument("url")
    s.add_argument("--routes", nargs="+", default=["/"])
    s.add_argument("--task")
    s.add_argument("--where", default="prod", choices=("local", "ci", "preview", "prod"))
    s.add_argument("--timeout", type=float, default=30)
    s.add_argument("--slow", type=float, default=8.0, help="seconds after which a page counts as slow")
    s.add_argument("--external", action="store_true", help="also check third-party assets")

    s = sub.add_parser("evidence")
    s.add_argument("action", choices=("add", "list", "redact"))
    s.add_argument("--id", help="redact: the evidence id")
    s.add_argument("--pattern", help="redact: regex of the text to remove")
    s.add_argument("--reason", help="redact: why (recorded in an audit entry)")
    s.add_argument("--task")
    s.add_argument("--kind", choices=KINDS)
    s.add_argument("--summary")
    s.add_argument("--method", default="observed", choices=("observed", "reported"))
    s.add_argument("--where", default="local", choices=("local", "ci", "preview", "prod"))
    s.add_argument("--url")
    s.add_argument("--file", action="append", help="screenshot or artifact path (repeatable)")
    s.add_argument("--failed", action="store_true", help="add: the observation found a problem; list: only failures")
    s.add_argument("--limit", type=int, default=40)

    s = sub.add_parser("diffcheck")
    s.add_argument("--base")
    s.add_argument("--task", help="use this task's BASE (recorded by `task start`)")

    s = sub.add_parser("intake")
    s.add_argument("id")
    s.add_argument("--base")

    s = sub.add_parser("mem")
    s.add_argument("action", choices=("add", "find", "check", "index", "mark"))
    s.add_argument("type", nargs="?", help="add: decision|failure|lesson|assumption|feedback|pattern; mark: record id")
    s.add_argument("extra", nargs="?", help="mark: helpful|harmful|verified|superseded|archived|invalidated")
    s.add_argument("--title")
    s.add_argument("--components", default="")
    s.add_argument("--triggers", default="")
    s.add_argument("--evidence", default="", help="path#L1-9, commit:sha, test:cmd, url:..")
    s.add_argument("--relates", default="")
    s.add_argument("--supersedes")
    s.add_argument("--scope", default="project", choices=("project", "global-candidate", "global"))
    s.add_argument("--source")
    s.add_argument("--body", help="record body (use \\n for newlines); default: the type's template")
    s.add_argument("--force", action="store_true")
    s.add_argument("--paths", default="")
    s.add_argument("--terms", default="")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--min-score", type=int, default=2, help="find: drop weaker matches")
    s.add_argument("--id", help="mark: record id")
    s.add_argument("--how", choices=("helpful", "harmful", "verified", "superseded", "archived", "invalidated"))
    s.add_argument("--by", help="mark superseded: the replacing record id")

    s = sub.add_parser("report")
    s.add_argument("file")
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    args = build_parser().parse_args(argv)
    root = find_root(args.root)
    if args.cmd == "init":
        args.mode_given = args.mode is not None
        args.mode = args.mode or "hybrid"
    if args.cmd == "mem" and args.action == "find" and args.type and args.type not in MEM_TYPES:
        die(f"--type for find must be one of {', '.join(MEM_TYPES)}")
    if args.cmd == "mem" and args.action == "mark":
        args.id = args.id or args.type
        args.how = args.how or args.extra
        if not args.id or args.how not in ("helpful", "harmful", "verified", "superseded", "archived", "invalidated"):
            die("usage: pb.py mem mark <ID> helpful|harmful|verified|superseded|archived|invalidated [--by ID]")
    handlers = {"init": cmd_init, "status": cmd_status, "plan": cmd_plan, "task": cmd_task, "run": cmd_run,
                "verify": cmd_verify,
                "smoke": cmd_smoke, "evidence": cmd_evidence, "diffcheck": cmd_diffcheck, "intake": cmd_intake,
                "mem": cmd_mem, "report": cmd_report}
    return handlers[args.cmd](args, root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # output piped into head/less that closed early
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
