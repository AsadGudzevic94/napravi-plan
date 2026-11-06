"""Izvoz planova u Word (.docx) i Excel (.xlsx)."""
from __future__ import annotations

import io

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from .modeli import MESECI, Cas, Program
from .pismo import preslovi
from .raspodela import meseci_u_godini


def _zaglavlje(p: Program, naslov: str, nastavnik: str = "", skola: str = "") -> list[str]:
    return [naslov,
            f"Predmet: {p.predmet}   Razred: {p.razred}.{'   Smer: ' + p.smer if p.smer else ''}",
            f"Nedeljni fond: {p.nedeljni_fond:g}   Izvor programa: {p.izvor}",
            f"Škola: {skola}   Nastavnik: {nastavnik}"]


def _landscape(doc: Document) -> None:
    s = doc.sections[0]
    s.orientation = WD_ORIENT.LANDSCAPE
    s.page_width, s.page_height = Cm(29.7), Cm(21.0)  # A4 položeno
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(s, m, Cm(1.5))


def _tabela(doc: Document, zaglavlje: list[str], redovi: list[list], pismo: str = "latinica",
            sirine_cm: list[float] | None = None) -> None:
    t = doc.add_table(rows=1, cols=len(zaglavlje))
    t.style = "Table Grid"
    t.autofit = False
    for i, h in enumerate(zaglavlje):
        c = t.rows[0].cells[i]
        c.text = preslovi(str(h), pismo)
        for r in c.paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(9)
    for red in redovi:
        cells = t.add_row().cells
        for i, v in enumerate(red):
            cells[i].text = "" if v is None else preslovi(str(v), pismo)
            for r in cells[i].paragraphs[0].runs:
                r.font.size = Pt(9)
    if sirine_cm:
        for kol, w in zip(t.columns, sirine_cm):
            kol.width = Cm(w)
        for red in t.rows:
            for c, w in zip(red.cells, sirine_cm):
                c.width = Cm(w)


def globalni_docx(p: Program, gp: dict, nastavnik: str = "", skola: str = "", pismo: str = "latinica") -> bytes:
    doc = Document()
    _landscape(doc)
    linije = _zaglavlje(p, "GLOBALNI (GODIŠNJI) PLAN RADA", nastavnik, skola)
    doc.add_heading(preslovi(linije[0], pismo), level=1)
    for l in linije[1:]:
        doc.add_paragraph(preslovi(l, pismo))
    zag = ["R.b.", "Tema / oblast"] + [n[:3] for n in gp["nazivi_meseci"]] + ["Obr.", "Utv.", "Ost.", "Ukupno"]
    redovi = [[r["rb"] if 0 < r["rb"] < 900 else "", r["tema"]] + [r["po_mesecu"][m] or "" for m in gp["meseci"]] +
              [r["obrada"], r["utvrdjivanje"], r["ostalo"], r["ukupno"]] for r in gp["redovi"]]
    redovi.append(["", "UKUPNO"] + [gp["ukupno_po_mesecu"][m] for m in gp["meseci"]] +
                  [sum(r["obrada"] for r in gp["redovi"]), sum(r["utvrdjivanje"] for r in gp["redovi"]),
                   sum(r["ostalo"] for r in gp["redovi"]), gp["ukupno"]])
    n_mes = len(gp["meseci"])
    _tabela(doc, zag, redovi, pismo, [1.0, 6.5] + [1.35] * n_mes + [1.3, 1.3, 1.3, 1.6])
    b = io.BytesIO()
    doc.save(b)
    return b.getvalue()


KOLONE_OP = ["Č.", "Datum", "Tema", "Nastavna jedinica", "Tip časa", "Ishodi", "Metode", "Oblici rada",
             "Korelacija"]


def _red_op(c: Cas) -> list:
    return [c.redni_broj, c.datum.strftime("%d.%m."), c.tema, c.jedinica, c.tip, c.ishodi, c.metode,
            c.oblici_rada, c.korelacija]


def operativni_docx(p: Program, casovi: list[Cas], mesec: int, nastavnik: str = "", skola: str = "", pismo: str = "latinica") -> bytes:
    doc = Document()
    _landscape(doc)
    linije = _zaglavlje(p, f"OPERATIVNI PLAN RADA — {MESECI[mesec].upper()}", nastavnik, skola)
    doc.add_heading(preslovi(linije[0], pismo), level=1)
    for l in linije[1:]:
        doc.add_paragraph(preslovi(l, pismo))
    _tabela(doc, KOLONE_OP, [_red_op(c) for c in casovi], pismo, [0.9, 1.4, 3.2, 5.0, 2.2, 6.0, 3.3, 2.6, 2.0])
    doc.add_paragraph(preslovi("\nSamoprocena ostvarenosti plana / napomene: ______________________________", pismo))
    b = io.BytesIO()
    doc.save(b)
    return b.getvalue()


def plan_xlsx(p: Program, gp: dict, casovi: list[Cas], pismo: str = "latinica") -> bytes:
    wb = Workbook()
    P = lambda v: preslovi(v, pismo) if isinstance(v, str) else v  # noqa: E731
    ws = wb.active
    ws.title = "Globalni plan"
    for l in _zaglavlje(p, "GLOBALNI PLAN"):
        ws.append([P(l)])
    ws.append([])
    ws.title = P("Globalni plan")
    ws.append([P(x) for x in ["R.b.", "Tema"] + gp["nazivi_meseci"] + ["Obrada", "Utvrđivanje", "Ostalo", "Ukupno"]])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for r in gp["redovi"]:
        ws.append([r["rb"] if 0 < r["rb"] < 900 else "", P(r["tema"])] + [r["po_mesecu"][m] for m in gp["meseci"]] +
                  [r["obrada"], r["utvrdjivanje"], r["ostalo"], r["ukupno"]])
    ws.append(["", P("UKUPNO")] + [gp["ukupno_po_mesecu"][m] for m in gp["meseci"]] + ["", "", "", gp["ukupno"]])
    ws.column_dimensions["B"].width = 40
    for god, mes in meseci_u_godini(casovi):
        w = wb.create_sheet(P(MESECI[mes])[:31])
        w.append([P(x) for x in KOLONE_OP])
        for c in w[1]:
            c.font = Font(bold=True)
        for c in casovi:
            if (c.datum.year, c.datum.month) == (god, mes):
                w.append([P(x) for x in _red_op(c)])
        for col, sir in zip("ABCDEFGHI", (5, 8, 28, 40, 13, 40, 25, 20, 20)):
            w.column_dimensions[col].width = sir
        for red in w.iter_rows(min_row=2):
            for c in red:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()
