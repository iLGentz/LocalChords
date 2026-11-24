"""Rendering dello spartito in TXT, ChordPro e PDF, e delle tab in PDF (reportlab)."""

from __future__ import annotations

import io
from collections.abc import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.export.sheet import ChordsBlock, LyricBlock, SectionBlock, Sheet, SheetMeta, chord_line


def _meta_lines(meta: SheetMeta) -> list[str]:
    parts = []
    if meta.key:
        parts.append(f"Tonalità: {meta.key}")
    if meta.capo:
        parts.append(f"Capo: {meta.capo}")
    if meta.bpm:
        parts.append(f"BPM: {meta.bpm:.0f}")
    lines = [" · ".join(parts)] if parts else []
    lines.extend(meta.notes)
    return lines


def to_txt(sheet: Sheet) -> str:
    m = sheet.meta
    out = [m.title + (f" - {m.artist}" if m.artist else "")]
    if m.album:
        out.append(m.album)
    out.extend(_meta_lines(m))
    out.append("")
    for b in sheet.blocks:
        if isinstance(b, SectionBlock):
            out.extend(["", f"[{b.name}]"])
        elif isinstance(b, ChordsBlock):
            out.append("| " + " | ".join(b.labels) + " |")
        else:
            if b.chords:
                out.append(chord_line(b))
            out.append(b.text)
    return "\n".join(out).rstrip() + "\n"


def to_chordpro(sheet: Sheet) -> str:
    m = sheet.meta
    out = [f"{{title: {m.title}}}"]
    if m.artist:
        out.append(f"{{artist: {m.artist}}}")
    if m.album:
        out.append(f"{{album: {m.album}}}")
    if m.key:
        out.append(f"{{key: {m.key}}}")
    if m.capo:
        out.append(f"{{capo: {m.capo}}}")
    if m.bpm:
        out.append(f"{{tempo: {m.bpm:.0f}}}")
    for note in m.notes:
        out.append(f"{{comment: {note}}}")
    for b in sheet.blocks:
        if isinstance(b, SectionBlock):
            out.extend(["", f"{{comment: {b.name}}}"])
        elif isinstance(b, ChordsBlock):
            out.append(" ".join(f"[{c}]" for c in b.labels))
        else:
            out.append(_inline(b))
    return "\n".join(out).rstrip() + "\n"


def _inline(block: LyricBlock) -> str:
    """Accordi in linea (``[C]parola``) inseriti alla colonna della parola."""
    text = block.text
    for col, name in sorted(block.chords, reverse=True):
        col = min(col, len(text))
        text = text[:col] + f"[{name}]" + text[col:]
    return text


# ------------------------------------------------------------------- PDF

BRAND = colors.HexColor("#9a5700")
MUTED = colors.HexColor("#5c5349")
MARGIN = 18 * mm
MONO = "Courier"
MONO_BOLD = "Courier-Bold"


class _Writer:
    def __init__(self, title: str) -> None:
        self.buffer = io.BytesIO()
        self.canvas = Canvas(self.buffer, pagesize=A4)
        self.canvas.setTitle(title)
        self.canvas.setCreator("LocalChords")
        self.width, self.height = A4
        self.y = self.height - MARGIN
        self.page = 1

    def need(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.footer()
            self.canvas.showPage()
            self.page += 1
            self.y = self.height - MARGIN

    def footer(self) -> None:
        self.canvas.setFont("Helvetica", 8)
        self.canvas.setFillColor(MUTED)
        self.canvas.drawRightString(self.width - MARGIN, MARGIN / 2, f"Pagina {self.page}")

    def text(
        self,
        value: str,
        font: str,
        size: float,
        color: colors.Color = colors.black,
        gap: float = 1.25,
    ) -> None:
        self.need(size * gap)
        self.canvas.setFont(font, size)
        self.canvas.setFillColor(color)
        self.canvas.drawString(MARGIN, self.y - size, value)
        self.y -= size * gap

    def finish(self) -> bytes:
        self.footer()
        self.canvas.save()
        return self.buffer.getvalue()


def _header(w: _Writer, meta: SheetMeta) -> None:
    w.text(meta.title, "Helvetica-Bold", 18)
    subtitle = " · ".join(x for x in (meta.artist, meta.album) if x)
    if subtitle:
        w.text(subtitle, "Helvetica", 11, MUTED)
    for line in _meta_lines(meta):
        w.text(line, "Helvetica", 9, MUTED)
    w.y -= 6


def sheet_pdf(sheet: Sheet) -> bytes:
    w = _Writer(sheet.meta.title)
    _header(w, sheet.meta)
    size = 10
    for b in sheet.blocks:
        if isinstance(b, SectionBlock):
            w.y -= 6
            w.text(b.name.upper(), "Helvetica-Bold", 9, MUTED)
        elif isinstance(b, ChordsBlock):
            w.text("| " + " | ".join(b.labels) + " |", MONO_BOLD, size, BRAND)
        else:
            w.need(size * 2.6)
            if b.chords:
                w.text(chord_line(b), MONO_BOLD, size, BRAND, gap=1.1)
            w.text(b.text, MONO, size)
    return w.finish()


def tabs_pdf(meta: SheetMeta, instrument: str, rows: Iterable[str]) -> bytes:
    w = _Writer(f"{meta.title} - tab {instrument}")
    _header(w, meta)
    w.text(
        f"Tab {instrument} (indicative: corda e tasto stimati automaticamente)",
        "Helvetica",
        9,
        MUTED,
    )
    w.y -= 4
    size = 7.5
    for row in rows:
        lines = row.splitlines()
        w.need(size * 1.15 * len(lines) + 8)
        for line in lines:
            w.text(line, MONO, size, gap=1.15)
        w.y -= 8
    return w.finish()
