"""Pronalaženje i provera službenog glasnika za predmet, razred i smer.

Postupak (bez nagađanja):
1. **ZUOV katalog** (https://zuov.gov.rs/zakoni-i-pravilnici/) — zvaničan spisak važećih pravilnika po
   nivou obrazovanja i području rada, sa oznakama glasnika (npr. „8/2018-1, … 7/2023-3 (др. правилник)“)
   i linkovima ka Pravno-informacionom sistemu (PIS).
2. Iz kataloga se biraju pravilnici o planu i programu koji odgovaraju školi, razredu, smeru i predmetu,
   i nude nastavniku da izabere.
3. Za izabrani pravilnik agent prolazi kroz njegove glasnike (od najnovijeg), preuzima tekst sa
   Paragrafove javne demo baze i **proverava** da u njemu zaista postoji program za traženi predmet,
   razred i nedeljni fond. Tek takav glasnik se koristi za plan.
4. Ako tekst ne može da se preuzme, nastavnik dobija tačan naziv, broj glasnika i link ka PIS-u.
"""
from __future__ import annotations

import io
import re
import tempfile
import time
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path

import requests

from .ekstrakcija import normalizuj

UA = {"User-Agent": "napravi-plan/0.4 (planovi rada nastavnika)"}
ZUOV_AJAX = "https://zuov.gov.rs/wp-admin/admin-ajax.php"
KATEGORIJA = {"osnovna": 2192, "srednja": 2193}
PARAGRAF_DEMO = "http://demo.paragraf.rs/demo/combined/Old/t/t{godina}_{mesec:02d}/{pg}.htm"
KES = Path(tempfile.gettempdir()) / "napravi-plan-kes"

# opšteobrazovni predmeti u srednjim školama (za izbor „opšteobrazovni“ ili „stručni“ pravilnik)
OPSTEOBRAZOVNI = ["srpski", "maternji", "strani jezik", "engleski", "nemacki", "ruski", "francuski", "matemat",
                  "fizik", "hemij", "biolog", "geograf", "istorij", "racunarstv", "informatik", "fizicko",
                  "likovn", "muzick", "umetnost", "sociolog", "filozof", "ustav", "gradjansk", "versk", "logik",
                  "psiholog", "ekologij"]

# ključne reči smera → naziv područja rada u ZUOV katalogu
PODRUCJA = {
    "saobracaj": ["saobracaj", "drumsk", "vozac", "zeleznic", "vazduhoplov", "nautick", "logisti", "ptt",
                  "spedit", "brodo"],
    "elektrotehnika": ["elektro", "racunar", "informat", "energet", "telekomunik", "mehatron", "automatik"],
    "masinstvo": ["masin", "metal", "bravar", "zavariv", "automehan", "autoelektr", "instalater", "tokar"],
    "ekonomija": ["ekonom", "pravn", "administr", "finansij", "bankar", "osigur", "poslovn", "knjigovo"],
    "geodezija": ["geodet", "gradjevin", "arhitekt", "keramicar", "zidar", "tesar", "moler"],
    "poljoprivreda": ["poljopriv", "veterin", "prehramb", "pekar", "mesar", "mlekar", "agro", "horti",
                      "cvecar", "ratar", "vocar"],
    "prirodno-matematicka": ["laborant", "prirodno-matemat", "hemijsk"],
    "tekstilstvo": ["tekstil", "kozar", "kozn", "modni", "kroja", "obucar", "konfekc"],
    "licne usluge": ["frizer", "kozmet", "pediker", "manikir"],
}

RAZREDI_RECI = {1: ["prvi", "prvog"], 2: ["drugi", "drugog"], 3: ["treci", "treceg"], 4: ["cetvrti", "cetvrtog"],
                5: ["peti", "petog"], 6: ["sesti", "sestog"], 7: ["sedmi", "sedmog"], 8: ["osmi", "osmog"]}


# ---------------------------------------------------------------- modeli

@dataclass(frozen=True)
class Referenca:
    broj: int
    godina: int
    strana: int
    napomena: str = ""  # „др. правилник“, „исправка“ …

    @property
    def oznaka(self) -> str:
        return f"{self.broj}/{self.godina}-{self.strana}"

    @property
    def pg_id(self) -> str:
        return f"PG_{self.broj:03d}_{self.godina}_{self.strana:03d}"


@dataclass
class Pravilnik:
    rb: int
    naziv: str
    reference: list[Referenca]
    pis_url: str | None = None
    katalog: str = ""
    napomena: str = ""

    @property
    def glasnici(self) -> str:
        return ", ".join(r.oznaka + (f" ({r.napomena})" if r.napomena else "") for r in self.reference)


@dataclass
class Predlog:
    pravilnik: Pravilnik
    ocena: float
    razlog: str


@dataclass
class Provera:
    status: str  # "provereno" | "nema_programa" | "nedostupno"
    poruka: str
    referenca: Referenca | None = None
    izvor_url: str | None = None
    varijante: list = field(default_factory=list)  # glasnik_parser.Varijanta (svi programi iz glasnika)
    naslov: str = ""


Preuzimac = Callable[[str], tuple[int, bytes]]


# ---------------------------------------------------------------- mreža (sa kešom)

def preuzmi(url: str, timeout: int = 30, kes: bool = True) -> tuple[int, bytes]:
    putanja = KES / sha1(url.encode()).hexdigest()
    if kes and putanja.exists():
        return 200, putanja.read_bytes()
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
    except requests.RequestException:
        return 0, b""
    if r.status_code == 200 and kes:
        KES.mkdir(parents=True, exist_ok=True)
        putanja.write_bytes(r.content)
    return r.status_code, r.content


# ---------------------------------------------------------------- ZUOV katalog

def spisak_kataloga(tip_skole: str, preuzimac: Preuzimac = preuzmi) -> list[tuple[str, str]]:
    """[(naziv, url_pdf)] za nivo obrazovanja (osnovna / srednja) sa ZUOV sajta."""
    import json

    kat = KATEGORIJA["osnovna" if tip_skole == "osnovna" else "srednja"]
    url = (f"{ZUOV_AJAX}?juwpfisadmin=false&action=wpfd&task=files.display&view=files&id={kat}&rootcat=2190")
    status, sadrzaj = preuzimac(url)
    if status != 200:
        return []
    try:
        fajlovi = json.loads(sadrzaj.decode("utf-8", errors="ignore")).get("files", [])
    except ValueError:
        return []
    return [(f.get("post_title", ""), f.get("linkdownload", "")) for f in fajlovi if f.get("linkdownload")]


_REF = re.compile(r"(\d{1,2})/(\d{4})-\s*(\d+)(?:\s*\(([^)]*)\))?")
_POCETAK = re.compile(r"^(\d{1,3})\s+(Правилник.*)$")
_NAPOMENA = re.compile(r"^Правилник (је|формалноправно)")


def ucitaj_katalog(pdf: bytes, naziv_kataloga: str = "") -> list[Pravilnik]:
    """ZUOV PDF katalog („2.8 Саобраћај“) → lista pravilnika sa glasnicima i PIS linkovima."""
    from pypdf import PdfReader

    citac = PdfReader(io.BytesIO(pdf))
    linije, linkovi = [], []
    for strana in citac.pages:
        linije += (strana.extract_text() or "").splitlines()
        for a in strana.get("/Annots") or []:
            a = a.get_object()
            akcija = a.get("/A")
            if akcija and akcija.get("/URI"):
                linkovi.append(str(akcija["/URI"]))
    return pravilnici_iz_linija(linije, linkovi, naziv_kataloga)


def pravilnici_iz_linija(linije: list[str], linkovi: list[str], naziv_kataloga: str = "") -> list[Pravilnik]:
    """Redovi teksta ZUOV kataloga → pravilnici (redni broj, naziv, glasnici, napomene, PIS link)."""
    stavke: list[list] = []  # [rb, delovi naziva/oznaka, napomene]
    for l in linije:
        l = l.strip()
        if m := _POCETAK.match(l):
            stavke.append([int(m.group(1)), [m.group(2)], []])
        elif stavke and _NAPOMENA.match(l) or stavke and stavke[-1][2]:
            stavke[-1][2].append(l)
        elif stavke:
            stavke[-1][1].append(l)
    pravilnici = []
    for i, (rb, delovi, napomene) in enumerate(stavke):
        tekst = ""
        for d in delovi:  # spoji prelomljene redove („2/2022-“ + „333“)
            tekst += d if tekst.endswith(("-", "(")) else (" " + d if tekst else d)
        naziv, _, oznake = tekst.partition(" : ")
        reference = [Referenca(int(a), int(b), int(c), (n or "").strip()) for a, b, c, n in _REF.findall(oznake)]
        pis = linkovi[i] if len(linkovi) == len(stavke) else None
        pravilnici.append(Pravilnik(rb, re.sub(r"\s+", " ", naziv).strip(), reference, pis, naziv_kataloga,
                                    " ".join(napomene)))
    return pravilnici


def izaberi_katalog(katalozi: list[tuple[str, str]], tip_skole: str, smer: str | None,
                    llm=None) -> tuple[str, str] | None:
    if not katalozi:
        return None
    nazivi = [(normalizuj(n), n, u) for n, u in katalozi]
    if tip_skole == "osnovna":
        return next(((n, u) for k, n, u in nazivi if "osnovno" in k), None)
    s = normalizuj(smer or "")
    if "gimnazij" in s:
        return next(((n, u) for k, n, u in nazivi if "gimnazij" in k), None)
    najbolji, ocena = None, 0
    for podrucje, reci in PODRUCJA.items():
        pogodaka = sum(1 for r in reci if r in s)
        if pogodaka > ocena:
            kand = next(((n, u) for k, n, u in nazivi if podrucje.split()[0][:6] in k), None)
            if kand:
                najbolji, ocena = kand, pogodaka
    if najbolji or not llm:
        return najbolji
    try:  # nepoznat smer → neka model izabere područje rada sa spiska
        odg = llm.chat_json('Vrati JSON {"rb": <redni broj područja rada sa spiska ili null>}.',
                            f"Obrazovni profil: {smer}\nPodručja rada:\n" +
                            "\n".join(f"{i + 1}. {n}" for i, (n, _) in enumerate(katalozi)), max_tokena=300)
        rb = int(odg.get("rb") or 0)
        return katalozi[rb - 1] if 1 <= rb <= len(katalozi) else None
    except (ValueError, TypeError, AttributeError, Exception):  # noqa: BLE001 — model je samo pomoć
        return None


# ---------------------------------------------------------------- predlozi

def je_opsteobrazovni(predmet: str) -> bool:
    p = normalizuj(predmet)
    return any(k in p for k in OPSTEOBRAZOVNI)


def predlozi(pravilnici: list[Pravilnik], predmet: str, razred: int, tip_skole: str,
             smer: str | None = None, koliko: int = 4) -> list[Predlog]:
    """Rangira pravilnike iz kataloga za dati predmet/razred/smer, sa obrazloženjem."""
    s = normalizuj(smer or "")
    out = []
    for p in pravilnici:
        n = normalizuj(p.naziv)
        if "program" not in n or not p.reference:
            continue
        if re.search(r"blizim uslovima|stepenu i vrsti|zavrsnog ispita|osposobljavanja|matursk|neposredne ratne",
                     n):
            continue
        ocena, razlozi = 0.0, []
        if "nastave i ucenja" in n:
            ocena += 3
            razlozi.append("važeći tip programa („nastave i učenja“)")
        else:
            ocena -= 2
            razlozi.append("stariji „nastavni plan i program“")
        if re.search(r"izmen|dopun", n) and not n.startswith("pravilnik o planu"):
            ocena -= 3
        posebno = re.search(r"baletsk|muzick\w* obraz|obdaren|posebnim sposobnost|francusk|dvojezic|katolick|"
                            r"ogleda|versk|gradjansk", n)
        if posebno and posebno.group(0)[:6] not in s and posebno.group(0)[:6] not in normalizuj(predmet):
            ocena -= 6
        if tip_skole == "osnovna":
            reci = RAZREDI_RECI.get(razred, [])
            if any(re.search(rf"\b{r}\b", n) for r in reci):
                ocena += 5
                razlozi.append(f"za {razred}. razred")
            elif "prvi ciklus" in n and razred <= 4 or "drugi ciklus" in n and razred >= 5:
                ocena += 3
                razlozi.append("za ciklus kome pripada razred")
            elif re.search(r"\b(prvi|drugi|treci|cetvrti|peti|sesti|sedmi|osmi)\b", n):
                ocena -= 5
        elif "gimnazij" in n:
            ocena += 3 if "gimnazij" in s else -4
        else:
            if je_opsteobrazovni(predmet):
                if "opsteobrazovn" in n:
                    ocena += 4
                    razlozi.append("opšteobrazovni predmeti u stručnoj školi")
                elif "strucnih predmeta" in n:
                    ocena -= 3
            elif "strucnih predmeta" in n:
                ocena += 4
                razlozi.append("stručni predmeti područja rada")
        ocena += (max(r.godina for r in p.reference) - 2000) / 100  # noviji malo napred
        out.append(Predlog(p, ocena, "; ".join(razlozi)))
    out.sort(key=lambda x: -x.ocena)
    return [x for x in out if x.ocena > 0][:koliko] or out[:koliko]


# ---------------------------------------------------------------- preuzimanje teksta i provera

def nadji_na_paragrafu(ref: Referenca, preuzimac: Preuzimac = preuzmi) -> tuple[str, bytes] | None:
    """Paragrafova javna demo baza čuva glasnike po mesecu objave — probaj mesece te i sledeće godine."""
    kandidati = [PARAGRAF_DEMO.format(godina=g, mesec=m, pg=ref.pg_id)
                 for g in (ref.godina, ref.godina + 1) for m in range(1, 13)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        buduci = {ex.submit(preuzimac, u): u for u in kandidati}
        for b in as_completed(buduci):
            status, sadrzaj = b.result()
            if status == 200 and sadrzaj:
                for ostali in buduci:
                    ostali.cancel()
                return buduci[b], sadrzaj
    return None


def html_u_tekst(sadrzaj: bytes) -> str:
    try:
        return sadrzaj.decode("utf-8")
    except UnicodeDecodeError:
        return sadrzaj.decode("windows-1250", errors="replace")


def prilozi_iz_html(html: str) -> list[str]:
    """Linkovi ka prilozima (sam program je obično u prilogu, kao DOCX ili PDF)."""
    linkovi = re.findall(r'href="([^"]+)"', html)
    return [l for l in linkovi if re.search(r"/dokumenti/|\.(?:pdf|docx?)$", l, re.I)]


def nedostupni_tekst() -> str:
    return "Tekst nije javno dostupan za automatsko preuzimanje."


def naslov_iz_html(html: str) -> str:
    import html as _html

    tekst = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).strip()
    m = re.search(r"(PRAVILNIK|ПРАВИЛНИК).{0,300}?\)", tekst)
    return m.group(0) if m else tekst[:200]


def proveri_pravilnik(p: Pravilnik, predmet: str, razred: int, fond: float | None = None,
                      trajanje: int | None = None, preuzimac: Preuzimac = preuzmi,
                      najvise: int = 6, rok: float = 120) -> Provera:
    """Prođi kroz glasnike pravilnika (od najnovijeg) i nađi onaj koji sadrži program predmeta."""
    from .glasnik_parser import blokovi_iz_docx, blokovi_iz_html, izaberi, naslov_izvora, parsiraj_blokove

    def nadjen(blokovi) -> list:
        varijante = parsiraj_blokove(blokovi)
        return varijante if izaberi(varijante, predmet, razred, fond, trajanje) else []

    # od najnovijeg (Paragraf tamo čuva prečišćen tekst sa svim izmenama) + osnovni tekst na kraju
    sve = sorted((r for r in p.reference if "ispravk" not in normalizuj(r.napomena)),
                 key=lambda r: (r.godina, r.broj, r.strana), reverse=True)
    reference = sve[:najvise - 1] + ([sve[-1]] if len(sve) >= najvise else [])
    kraj = time.monotonic() + rok
    dostupno, probani = [], set()
    for ref in reference:
        if time.monotonic() > kraj:
            break
        nadjeno = nadji_na_paragrafu(ref, preuzimac)
        if not nadjeno:
            continue
        url, sadrzaj = nadjeno
        html = html_u_tekst(sadrzaj)
        dostupno.append(ref.oznaka)
        if "<table" in html and _pominje(html, predmet, razred) and (varijante := nadjen(blokovi_iz_html(html))):
            return Provera("provereno", _poruka_ok(ref, predmet, razred, fond), ref, url, varijante,
                           naslov_iz_html(html))  # program je u samom (prečišćenom) tekstu
        for prilog in prilozi_iz_html(html):
            if prilog in probani or time.monotonic() > kraj:
                continue
            probani.add(prilog)
            status, fajl = preuzimac(prilog)
            if status != 200 or not fajl.startswith(b"PK"):  # DOCX (i kad se zove .pdf); pravi PDF čita AI
                continue
            if not _pominje(_tekst_docx(fajl), predmet, razred):  # brza provera pre punog čitanja
                continue
            try:
                blokovi = blokovi_iz_docx(fajl)
            except Exception:  # noqa: BLE001 — oštećen ili neočekivan fajl
                continue
            if varijante := nadjen(blokovi):
                return Provera("provereno", _poruka_ok(ref, predmet, razred, fond), ref, prilog, varijante,
                               naslov_izvora(blokovi) or naslov_iz_html(html))
    if dostupno:
        return Provera("nema_programa", f"Preuzeo sam glasnike {', '.join(dostupno)}, ali nijedan ne sadrži program "
                       f"za {predmet}, {razred}. razred (ovaj pravilnik je verovatno samo plan ili izmene).")
    return Provera("nedostupno", "Tekst ovog pravilnika nije javno dostupan za automatsko preuzimanje."
                   + (f" Zvanični registar: {p.pis_url}" if p.pis_url else ""))


def _tekst_docx(fajl: bytes) -> str:
    try:
        return zipfile.ZipFile(io.BytesIO(fajl)).read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError):
        return ""


def _pominje(tekst: str, predmet: str, razred: int) -> bool:
    """Da li tekst uopšte pominje predmet i razred (pre skupog punog čitanja)."""
    n = normalizuj(re.sub(r"<[^>]+>", " ", tekst))
    reci = RAZREDI_RECI.get(razred, [])
    return normalizuj(predmet) in n and (not reci or any(r in n for r in reci))


def _poruka_ok(ref: Referenca, predmet: str, razred: int, fond: float | None) -> str:
    return (f"Glasnik {ref.oznaka} sadrži program: {predmet}, {razred}. razred"
            + (f", {fond:g} časa nedeljno" if fond else "") + ".")


# ---------------------------------------------------------------- sve zajedno

def pronadji_predloge(tip_skole: str, razred: int, predmet: str, smer: str | None = None, llm=None,
                      preuzimac: Preuzimac = preuzmi) -> tuple[list[Predlog], str]:
    """Vrati (predlozi, opis izvora). Prazna lista + poruka ako katalog nije dostupan."""
    katalozi = spisak_kataloga(tip_skole, preuzimac)
    if not katalozi:
        return [], "ZUOV katalog trenutno nije dostupan (proverite internet vezu)."
    izbor = izaberi_katalog(katalozi, tip_skole, smer, llm)
    if not izbor:
        return [], ("Nisam prepoznao područje rada za smer „" + (smer or "") + "“. Dostupni katalozi: "
                    + ", ".join(n for n, _ in katalozi) + ".")
    naziv, url = izbor
    status, pdf = preuzimac(url)
    if status != 200:
        return [], f"Ne mogu da preuzmem ZUOV katalog „{naziv}“."
    pravilnici = ucitaj_katalog(pdf, naziv)
    return predlozi(pravilnici, predmet, razred, tip_skole, smer), f"ZUOV katalog „{naziv}“ ({len(pravilnici)} propisa)"


def pretraga_interneta(llm, upit: str) -> str:
    """Pomoćna pretraga (Groq `browser_search`), samo kad katalog ne pomogne. Rezultat se NE koristi bez provere."""
    if not llm or getattr(llm, "provider", "") != "groq":
        return ""
    try:
        r = requests.post(f"{llm.url}/chat/completions", headers={"Authorization": f"Bearer {llm.kljuc}"},
                          json={"model": llm.model, "tools": [{"type": "browser_search"}], "reasoning_effort": "low",
                                "messages": [{"role": "user", "content": upit}]}, timeout=90)
        return r.json()["choices"][0]["message"].get("content") or "" if r.ok else ""
    except (requests.RequestException, ValueError, KeyError):
        return ""
