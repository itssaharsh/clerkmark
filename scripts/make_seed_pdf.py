"""Render seed/sample-motion.txt to seed/sample-motion.pdf with fpdf2.

Letter paper, 1-inch margins, 12 pt Times (core font), double-spaced body,
caption block, page numbers, and the SYNTHETIC label on page 1.

Line wrapping happens only at spaces (fpdf2 does not hyphenate), so a
citation may wrap between tokens but never inside a token; eyecite's
clean_text('all_whitespace') collapses the resulting newlines.

Usage: python scripts/make_seed_pdf.py [--check]
  --check   extract the PDF text with pdfplumber and count eyecite citations
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "seed" / "sample-motion.txt"
OUT = ROOT / "seed" / "sample-motion.pdf"

PT = 12
LINE = PT * 2 / 72 * 25.4  # double spacing in mm (fpdf units)
SINGLE = PT * 1.2 / 72 * 25.4


def ascii_safe(s: str) -> str:
    """Core fonts are cp1252; keep the section sign and em dash, drop the rest."""
    return s.encode("cp1252", errors="replace").decode("cp1252")


class Memo(FPDF):
    def footer(self) -> None:
        self.set_y(-18)
        self.set_font("Times", "", 10)
        self.cell(0, 6, f"{self.page_no()}", align="C")


def is_heading(line: str) -> bool:
    return (
        line.isupper()
        and len(line) < 120
        and not line.startswith("SYNTHETIC")
    ) or re.match(r"^(I|II|III|IV|V|VI)\.\s+[A-Z]", line) is not None


def render() -> Path:
    text = SRC.read_text(encoding="utf-8")
    blocks = [b.strip("\n") for b in text.split("\n\n")]

    pdf = Memo(orientation="P", unit="mm", format="Letter")
    pdf.core_fonts_encoding = "cp1252"  # core Times uses WinAnsi; this keeps the em dash and section sign
    pdf.set_margins(25.4, 25.4, 25.4)
    pdf.set_auto_page_break(auto=True, margin=25.4)
    pdf.add_page()
    pdf.set_font("Times", "", PT)

    # caption ends at the memorandum title (first block starting with PLAINTIFF'S)
    in_caption = True
    for i, block in enumerate(blocks):
        block = ascii_safe(block)
        if i == 0 and block.startswith("SYNTHETIC"):
            pdf.set_font("Times", "B", 10)
            pdf.multi_cell(0, SINGLE, block, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(SINGLE)
            pdf.set_font("Times", "", PT)
            continue
        if in_caption:
            if block.startswith("PLAINTIFF'S MEMORANDUM"):
                in_caption = False
                pdf.ln(SINGLE)
                pdf.set_font("Times", "B", PT)
                pdf.multi_cell(0, SINGLE, block, align="C", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Times", "", PT)
                pdf.ln(SINGLE)
                continue
            # caption lines: single-spaced, centred court name, left-aligned parties
            for ln in block.split("\n"):
                if ln.startswith("UNITED STATES") or ln.startswith("SOUTHERN DISTRICT"):
                    pdf.set_font("Times", "B", PT)
                    pdf.cell(0, SINGLE, ln, align="C", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font("Times", "", PT)
                else:
                    pdf.cell(0, SINGLE, ln, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(SINGLE / 2)
            continue
        lines = block.split("\n")
        if len(lines) == 1 and is_heading(block):
            pdf.set_font("Times", "B", PT)
            pdf.multi_cell(0, LINE, block, align="L", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Times", "", PT)
            continue
        if len(lines) > 1:  # signature / date blocks: single spaced
            for ln in lines:
                pdf.cell(0, SINGLE, ln, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(SINGLE)
            continue
        pdf.multi_cell(0, LINE, block, align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(LINE / 2)

    pdf.output(str(OUT))
    return OUT


def check() -> int:
    import pdfplumber
    from eyecite import clean_text, get_citations

    with pdfplumber.open(str(OUT)) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
    text = "\n".join(pages)
    cites = get_citations(clean_text(text, ["all_whitespace"]))
    kinds = {}
    for c in cites:
        kinds[type(c).__name__] = kinds.get(type(c).__name__, 0) + 1
    full = [c for c in cites if type(c).__name__ == "FullCaseCitation"]
    print(f"pages={len(pages)} chars={len(text)} citations={kinds}")
    for c in full:
        g = c.groups
        print(f"  {g.get('volume')} {g.get('reporter')} {g.get('page')}  {c.metadata.plaintiff!r} v. {c.metadata.defendant!r} ({c.metadata.year})")
    return len(full)


if __name__ == "__main__":
    out = render()
    print("wrote", out)
    if "--check" in sys.argv:
        n = check()
        print("full case citations from PDF text:", n)
        sys.exit(0 if n >= 18 else 1)
