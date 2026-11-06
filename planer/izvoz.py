"""Izvoz planova u Word (.docx) i Excel (.xlsx)."""
from __future__ import annotations

import io

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from .modeli import MESECI, Cas, Program
from .formule import formatiraj
from .pismo import preslovi as _preslovi


def preslovi(t: str, pismo: str) -> str:
    """Pismo koje je nastavnik izabrao + ispravno zapisane formule (x², log₂, √, ≤)."""
    return _preslovi(formatiraj(t), pismo)
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


# ---------------------------------------------------------------- ZUOV obrasci
# Obrasci „Годишњи план“ i „Оперативни план“ sa https://zuov.gov.rs/obrasci/ (sekcija Školska
# dokumentacija): iste kolone i redosled, uz identifikaciju plana i raspodelu po tipu časa koju
# zahteva program nastave i učenja.

RIMSKI_MESECI = [(9, "IX"), (10, "X"), (11, "XI"), (12, "XII"), (1, "I"), (2, "II"), (3, "III"), (4, "IV"),
                 (5, "V"), (6, "VI")]
MESECI_MALA = {m: n.lower() for m, n in MESECI.items()}
SKRACENICE_TIPA = {"obrada": "O", "utvrđivanje": "U", "ispravka": "U", "provera": "P", "pismeni": "P",
                   "inicijalni": "P", "sistematizacija": "S", "rezerva": "S"}
MK_OPSTE = "kompetencija za učenje, komunikacija, rešavanje problema, saradnja"
MK_PO_PREDMETU = {
    "matemat": "kompetencija za učenje, rešavanje problema, rad sa podacima i informacijama, komunikacija, "
               "saradnja, digitalna kompetencija",
}


def _mk(p: Program) -> str:
    from .ekstrakcija import normalizuj
    n = normalizuj(p.predmet)
    return next((v for k, v in MK_PO_PREDMETU.items() if k in n), MK_OPSTE)


def _novi_dokument() -> Document:
    doc = Document()
    _landscape(doc)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    return doc


def _par(doc, tekst: str, pismo: str, bold: bool = False, velicina: float | None = None, centar: bool = False):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    par = doc.add_paragraph()
    run = par.add_run(preslovi(tekst, pismo))
    run.bold = bold
    if velicina:
        run.font.size = Pt(velicina)
    if centar:
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return par


def _upisi(celija, tekst, pismo: str, bold: bool = False, velicina: float = 10, centar: bool = False) -> None:
    """Upis u ćeliju; više redova → više pasusa."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    linije = str(tekst).split("\n") if tekst not in (None, "") else [""]
    celija.text = ""
    for i, l in enumerate(linije):
        par = celija.paragraphs[0] if i == 0 else celija.add_paragraph()
        run = par.add_run(preslovi(l, pismo))
        run.bold, run.font.size = bold, Pt(velicina)
        if centar:
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _sirine(t, sirine_cm: list[float]) -> None:
    t.autofit = False
    for kol, w in zip(t.columns, sirine_cm):
        kol.width = Cm(w)
    for red in t.rows:
        for c, w in zip(red.cells, sirine_cm):
            c.width = Cm(w)


def _sacuvaj(doc) -> bytes:
    b = io.BytesIO()
    doc.save(b)
    return b.getvalue()


def _identifikacija(p: Program, nastavnik: str, skola: str, odeljenje: str, skolska_godina: str) -> str:
    delovi = [f"Škola: {skola or '________________'}", f"Nastavnik: {nastavnik or '________________'}",
              f"Razred i odeljenje: {p.razred}/{odeljenje or '__'}"]
    if p.smer:
        delovi.append(f"Obrazovni profil: {p.smer}")
    delovi += [f"Školska godina: {skolska_godina or '______'}",
               f"Nedeljni fond: {p.nedeljni_fond:g}", f"Godišnji fond: {p.ukupno_casova}"]
    return "   ".join(delovi)


def globalni_docx(p: Program, gp: dict, nastavnik: str = "", skola: str = "", pismo: str = "latinica",
                  napomena: str = "", odeljenje: str = "", skolska_godina: str = "") -> bytes:
    """Godišnji (globalni) plan po ZUOV obrascu."""
    doc = _novi_dokument()
    _par(doc, "Planiranje nastave i učenja", pismo, velicina=14, centar=True)
    _par(doc, "Godišnji plan*", pismo, bold=True, centar=True)
    _par(doc, f"Godišnji plan (predmet): {p.predmet}", pismo)
    _par(doc, _identifikacija(p, nastavnik, skola, odeljenje, skolska_godina), pismo, velicina=9)
    _par(doc, "*Sastavni deo plana je podzakonski akt koji se odnose na standarde postignuća za program "
              "predmeta određenog nivoa obrazovanja", pismo, velicina=9)

    po_mesecu = {r["rb"]: {m: n for (g, m), n in r["po_mesecu"].items()} for r in gp["redovi"]}
    ukupno_mes = {m: n for (g, m), n in gp["ukupno_po_mesecu"].items()}
    redovi = gp["redovi"]
    t = doc.add_table(rows=2 + len(redovi) + 1, cols=13)
    t.style = "Table Grid"
    _upisi(t.cell(0, 0), "RED. BR.", pismo, True, centar=True)
    _upisi(t.cell(0, 1), "TEMA/\nOBLAST", pismo, True, centar=True)
    t.cell(0, 2).merge(t.cell(0, 11))
    _upisi(t.cell(0, 2), "MESEC", pismo, True, centar=True)
    _upisi(t.cell(0, 12), "UKUPNO", pismo, True, centar=True)
    t.cell(0, 0).merge(t.cell(1, 0))
    t.cell(0, 1).merge(t.cell(1, 1))
    t.cell(0, 12).merge(t.cell(1, 12))
    for j, (_, rim) in enumerate(RIMSKI_MESECI):
        _upisi(t.cell(1, 2 + j), rim, pismo, centar=True)
    rb = 0
    for i, r in enumerate(redovi):
        red = 2 + i
        posebna = not 0 < r["rb"] < 900
        if not posebna:
            rb += 1
        _upisi(t.cell(red, 0), "" if posebna else f"{rb}.", pismo, centar=True)
        _upisi(t.cell(red, 1), r["tema"], pismo, bold=not posebna)
        for j, (m, _) in enumerate(RIMSKI_MESECI):
            _upisi(t.cell(red, 2 + j), po_mesecu[r["rb"]].get(m) or "", pismo, centar=True)
        _upisi(t.cell(red, 12), r["ukupno"], pismo, centar=True)
    zadnji = 2 + len(redovi)
    t.cell(zadnji, 0).merge(t.cell(zadnji, 1))
    _upisi(t.cell(zadnji, 0), "Ukupno", pismo, True, centar=True)
    for j, (m, _) in enumerate(RIMSKI_MESECI):
        _upisi(t.cell(zadnji, 2 + j), ukupno_mes.get(m) or "", pismo, True, centar=True)
    _upisi(t.cell(zadnji, 12), gp["ukupno"], pismo, True, centar=True)
    _sirine(t, [1.6, 7.4] + [1.3] * 10 + [2.2])

    # Tema/oblast — međupredmetne kompetencije (ZUOV primer za srednju školu)
    doc.add_paragraph()
    redovne = [r for r in redovi if 0 < r["rb"] < 900]
    t2 = doc.add_table(rows=1 + len(redovne), cols=3)
    t2.style = "Table Grid"
    for j, h in enumerate(("Redni broj", "TEMA/\nOBLAST", "MEĐUPREDMETNE KOMPETENCIJE")):
        _upisi(t2.cell(0, j), h, pismo, True, centar=True)
    mk = _mk(p)
    po_nazivu = {t.naziv: t for t in p.teme}
    for i, r in enumerate(redovne):
        tm = po_nazivu.get(r["tema"])
        _upisi(t2.cell(1 + i, 0), f"{i + 1}.", pismo, centar=True)
        _upisi(t2.cell(1 + i, 1), r["tema"], pismo, bold=True)
        _upisi(t2.cell(1 + i, 2), ", ".join(tm.kompetencije) if tm and tm.kompetencije else mk, pismo)
    _sirine(t2, [2.0, 9.0, 14.7])

    # raspodela po tipovima časa (program nastave i učenja to traži u godišnjem planu)
    doc.add_paragraph()
    _par(doc, "Raspodela časova po tipu časa", pismo, bold=True, velicina=10)
    t3 = doc.add_table(rows=2 + len(redovi), cols=6)
    t3.style = "Table Grid"
    for j, h in enumerate(("Red. br.", "Tema/oblast", "Obrada", "Utvrđivanje i uvežbavanje",
                           "Ponavljanje, proveravanje i sistematizacija", "Ukupno")):
        _upisi(t3.cell(0, j), h, pismo, True, 9, centar=True)
    rb = 0
    for i, r in enumerate(redovi):
        posebna = not 0 < r["rb"] < 900
        if not posebna:
            rb += 1
        vals = ["" if posebna else f"{rb}.", r["tema"], r["obrada"], r["utvrdjivanje"], r["ostalo"], r["ukupno"]]
        for j, v in enumerate(vals):
            _upisi(t3.cell(1 + i, j), v, pismo, velicina=9, centar=j != 1)
    zadnji = 1 + len(redovi)
    for j, v in enumerate(["", "Ukupno", sum(r["obrada"] for r in redovi), sum(r["utvrdjivanje"] for r in redovi),
                           sum(r["ostalo"] for r in redovi), gp["ukupno"]]):
        _upisi(t3.cell(zadnji, j), v, pismo, True, 9, centar=j != 1)
    _sirine(t3, [1.6, 9.0, 2.6, 3.6, 4.6, 2.2])
    izvor = f"Izvor programa: {p.izvor}." if p.izvor else ""
    if napomena or izvor:
        _par(doc, " ".join(x for x in (izvor, napomena) if x), pismo, velicina=9)
    return _sacuvaj(doc)


def _grupe_po_temi(casovi: list[Cas]) -> list[tuple[str, list[Cas]]]:
    """Časovi meseca grupisani po temi; inicijalni/pismeni/ispravke idu uz temu tokom koje se održavaju."""
    redovni = [c for c in casovi if 0 < c.tema_rb < 900]
    def tema_za(c: Cas) -> str:
        if 0 < c.tema_rb < 900:
            return c.tema
        pre = [r for r in redovni if r.redni_broj < c.redni_broj]
        posle = [r for r in redovni if r.redni_broj > c.redni_broj]
        return (pre[-1] if pre else posle[0]).tema if (pre or posle) else c.tema
    grupe: dict[str, list[Cas]] = {}
    for c in casovi:
        grupe.setdefault(tema_za(c), []).append(c)
    return list(grupe.items())


def operativni_docx(p: Program, casovi: list[Cas], mesec: int, nastavnik: str = "", skola: str = "",
                    pismo: str = "latinica", odeljenje: str = "", korelacija: str = "",
                    sa_datumima: bool = False) -> bytes:
    """Operativni (mesečni) plan po ZUOV obrascu: jedan red po času, a Oblast/Tema, Ishodi,
    Međupredmetno povezivanje i Evaluacija spojeni za celu temu."""
    doc = _novi_dokument()
    _par(doc, "OPERATIVNI PLAN", pismo, bold=True, centar=True)
    for oznaka, vrednost in (("Predmetni nastavnik", nastavnik), ("Predmet", p.predmet),
                             ("Razred i odeljenje", f"{p.razred}/{odeljenje}" if odeljenje else f"{p.razred}/__"),
                             ("Mesec", MESECI_MALA[mesec])):
        _par(doc, f"{oznaka}: {vrednost}", pismo, bold=True)
    if skola or p.smer:
        _par(doc, "   ".join(x for x in (f"Škola: {skola}" if skola else "",
                                         f"Obrazovni profil: {p.smer}" if p.smer else "") if x), pismo, velicina=9)

    grupe = _grupe_po_temi(casovi)
    t = doc.add_table(rows=1 + len(casovi), cols=6)
    t.style = "Table Grid"
    zag = ("Oblast/\nTema", "ISHODI\nNa kraju meseca učenik će biti u stanju da:",
           "REDNI BROJ ČASA I NAZIV NASTAVNE JEDINICE", "TIP ČASA",
           "MEĐUPREDMETNO POVEZIVANJE\nNavesti predmet/e:", "EVALUACIJA ISPLANIRANOG NAKON OSTVARIVANJA")
    for j, h in enumerate(zag):
        _upisi(t.cell(0, j), h, pismo, True, 9, centar=True)
    mk_opste = _mk(p)
    po_nazivu = {t.naziv: t for t in p.teme}
    red = 1
    for tema, cc in grupe:
        tm = po_nazivu.get(tema)
        mk = ", ".join(tm.kompetencije) if tm and tm.kompetencije else mk_opste
        cc = sorted(cc, key=lambda c: c.redni_broj)
        ishodi = list(dict.fromkeys(i.strip() for c in cc for i in c.ishodi.split(";") if i.strip()))
        predmeti = (", ".join(tm.korelacija) if tm and tm.korelacija else "") or korelacija or \
            ", ".join(dict.fromkeys(c.korelacija for c in cc if c.korelacija))
        for k, c in enumerate(cc):
            datum = f" ({c.datum:%d.%m.})" if sa_datumima else ""
            _upisi(t.cell(red + k, 2), f"{c.redni_broj}. {c.jedinica}{datum}", pismo, velicina=9)
            _upisi(t.cell(red + k, 3), SKRACENICE_TIPA.get(c.tip, ""), pismo, velicina=9, centar=True)
        kraj = red + len(cc) - 1
        for j in (0, 1, 4, 5):
            if kraj > red:
                t.cell(red, j).merge(t.cell(kraj, j))
        _upisi(t.cell(red, 0), tema.upper(), pismo, True, 9)
        _upisi(t.cell(red, 1), "\n".join(f"- {i};" for i in ishodi), pismo, velicina=9)
        _upisi(t.cell(red, 4), (f"{predmeti};\n\n" if predmeti else "") + f"Međupredmetne kompetencije: {mk}.",
               pismo, velicina=9)
        _upisi(t.cell(red, 5), "", pismo, velicina=9)
        red = kraj + 1
    _sirine(t, [3.2, 7.0, 7.0, 1.4, 4.4, 3.7])
    _par(doc, "Tip časa: O – obrada, U – utvrđivanje i uvežbavanje, P – proveravanje, S – sistematizacija i "
              "ponavljanje.", pismo, velicina=9)
    return _sacuvaj(doc)


KOLONE_OP = ["Č.", "Datum", "Tema", "Nastavna jedinica", "Tip časa", "Ishodi", "Metode", "Oblici rada",
             "Korelacija"]


def _red_op(c: Cas) -> list:
    return [c.redni_broj, c.datum.strftime("%d.%m."), c.tema, c.jedinica, c.tip, c.ishodi, c.metode,
            c.oblici_rada, c.korelacija]


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
