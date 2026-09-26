"""Quote matcher (T03, DECISION-RULE §4): a quoted passage against an opinion's text.

Public surface (pure functions; no I/O, no network):

``opinion_text(case_json: dict) -> str``
    Concatenation of ``casebody.opinions[].text`` of a CAP case file, majority
    first (the order CAP gives), joined by blank lines.

``norm_quote(s: str, other: str = "") -> tuple[str, list[int]]``
    §4.1 normalization with an offset map back into ``s``: NFKC; curly quotes and
    dashes straightened; soft hyphens dropped; ``word-\\nword`` / ``word- word``
    joined when the joined word occurs in ``other`` or ``s``; ``[T]he`` → ``the``,
    ``[word]`` → ``word``; ``(citation omitted)``-style parentheticals dropped;
    ellipses (``. . .``, ``...``, ``…``) kept as one ``…`` marker; lowercase;
    apostrophes removed; other punctuation → space; whitespace collapsed.

``check_quote(quote: str, opinion_text: str) -> QuoteCheck``
    Returns a :class:`QuoteMatch` (a :class:`QuoteCheck` with ``closest_passage``,
    ``excerpt``, ``excerpt_highlight`` and ``notes`` added):

    * split the quote on ellipses into ordered segments; segments with fewer than
      4 tokens are not compared (note ``"short quote fragment not checked"``);
    * locate each segment with ``rapidfuzz.fuzz.partial_ratio_alignment`` in the
      normalized opinion, widen the window to token boundaries plus two tokens each
      side, and count differing tokens with ``difflib`` over the best-fitting
      sub-window (the widening tokens never count);
    * segments must appear in the opinion in the quote's order;
    * decision: every segment an exact substring or 0 differing tokens →
      ``verbatim``; 1–3 differing tokens in total and every ratio ≥ 70 →
      ``differs`` (``diff`` lists ``DiffToken(filed, opinion)`` pairs); more than 3,
      any ratio < 70, or order violated → ``not_found``; nothing to compare →
      ``not_checked``.

    ``similarity`` is the minimum segment ratio (0–100). ``closest_passage`` is the
    raw opinion text around the aligned window (about ±200 chars) with
    ``highlight`` = the window inside it; ``excerpt``/``excerpt_highlight`` repeat
    it for ``Evidence``. The classifier (T04) turns ``differs``/``not_found`` into
    class ``quote_not_found``; nothing here decides a class.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Callable, Optional

from rapidfuzz import fuzz

from citememo.models import ClosestPassage, DiffToken, QuoteCheck, QuoteStatus

__all__ = ["QuoteMatch", "check_quote", "norm_quote", "opinion_text", "tokens"]

MIN_SEGMENT_TOKENS = 4
MAX_DIFF_TOKENS = 3
MIN_RATIO = 70.0
CONTEXT_CHARS = 200
WIDEN_TOKENS = 2


class QuoteMatch(QuoteCheck):
    """:class:`QuoteCheck` plus the evidence the memo row shows."""

    closest_passage: Optional[ClosestPassage] = None
    excerpt: Optional[str] = None
    excerpt_highlight: Optional[tuple[int, int]] = None
    notes: list[str] = []


def opinion_text(case_json: dict) -> str:
    """``casebody.opinions[].text`` joined, majority first (CAP's order)."""
    casebody = case_json.get("casebody") or {}
    opinions = casebody.get("opinions") or []
    majority = [o.get("text") or "" for o in opinions if (o.get("type") or "").lower() == "majority"]
    rest = [o.get("text") or "" for o in opinions if (o.get("type") or "").lower() != "majority"]
    return "\n\n".join(t for t in majority + rest if t)


# --------------------------------------------------------------------------- #
# Normalization with an offset map
# --------------------------------------------------------------------------- #

_CURLY_DQ = {"“", "”", "„", "‟", "«", "»"}
_CURLY_SQ = {"‘", "’", "‚", "‛", "′"}
_DASHES = {"–", "—", "‒", "―", "−"}
_DROP = {"­", "​", "﻿"}
_ELLIPSIS = "…"

_HYPHEN_NL = re.compile(r"(\w+)-\s*\n\s*(\w+)")
_HYPHEN_SP = re.compile(r"(\w+)- (\w+)")
_BRACKET_LETTER = re.compile(r"\[(\w)\](\w+)")
_BRACKET_WORD = re.compile(r"\[([\w' ]+)\]")
_BRACKET_ELLIPSIS = re.compile(r"\[\s*(?:\.\s*){3}\s*\]|\[…\]")
_OMITTED = re.compile(
    r"\((?:citations? omitted|internal (?:quotation marks?|citations?|quotations?)(?: and (?:citations?|alterations?))? omitted|"
    r"emphasis (?:added|omitted|in original|supplied)|footnotes? omitted|alterations? (?:omitted|in original)|"
    r"brackets omitted|quotation omitted|cleaned up|internal quotation marks and citation omitted)\)",
    re.IGNORECASE,
)
_ELLIPSES = re.compile(r"(?:\.\s*){3,4}(?!\d)|…")
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")
_CLOSING = set(".,;:!?)\"'\u201d\u2019")


class _Mapped:
    """A string whose every character remembers the source offset it came from."""

    def __init__(self, text: str) -> None:
        self.chars: list[str] = []
        self.src: list[int] = []
        for i, ch in enumerate(text):
            for out in unicodedata.normalize("NFKC", ch):
                self.chars.append(out)
                self.src.append(i)
        self.length = len(text)

    def text(self) -> str:
        return "".join(self.chars)

    def map_chars(self, fn: Callable[[str], Optional[str]]) -> None:
        chars: list[str] = []
        src: list[int] = []
        for ch, s in zip(self.chars, self.src):
            out = fn(ch)
            if out is None:
                continue
            for o in out:
                chars.append(o)
                src.append(s)
        self.chars, self.src = chars, src

    def sub(self, pattern: re.Pattern, repl: Callable[[re.Match], str]) -> None:
        text = self.text()
        chars: list[str] = []
        src: list[int] = []
        pos = 0
        for m in pattern.finditer(text):
            chars.extend(self.chars[pos : m.start()])
            src.extend(self.src[pos : m.start()])
            out = repl(m)
            span_len = m.end() - m.start()
            for k, ch in enumerate(out):
                chars.append(ch)
                if span_len:
                    src.append(self.src[m.start() + min(k, span_len - 1)])
                else:
                    src.append(self.src[m.start()] if m.start() < len(self.src) else self.length)
            pos = m.end()
        chars.extend(self.chars[pos:])
        src.extend(self.src[pos:])
        self.chars, self.src = chars, src

    def offset_map(self) -> list[int]:
        return self.src + [self.length]


def _char_norm(ch: str) -> Optional[str]:
    if ch in _DROP:
        return None
    if ch in _CURLY_DQ:
        return '"'
    if ch in _CURLY_SQ:
        return "'"
    if ch in _DASHES:
        return "-"
    return ch


def _word_set(*texts: str) -> set[str]:
    words: set[str] = set()
    for t in texts:
        words.update(w.lower() for w in re.findall(r"\w+", t))
    return words


def norm_quote(s: str, other: str = "") -> tuple[str, list[int]]:
    """§4.1 normalization of ``s``; returns ``(normalized, to_source)`` with ``len(normalized) + 1`` offsets."""
    m = _Mapped(s)
    m.map_chars(_char_norm)
    words = _word_set(s, other) if (other or "-" in s) else set()

    def join_if_word(match: re.Match) -> str:
        joined = match.group(1) + match.group(2)
        if joined.lower() in words:
            return joined
        return match.group(1) + "-" + match.group(2)

    m.sub(_HYPHEN_NL, join_if_word)
    m.sub(_HYPHEN_SP, join_if_word)
    m.sub(_BRACKET_ELLIPSIS, lambda _m: " " + _ELLIPSIS + " ")
    m.sub(_BRACKET_LETTER, lambda _m: _m.group(1) + _m.group(2))
    m.sub(_BRACKET_WORD, lambda _m: _m.group(1))
    m.sub(_OMITTED, lambda _m: " ")
    m.sub(_ELLIPSES, lambda _m: " " + _ELLIPSIS + " ")
    m.map_chars(lambda ch: None if ch == "'" else (ch.lower() if ch.isalnum() or ch == _ELLIPSIS else " "))
    m.sub(_WS, lambda _m: " ")
    text = m.text()
    to_src = m.offset_map()
    # trim the edges (keep the map aligned)
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    return text[start:end], to_src[start : end + 1]


def tokens(s: str) -> list[str]:
    return _TOKEN.findall(s)


# --------------------------------------------------------------------------- #
# Locate and compare
# --------------------------------------------------------------------------- #


def _token_spans(s: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _TOKEN.finditer(s)]


def _diff(seg_toks: list[str], win_toks: list[str]) -> tuple[int, list[DiffToken]]:
    """Differing tokens between the filed segment and an opinion window.

    Opinion tokens inserted before the first or after the last filed token are
    window edges, not misquotation (a quote may start or stop mid-sentence), so
    they never count.
    """
    sm = difflib.SequenceMatcher(None, seg_toks, win_toks, autojunk=False)
    n = 0
    diff: list[DiffToken] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert" and (i1 == 0 or i1 == len(seg_toks)):
            continue
        n += max(i2 - i1, j2 - j1)
        diff.append(DiffToken(filed=" ".join(seg_toks[i1:i2]), opinion=" ".join(win_toks[j1:j2])))
    return n, diff


def _locate(seg: str, t_norm: str, t_spans: list[tuple[int, int]]) -> tuple[float, int, int, int, list[DiffToken]]:
    """``(ratio, n_diff, win_start, win_end, diff)`` for one segment against the normalized opinion."""
    seg_toks = tokens(seg)
    exact = t_norm.find(seg)
    if exact >= 0:
        return 100.0, 0, exact, exact + len(seg), []
    al = fuzz.partial_ratio_alignment(seg, t_norm)
    if al is None:  # pragma: no cover - rapidfuzz returns None only for empty input
        return 0.0, len(seg_toks), 0, 0, [DiffToken(filed=" ".join(seg_toks), opinion="")]
    ratio = float(al.score)
    d0, d1 = al.dest_start, al.dest_end
    # token indexes covering [d0, d1), widened by WIDEN_TOKENS each side
    first = next((k for k, (a, b) in enumerate(t_spans) if b > d0), len(t_spans) - 1)
    last = next((k for k in range(len(t_spans) - 1, -1, -1) if t_spans[k][0] < d1), first)
    lo = max(0, first - WIDEN_TOKENS)
    hi = min(len(t_spans), last + 1 + WIDEN_TOKENS)
    win_toks = [t_norm[a:b] for a, b in t_spans[lo:hi]]
    best: Optional[tuple[int, int, int, int, list[DiffToken]]] = None  # n, len, a, b, diff
    max_trim = WIDEN_TOKENS + 3  # the alignment window may overshoot by a few tokens on either side
    max_trim_l = min(max_trim, len(win_toks) - 1)
    for a in range(0, max_trim_l + 1):
        for b in range(0, min(max_trim, len(win_toks) - 1 - a) + 1):
            sub = win_toks[a : len(win_toks) - b]
            if not sub:
                continue
            n, diff = _diff(seg_toks, sub)
            cand = (n, len(diff), a, b, diff)
            if best is None or cand[:2] < best[:2]:
                best = cand
    if best is None:  # pragma: no cover
        return ratio, len(seg_toks), d0, d1, []
    n, _, a, b, diff = best
    ws = t_spans[lo + a][0]
    we = t_spans[hi - 1 - b][1]
    return ratio, n, ws, we, diff


def _split_segments(q_norm: str) -> list[str]:
    return [p.strip() for p in q_norm.split(_ELLIPSIS)]


def check_quote(quote: str, opinion_text: str) -> QuoteCheck:
    """Compare a filed quotation with an opinion's text (DECISION-RULE §4); see the module docstring."""
    t_norm, t_map = norm_quote(opinion_text)
    q_norm, _ = norm_quote(quote, opinion_text)
    t_spans = _token_spans(t_norm)
    notes: list[str] = []

    segments = [seg for seg in _split_segments(q_norm) if seg]
    compared = [seg for seg in segments if len(tokens(seg)) >= MIN_SEGMENT_TOKENS]
    if len(compared) < len(segments):
        notes.append("short quote fragment not checked")
    if not compared or not t_norm:
        return QuoteMatch(status="not_checked", quote=quote, similarity=None, segments=0, diff=[], notes=notes)

    ratios: list[float] = []
    total_diff = 0
    diff: list[DiffToken] = []
    windows: list[tuple[int, int]] = []
    in_order = True
    prev_end = -1
    for seg in compared:
        ratio, n, ws, we, seg_diff = _locate(seg, t_norm, t_spans)
        ratios.append(ratio)
        total_diff += n
        diff.extend(seg_diff)
        windows.append((ws, we))
        if ws < prev_end:
            in_order = False
        prev_end = we

    similarity = round(min(ratios), 1)
    status: QuoteStatus
    if not in_order:
        status = "not_found"
        notes.append("the quote's segments appear in the opinion in a different order")
    elif total_diff == 0:
        status = "verbatim"
        if len(compared) > 1:
            notes.append("with an omission marked by ellipsis")
    elif total_diff <= MAX_DIFF_TOKENS and similarity >= MIN_RATIO:
        status = "differs"
    else:
        status = "not_found"

    # Closest passage in raw opinion text: from the first window to the last (or the first when out of order)
    if in_order:
        n_start = windows[0][0]
        n_end = windows[-1][1]
    else:
        n_start, n_end = windows[0]
    raw_start = t_map[min(n_start, len(t_map) - 1)]
    raw_end = t_map[min(n_end, len(t_map) - 1)]
    if raw_end <= raw_start:
        raw_end = min(len(opinion_text), raw_start + 1)
    while raw_end < len(opinion_text) and opinion_text[raw_end] in _CLOSING:
        raw_end += 1
    ctx_start = max(0, raw_start - CONTEXT_CHARS)
    ctx_end = min(len(opinion_text), raw_end + CONTEXT_CHARS)
    excerpt = opinion_text[ctx_start:ctx_end]
    highlight = (raw_start - ctx_start, raw_end - ctx_start)
    closest = ClosestPassage(text=excerpt, similarity=similarity, diff_tokens=diff, status=status, highlight=highlight)

    return QuoteMatch(
        status=status,
        quote=quote,
        similarity=similarity,
        segments=len(compared),
        diff=diff,
        closest_passage=closest,
        excerpt=excerpt,
        excerpt_highlight=highlight,
        notes=notes,
    )
