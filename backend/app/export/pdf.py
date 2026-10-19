"""PDF versions of the CSV exports, laid out to read on a phone: A4 portrait, one card per
row (heading, then label: value lines) instead of a wide table. Uses the PDF core fonts, so
text is folded to Latin-1 (₹ becomes "Rs") and the file needs no bundled fonts."""

from datetime import date, datetime

from fpdf import FPDF

from app.core.formatting import format_freshness, format_inr, now_ist
from app.core.profiles import get_profiles
from app.export.tables import Table, Value

# Characters outside Latin-1 that the exports use, with plain stand-ins.
_FOLD = str.maketrans(
    {"₹": "Rs ", "—": "-", "–": "-", "→": "->", "←": "<-", "≥": ">=", "≤": "<=", "…": "...",
     "‘": "'", "’": "'", "“": '"', "”": '"', "•": "·", "×": "x", "≈": "~", "−": "-", "\u200b": ""}
)  # fmt: skip

MARGIN = 12
LONG = 38  # values longer than this get a full-width line instead of half a row


def _text(s: str) -> str:
    return s.translate(_FOLD).encode("latin-1", "replace").decode("latin-1")


def _fmt(v: Value, money: bool) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int | float):
        if money:
            return format_inr(float(v))
        return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    if isinstance(v, datetime):
        return format_freshness(v)
    if isinstance(v, date):
        return f"{v:%d %b %Y}"
    return str(v)


class _Doc(FPDF):
    def __init__(self, footer_note: str) -> None:
        super().__init__(orientation="portrait", unit="mm", format="A4")
        self.footer_note = footer_note
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=7)
        self.set_text_color(120)
        self.cell(0, 4, _text(f"{self.footer_note} · page {self.page_no()}/{{nb}}"), align="C")


def table_pdf(t: Table) -> bytes:
    """The table as cards: one per row, empty values left out, ₹ columns formatted."""
    generated = format_freshness(now_ist())
    doc = _Doc(f"{t.title} · {generated} · Not investment advice")
    doc.alias_nb_pages()
    doc.add_page()
    width = doc.epw

    doc.set_font("Helvetica", "B", 16)
    _block(doc, 8, t.title)
    doc.set_font("Helvetica", size=9)
    doc.set_text_color(90)
    _block(doc, 4.5, f"{t.context}\nGenerated {generated}")
    doc.set_text_color(0)
    doc.ln(3)

    if not t.rows:
        doc.set_font("Helvetica", size=11)
        _block(doc, 6, t.empty_note or "Nothing to show.")

    half = (width - 4) / 2
    for i, row in enumerate(t.rows):
        money = set(t.inr_columns) | ({1} if i in t.inr_rows else set())
        cells = [(t.header[c], _fmt(v, c in money)) for c, v in enumerate(row)]
        heading = " · ".join(v for c, (_, v) in enumerate(cells) if c in t.heading and v)
        rest = [(k, v) for c, (k, v) in enumerate(cells) if c not in t.heading and v]
        short = [(k, v) for k, v in rest if len(v) <= LONG]
        long = [(k, v) for k, v in rest if len(v) > LONG]

        if doc.get_y() > doc.h - 60:  # keep a card's heading with its first lines
            doc.add_page()
        doc.set_draw_color(200)
        doc.line(MARGIN, doc.get_y(), MARGIN + width, doc.get_y())
        doc.ln(2)
        doc.set_font("Helvetica", "B", 12)
        _block(doc, 6, heading or f"Row {i + 1}")
        doc.ln(1)

        for j in range(0, len(short), 2):
            if doc.get_y() > doc.h - 30:  # break before a pair so both columns share a page
                doc.add_page()
            y = doc.get_y()
            heights = []
            for col, (k, v) in enumerate(short[j : j + 2]):
                doc.set_xy(MARGIN + col * (half + 4), y)
                _pair(doc, half, k, v)
                heights.append(doc.get_y())
            doc.set_xy(MARGIN, max(heights))
        for k, v in long:
            _pair(doc, width, k, v)
        doc.ln(3)

    doc.ln(2)
    doc.set_font("Helvetica", "I", 8)
    doc.set_text_color(90)
    _block(doc, 4, get_profiles().disclaimer)
    return bytes(doc.output())


def _block(doc: FPDF, h: float, text: str) -> None:
    """Full-width wrapped text, leaving the cursor at the left margin below it."""
    doc.multi_cell(doc.epw, h, _text(text), new_x="LMARGIN", new_y="NEXT")


def _pair(doc: FPDF, w: float, label: str, value: str) -> None:
    x = doc.get_x()
    doc.set_font("Helvetica", size=8)
    doc.set_text_color(110)
    doc.multi_cell(w, 4, _text(label), new_x="LEFT", new_y="NEXT")
    doc.set_x(x)
    doc.set_font("Helvetica", size=10)
    doc.set_text_color(0)
    doc.multi_cell(w, 5, _text(value), new_x="LEFT", new_y="NEXT")
    doc.set_x(x)
    doc.ln(1.2)
