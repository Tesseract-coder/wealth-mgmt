"""PDF versions of the CSV exports, laid out to read on a phone: A4 portrait, one card per
row instead of a wide table. Colour carries the meaning: green for buy signals and positive
points, red for sell signals, negatives and stops, amber for reduce/review and grey for hold.
Uses the PDF core fonts, so text is folded to Latin-1 (₹ becomes "Rs") and the file needs
no bundled fonts."""

from collections import Counter
from datetime import date, datetime

from fpdf import FPDF

from app.core.formatting import format_freshness, format_inr, now_ist
from app.core.profiles import get_profiles
from app.export.report import TONE
from app.export.tables import Table, Value

# Characters outside Latin-1 that the exports use, with plain stand-ins.
_FOLD = str.maketrans(
    {"₹": "Rs ", "—": "-", "–": "-", "→": "->", "←": "<-", "≥": ">=", "≤": "<=", "…": "...",
     "‘": "'", "’": "'", "“": '"', "”": '"', "•": "·", "×": "x", "≈": "~", "−": "-", "​": ""}
)  # fmt: skip

RGB = tuple[int, int, int]
INK: RGB = (31, 41, 55)
MUTED: RGB = (107, 114, 128)
LINE: RGB = (226, 230, 236)
TRACK: RGB = (236, 239, 243)
BAND: RGB = (17, 24, 39)
# tone → (text / accent, soft background)
TONES: dict[str, tuple[RGB, RGB]] = {
    "good": ((21, 128, 61), (220, 252, 231)),
    "bad": ((185, 28, 28), (254, 226, 226)),
    "warn": ((161, 98, 7), (254, 243, 199)),
    "neutral": ((75, 85, 99), (229, 231, 235)),
    "muted": ((107, 114, 128), (243, 244, 246)),
}

# How the PDF treats a column, by header name (the tables share these names).
SCORES = ("Composite", "Technical", "Fundamental")
SIGNED = {"P&L", "P&L %", "XIRR %", "1y %", "3y %", "5y %", "Benchmark 3y %"}
RED = {"Stop", "Stop %", "Trailing stop"}
GREEN = {"Target 1", "Target 2", "Target 3"}
# "; "-joined lists drawn as bullets: positives on the left, negatives on the right.
GOOD_POINTS = ("Top bullish", "Positives")
BAD_POINTS = ("Red flags", "Top bearish", "Concerns")
ORDER = [
    "strong_buy", "buy", "continue", "hold", "review", "reduce", "switch", "sell", "no_signal",
    "insufficient_data",
]  # fmt: skip
CONFIDENCE = {"high": "good", "medium": "warn", "low": "muted"}

MARGIN = 12
PAD = 5  # inside a card
LONG = 24  # values longer than this get a full-width line instead of a grid cell


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


def _value_tone(label: str, raw: Value, text: str) -> str | None:
    if label in SIGNED and isinstance(raw, int | float) and raw:
        return "good" if raw > 0 else "bad"
    if label in RED or (label == "Stop breached" and text == "yes"):
        return "bad"
    if label in GREEN:
        return "good"
    if label == "Confidence":
        return CONFIDENCE.get(text.lower())
    return None


class _Doc(FPDF):
    def __init__(self, title: str, footer_note: str) -> None:
        super().__init__(orientation="portrait", unit="mm", format="A4")
        self.title_text = title
        self.footer_note = footer_note
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=16)

    def header(self) -> None:
        if self.page_no() == 1:  # the first page has the full title band instead
            return
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, _text(self.title_text), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*LINE)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=7)
        self.set_text_color(*MUTED)
        self.cell(0, 4, _text(f"{self.footer_note} · page {self.page_no()}/{{nb}}"), align="C")


def table_pdf(t: Table) -> bytes:
    """The table as colour-coded cards: one per row, empty values left out."""
    generated = format_freshness(now_ist())
    doc = _Doc(t.title, f"{t.title} · {generated} · Not investment advice")
    doc.alias_nb_pages()
    doc.add_page()
    _title_band(doc, t, generated)

    sig_col = t.header.index("Signal") if "Signal" in t.header else None
    labels = [str(r[sig_col] or "") for r in t.rows] if sig_col is not None else []
    tones = [TONE.get(k, "muted") for k in t.signals] + ["muted"] * (len(t.rows) - len(t.signals))
    if labels:
        _summary(doc, labels, tones, t.signals)

    if not t.rows:
        doc.set_font("Helvetica", size=11)
        doc.set_text_color(*INK)
        doc.multi_cell(doc.epw, 6, _text(t.empty_note or "Nothing to show."))

    for i, row in enumerate(t.rows):
        _card(doc, t, i, row, sig_col, tones[i])

    doc.ln(2)
    doc.set_font("Helvetica", "I", 8)
    doc.set_text_color(*MUTED)
    doc.multi_cell(doc.epw, 4, _text(get_profiles().disclaimer))
    return bytes(doc.output())


def _title_band(doc: _Doc, t: Table, generated: str) -> None:
    doc.set_fill_color(*BAND)
    doc.rect(0, 0, doc.w, 34, style="F")
    doc.set_xy(MARGIN, 9)
    doc.set_font("Helvetica", "B", 18)
    doc.set_text_color(255, 255, 255)
    doc.cell(doc.epw, 9, _text(t.title), new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", size=9)
    doc.set_text_color(203, 213, 225)
    doc.multi_cell(doc.epw, 4.5, _text(f"{t.context}\nGenerated {generated}"))
    doc.set_y(max(doc.get_y(), 34) + 6)


def _summary(doc: _Doc, labels: list[str], tones: list[str], keys: list[str]) -> None:
    """One chip per signal with its count, strongest buy first."""
    tone_of = dict(zip(labels, tones, strict=True))
    rank = {
        label: ORDER.index(k) if k in ORDER else len(ORDER)
        for label, k in zip(labels, keys, strict=False)
    }
    counts = sorted(Counter(labels).items(), key=lambda kv: (rank.get(kv[0], len(ORDER)), kv[0]))
    x, y = float(MARGIN), doc.get_y()
    for label, n in counts:
        w = _chip(doc, x, y, f"{label}  {n}", tone_of[label], measure=True)
        if x + w > doc.w - MARGIN:
            x, y = MARGIN, y + 8
        x += _chip(doc, x, y, f"{label}  {n}", tone_of[label]) + 2
    doc.set_xy(MARGIN, y + 7)
    doc.set_font("Helvetica", size=7.5)
    doc.set_text_color(*MUTED)
    doc.cell(0, 4, _text("Green: buy / positive · Amber: reduce or review · Grey: hold · "
                         "Red: sell / negative"), new_x="LMARGIN", new_y="NEXT")  # fmt: skip
    doc.ln(4)


def _chip(doc: FPDF, x: float, y: float, text: str, tone: str, measure: bool = False) -> float:
    fg, bg = TONES[tone]
    doc.set_font("Helvetica", "B", 8.5)
    w = doc.get_string_width(_text(text)) + 6
    if not measure:
        doc.set_fill_color(*bg)
        doc.rect(x, y, w, 5.6, style="F", round_corners=True, corner_radius=2.8)
        doc.set_text_color(*fg)
        doc.set_xy(x, y)
        doc.cell(w, 5.6, _text(text), align="C")
    return w


def _card(doc: _Doc, t: Table, i: int, row: list[Value], sig_col: int | None, tone: str) -> None:
    """Measure the card off-page, move to a new page if it doesn't fit, then draw its
    background and accent bar under the content."""
    y0 = doc.get_y()
    with doc.offset_rendering():  # everything drawn here is rolled back afterwards
        doc.set_auto_page_break(False)
        _card_body(doc, t, i, row, sig_col, tone)
        height = doc.get_y() - y0
    fits_page = height < doc.eph - 10
    if fits_page and y0 + height > doc.page_break_trigger:
        doc.add_page()
    y0 = doc.get_y()
    if fits_page:  # a card taller than a page is drawn without its frame
        fg, _ = TONES[tone]
        doc.set_draw_color(*LINE)
        doc.set_fill_color(255, 255, 255)
        doc.set_line_width(0.3)
        doc.rect(MARGIN, y0, doc.epw, height, style="DF", round_corners=True, corner_radius=2.5)
        doc.set_fill_color(*fg)
        doc.rect(MARGIN, y0, 1.8, height, style="F", round_corners=True, corner_radius=0.9)
    _card_body(doc, t, i, row, sig_col, tone)
    doc.ln(4)


def _card_body(
    doc: FPDF, t: Table, i: int, row: list[Value], sig_col: int | None, tone: str
) -> None:
    money = set(t.inr_columns) | ({1} if i in t.inr_rows else set())
    cells = [(t.header[c], v, _fmt(v, c in money)) for c, v in enumerate(row)]
    heading = " · ".join(s for c, (_, _, s) in enumerate(cells) if c in t.heading and s)
    signal = cells[sig_col][2] if sig_col is not None else ""
    rest = [
        (k, v, s) for c, (k, v, s) in enumerate(cells) if s and c not in t.heading and c != sig_col
    ]
    scores = [(k, v) for k, v, _ in rest if k in SCORES and isinstance(v, int | float)]
    good = [(k, s) for k, _, s in rest if k in GOOD_POINTS]
    bad = [(k, s) for k, _, s in rest if k in BAD_POINTS]
    lists = GOOD_POINTS + BAD_POINTS
    plain = [(k, v, s) for k, v, s in rest if k not in SCORES and k not in lists]
    short = [x for x in plain if len(x[2]) <= LONG]
    long = [x for x in plain if len(x[2]) > LONG]

    left, inner = MARGIN + PAD, doc.epw - 2 * PAD
    y = doc.get_y() + PAD

    # Heading, with the signal badge on the right.
    badge = _chip(doc, 0, 0, signal, tone, measure=True) if signal else 0
    doc.set_xy(left, y)
    doc.set_font("Helvetica", "B", 12)
    doc.set_text_color(*INK)
    doc.multi_cell(inner - badge - 3, 6, _text(heading or f"Row {i + 1}"))
    after_heading = doc.get_y()
    if signal:
        _chip(doc, left + inner - badge, y + 0.2, signal, tone)
    doc.set_y(max(after_heading, y + 6) + 2.5)

    if scores:
        _scores(doc, left, inner, scores)

    cols = 4
    cw = (inner - (cols - 1) * 4) / cols
    for j in range(0, len(short), cols):
        y = doc.get_y()
        bottoms = []
        for col, (k, v, s) in enumerate(short[j : j + cols]):
            doc.set_xy(left + col * (cw + 4), y)
            _pair(doc, cw, k, s, _value_tone(k, v, s))
            bottoms.append(doc.get_y())
        doc.set_y(max(bottoms))
    for k, v, s in long:
        doc.set_x(left)
        _pair(doc, inner, k, s, _value_tone(k, v, s))

    if good or bad:
        half = (inner - 6) / 2 if good and bad else inner
        y = doc.get_y()
        bottoms = []
        for x, side, tone_ in ((left, good, "good"), (left + inner - half, bad, "bad")):
            doc.set_y(y)
            for k, s in side:
                _points(doc, x, half, k, s.split("; "), tone_)
            bottoms.append(doc.get_y())
        doc.set_y(max(bottoms))
    doc.set_y(doc.get_y() + PAD - 1.2)


def _scores(doc: FPDF, left: float, inner: float, scores: list[tuple[str, float]]) -> None:
    """0-100 scores as bars, coloured by the signal bands they fall in."""
    p = get_profiles()
    buy = min(r.buy_threshold for r in p.risk_levels.values())
    gap = 6
    w = (inner - gap * (len(scores) - 1)) / len(scores)
    y = doc.get_y()
    for n, (label, v) in enumerate(scores):
        x = left + n * (w + gap)
        tone = "good" if v >= buy else "warn" if v >= p.signals.hold_floor else "bad"
        fg, _ = TONES[tone]
        doc.set_xy(x, y)
        doc.set_font("Helvetica", size=7.5)
        doc.set_text_color(*MUTED)
        doc.cell(w / 2, 4, _text(label))
        doc.set_font("Helvetica", "B", 9)
        doc.set_text_color(*fg)
        doc.cell(w / 2, 4, f"{v:.0f}", align="R")
        doc.set_fill_color(*TRACK)
        doc.rect(x, y + 5, w, 1.8, style="F", round_corners=True, corner_radius=0.9)
        filled = w * max(0.0, min(float(v), 100.0)) / 100
        if filled > 1:
            doc.set_fill_color(*fg)
            doc.rect(x, y + 5, filled, 1.8, style="F", round_corners=True, corner_radius=0.9)
    doc.set_y(y + 10.5)


def _pair(doc: FPDF, w: float, label: str, value: str, tone: str | None) -> None:
    x = doc.get_x()
    doc.set_font("Helvetica", size=7.5)
    doc.set_text_color(*MUTED)
    doc.multi_cell(w, 3.8, _text(label), new_x="LEFT", new_y="NEXT")
    doc.set_x(x)
    doc.set_font("Helvetica", "B" if tone else "", 10)
    doc.set_text_color(*(TONES[tone][0] if tone else INK))
    doc.multi_cell(w, 5, _text(value), new_x="LEFT", new_y="NEXT")
    doc.set_x(x)
    doc.ln(1)


def _points(doc: FPDF, left: float, inner: float, label: str, items: list[str], tone: str) -> None:
    """A labelled list with a coloured dot before each point."""
    fg, _ = TONES[tone]
    doc.set_x(left)
    doc.set_font("Helvetica", "B", 7.5)
    doc.set_text_color(*fg)
    doc.cell(inner, 4.5, _text(label.upper()), new_x="LMARGIN", new_y="NEXT")
    for item in items:
        y = doc.get_y()
        doc.set_fill_color(*fg)
        doc.ellipse(left + 0.6, y + 1.7, 1.6, 1.6, style="F")
        doc.set_xy(left + 4, y)
        doc.set_font("Helvetica", size=9.5)
        doc.set_text_color(*INK)
        doc.multi_cell(inner - 4, 4.6, _text(item), new_x="LMARGIN", new_y="NEXT")
    doc.ln(1.5)
