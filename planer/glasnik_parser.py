"""Deterministički parser Pravilnika o programu nastave i učenja (DOCX, npr. sa paragraf.rs).

Bez LLM-a čita: predmet → varijanta („za profile u četvorogodišnjem trajanju koji imaju 3 časa…“)
→ razred → nedeljni fond → ishodi i teme sa sadržajima → oriјentacioni broj časova po temama
i napomenu o inicijalnom testu i pismenim zadacima.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from .ekstrakcija import normalizuj
from .modeli import Program, Tema

RAZREDI = {"prvi": 1, "drugi": 2, "treci": 3, "cetvrti": 4, "peti": 5, "sesti": 6, "sedmi": 7, "osmi": 8,
           "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8}
BROJEVI = {"jedan": 1, "jednog": 1, "dva": 2, "tri": 3, "cetiri": 4, "pet": 5, "sest": 6}


@dataclass
class Blok:
    tekst: str = ""  # paragraf
    tabela: list[list[str]] | None = None  # redovi → ćelije (sa \n)


@dataclass
class Varijanta:
    predmet: str
    opis: str  # npr. "(за образовне профиле у четворогодишњем трајању који имају 3 часа недељно)"
    razred: int
    nedeljni_fond: float
    napomena_fonda: str = ""
    ishodi: list[str] = field(default_factory=list)
    teme: list[Tema] = field(default_factory=list)
    inicijalni: int = 0
    pismeni_broj: int = 0
    pismeni_trajanje: int = 1
    pismeni_casova: int = 0  # ukupno sa ispravkama
    fusnote: list[str] = field(default_factory=list)
    uputstvo: list[str] = field(default_factory=list)  # pasusi uputstva za ostvarivanje programa (ceo predmet)

    def uputstvo_za_razred(self) -> list[str]:
        """Pasusi uputstva koji se odnose na ovaj razred (između „Drugi razred“ i sledećeg naslova razreda)."""
        out, u_razredu = [], False
        for t in self.uputstvo:
            n = normalizuj(t).strip(" .")
            if len(t) < 30 and n.endswith("razred"):
                u_razredu = _razred(t) == self.razred
                continue
            if u_razredu:
                out.append(t)
        return out or self.uputstvo

    def naziv(self) -> str:
        return f"{self.predmet} {self.opis} — {self.razred}. razred, {self.nedeljni_fond:g} č. nedeljno"


# ---------------------------------------------------------------- čitanje fajla


def blokovi_iz_docx(sadrzaj: bytes) -> list[Blok]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(sadrzaj))
    out: list[Blok] = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = Paragraph(el, d).text.strip()
            if t:
                out.append(Blok(tekst=t))
        elif tag == "tbl":
            redovi = []
            for r in Table(el, d).rows:
                celije: list[str] = []
                for c in r.cells:  # spojene ćelije se ponavljaju → preskoči duplikate
                    tx = c.text.strip()
                    if not celije or celije[-1] != tx:
                        celije.append(tx)
                redovi.append(celije)
            out.append(Blok(tabela=redovi))
    return out


# ---------------------------------------------------------------- pomoćne


def _velika_slova(t: str) -> bool:
    slova = [c for c in t if c.isalpha()]
    return len(slova) >= 3 and all(c.isupper() for c in slova)


def _broj(t: str) -> int | None:
    n = normalizuj(t)
    if m := re.search(r"\d+", n):
        return int(m.group())
    for rec, v in BROJEVI.items():
        if re.search(rf"\b{rec}\b", n):
            return v
    return None


def _razred(t: str) -> int | None:
    n = normalizuj(t).strip(" .")
    for rec in re.split(r"[\s/]+", n):
        if rec in RAZREDI:
            return RAZREDI[rec]
    m = re.match(r"(\d)\.?\s*razred", n)
    return int(m.group(1)) if m else None


def _linije(celija: str) -> list[str]:
    return [l.strip() for l in celija.splitlines() if l.strip()]


def _teme_iz_celije(celija: str) -> list[Tema]:
    teme: list[Tema] = []
    for l in _linije(celija):
        if _velika_slova(l.rstrip("*").strip()):
            teme.append(Tema(redni_broj=len(teme) + 1, naziv=l.strip()))
        elif teme:
            teme[-1].sadrzaji.append(l)
    return teme


def _ishodi(celija: str) -> list[str]:
    out = []
    for l in _linije(celija):
        if normalizuj(l).startswith("po zavrsetku"):
            continue
        out.append(l.lstrip("–-• ").rstrip(";.").strip())
    return [o for o in out if o]


def _isti_naziv(a: str, b: str) -> bool:
    na, nb = (re.sub(r"[^a-z ]", "", normalizuj(x)).strip() for x in (a, b))
    return na == nb or na.startswith(nb) or nb.startswith(na)


# ---------------------------------------------------------------- glavni parser


def parsiraj_blokove(blokovi: list[Blok]) -> list[Varijanta]:
    varijante: list[Varijanta] = []
    predmet, opis = "", ""
    sekcija: list[Varijanta] = []  # varijante trenutnog predmeta (za oriјentacione časove)
    casovi_razred: int | None = None
    u_predlogu = False
    for i, b in enumerate(blokovi):
        if b.tabela is None:
            t = b.tekst
            n = normalizuj(t)
            sledeci = blokovi[i + 1].tekst if i + 1 < len(blokovi) and blokovi[i + 1].tabela is None else ""
            if "\n" in t:  # „НАЗИВ\n(за ... профиле ...)“ u jednom paragrafu
                prvi, ostatak = t.split("\n", 1)
                if _velika_slova(prvi) and ostatak.strip().startswith("("):
                    t, sledeci = prvi, ostatak.strip()
            if _velika_slova(t) and len(t) < 90 and not t.rstrip().endswith(":") and (
                    sledeci.startswith("(") or normalizuj(sledeci).startswith("cilj")):
                predmet, opis, sekcija, u_predlogu, casovi_razred = t.strip(), "", [], False, None
                if sledeci.startswith("("):
                    opis = sledeci.strip()
                continue
            if "orijentacion" in n and "broj" in n and "casova" in n:
                u_predlogu = True
                continue
            if u_predlogu:
                r = _razred(t) if len(t) < 30 and "razred" in n else None
                if r:
                    casovi_razred = r
                    for v in sekcija:
                        v.uputstvo.append(t)
                    continue
                m = re.match(r"^(.+?)\s*\((\d+)\)\s*$", t)
                if m and casovi_razred:
                    for v in sekcija:
                        if v.razred == casovi_razred:
                            for tm in v.teme:
                                if _isti_naziv(tm.naziv.rstrip("*"), m.group(1)):
                                    tm.casova_obrada = int(m.group(2))
                    continue
                if n.startswith("napomena") and casovi_razred:
                    for v in sekcija:
                        if v.razred == casovi_razred:
                            _napomena(v, t)
                    continue
            if t.startswith("*") and sekcija:
                for v in sekcija:
                    if t not in v.fusnote:
                        v.fusnote.append(t)
            for v in sekcija:
                v.uputstvo.append(t)
            continue
        # tabela
        tab = b.tabela
        if not tab or not tab[0] or not normalizuj(tab[0][0]).startswith("razred") or len(tab[0]) < 2:
            continue
        razred = _razred(tab[0][1])
        if not razred or not predmet:
            continue
        fond, napomena = 0.0, ""
        ishodi: list[str] = []
        teme: list[Tema] = []
        for red in tab[1:]:
            k = normalizuj(red[0]) if red else ""
            if k.startswith("nedeljni fond") and len(red) > 1:
                fond = float(_broj(red[1]) or 0)
                napomena = " ".join(_linije(red[1])[1:])
            elif k.startswith("ishodi") or k.startswith("godisnji fond"):
                continue
            elif len(red) >= 2:
                ishodi += _ishodi(red[0])
                teme += _teme_iz_celije(red[-1])
        for k, tm in enumerate(teme):
            tm.redni_broj = k + 1
        v = Varijanta(predmet=predmet, opis=opis, razred=razred, nedeljni_fond=fond,
                      napomena_fonda=napomena, ishodi=ishodi, teme=teme)
        varijante.append(v)
        sekcija.append(v)
    return varijante


def _napomena(v: Varijanta, t: str) -> None:
    n = normalizuj(t)
    if m := re.search(r"inicijaln\w*.*?(\d+)\s*cas", n):
        v.inicijalni = int(m.group(1))
    if m := re.search(r"(\d+|jedan|dva|tri|cetiri|pet|sest)\s+pismen\w*\s+zadat", n):
        v.pismeni_broj = _broj(m.group(1)) or 0
        if t2 := re.search(r"trajanju\s+od\s+po\s+(\w+)\s+cas", n):
            v.pismeni_trajanje = _broj(t2.group(1)) or 1
        if t3 := re.search(r"pismen.*?planirano\s+je\s+(\d+)\s+cas", n):
            v.pismeni_casova = int(t3.group(1))


# ---------------------------------------------------------------- izbor i pretvaranje u Program


def izaberi(varijante: list[Varijanta], predmet: str, razred: int, nedeljni_fond: float | None = None,
            trajanje: int | None = None) -> list[Varijanta]:
    p = normalizuj(predmet).strip()
    kand = [v for v in varijante if normalizuj(v.predmet).strip() == p and v.razred == razred] or \
           [v for v in varijante if p in normalizuj(v.predmet) and v.razred == razred]
    if nedeljni_fond:
        kand = [v for v in kand if v.nedeljni_fond == nedeljni_fond] or kand
    if trajanje and len(kand) > 1:
        kljuc = {3: "trogodisnj", 4: "cetvorogodisnj"}.get(trajanje)
        kand = [v for v in kand if kljuc and kljuc in normalizuj(v.opis)] or kand
    return kand


def _dodeli_ishode(teme: list[Tema], ishodi: list[str]) -> None:
    """Ishodi su u glasniku zajednički za razred → dodeli temi po preklapanju ključnih reči."""
    def koreni(t: str) -> set[str]:
        return {w[:5] for w in re.findall(r"[a-z]{5,}", normalizuj(t))}
    ishodi = list(dict.fromkeys(ishodi))
    opste = {"resi", "resav", "koris", "izrac", "prime", "probl", "jedno", "osnov", "odred", "predst",
             "skicir", "analiz", "obraz", "matem", "zadat", "pomoc", "potre"}
    for tm in teme:
        k = koreni(tm.naziv + " " + " ".join(tm.sadrzaji)) - opste
        ocene = [(len((koreni(i) - opste) & k), i) for i in ishodi]
        tm.ishodi = [i for o, i in ocene if o >= 2] or [i for o, i in ocene if o >= 1]


def u_program(v: Varijanta, smer: str | None = None, izvor: str = "", tip_skole: str | None = None) -> Program:
    """Pretvori varijantu u Program. Stavke sa * (npr. samo za Elektrotehniku) se izbacuju
    ako smer ne odgovara fusnoti."""
    zvezdica_vazi = False
    if smer and v.fusnote:
        f = normalizuj(" ".join(v.fusnote))
        zvezdica_vazi = any(r[:8] in normalizuj(smer) for r in re.findall(r"[a-z]{6,}", f)
                            if r not in {"obrazovne", "profile", "podrucju"})
    teme = []
    for tm in v.teme:
        t = tm.model_copy(deep=True)
        if not zvezdica_vazi:
            t.sadrzaji = [s for s in t.sadrzaji if not s.rstrip().endswith("*")]
        t.naziv = t.naziv.rstrip("*").strip()
        if _velika_slova(t.naziv):
            t.naziv = t.naziv[:1] + t.naziv[1:].lower()
        teme.append(t)
    ishodi = list(dict.fromkeys(i for i in v.ishodi if zvezdica_vazi or not i.endswith("*")))
    _dodeli_ishode(teme, [i.rstrip("*") for i in ishodi])
    if tip_skole is None:
        tip_skole = "srednja" if re.search(r"profil|srednj|gimnazij", normalizuj(izvor + v.opis)) else "osnovna"
    return Program(predmet=v.predmet[:1] + v.predmet[1:].lower(), razred=v.razred, tip_skole=tip_skole,
                   smer=smer, nedeljni_fond=v.nedeljni_fond, izvor=izvor, teme=teme,
                   inicijalni_casova=v.inicijalni, pismeni_broj=v.pismeni_broj,
                   pismeni_trajanje=v.pismeni_trajanje,
                   pismeni_ispravka=v.pismeni_casova > v.pismeni_broj * v.pismeni_trajanje,
                   uputstvo=v.uputstvo_za_razred(),
                   fond_glasnika=sum(t.casova_obrada for t in teme) + v.inicijalni + (
                       v.pismeni_casova or v.pismeni_broj * v.pismeni_trajanje))


def naslov_izvora(blokovi: list[Blok]) -> str:
    for b in blokovi[:5]:
        tekst = b.tekst or (" ".join(" ".join(r) for r in b.tabela) if b.tabela else "")
        if m := re.search(r"\(\s*[\"“„]?\s*(С[лл]\.|Sl\.)[^)]*\)", tekst):
            return m.group(0).strip("() ")
    return ""
