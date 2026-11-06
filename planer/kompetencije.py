"""Međupredmetne kompetencije i predmeti za povezivanje — iz glasnika i logičkim zaključivanjem.

Za svaku temu agent:
1. traži u uputstvu glasnika pasuse koji se odnose na temu i u njima pominjanja drugih predmeta
   i aktivnosti (izvor: „glasnik“, uz citat);
2. dopunjuje logičkim pravilima — šta se u temi radi i gde se to primenjuje (izvor: „logika“, uz razlog);
3. zadržava samo predmete koje učenici tog razreda zaista imaju (iz glasnika ili od nastavnika);
4. sve to pokazuje nastavniku sa obrazloženjem, a nastavnik potvrđuje ili ispravlja.
"""
from __future__ import annotations

import re

from .ekstrakcija import normalizuj
from .modeli import Program, Tema

# Zakon o osnovama sistema obrazovanja i vaspitanja, čl. 12 — međupredmetne kompetencije
MK_SVE = [
    "kompetencija za učenje", "komunikacija", "rad sa podacima i informacijama", "digitalna kompetencija",
    "rešavanje problema", "saradnja", "odgovorno učešće u demokratskom društvu",
    "odgovoran odnos prema zdravlju", "odgovoran odnos prema okolini", "estetička kompetencija",
    "preduzimljivost i preduzetnička kompetencija",
]

# (korenovi reči u temi/sadržaju/ishodima/uputstvu) → kompetencija, razlog
MK_PRAVILA = [
    (r"resi|resav|problem|zadat|primen|model", "rešavanje problema", "tema traži rešavanje zadataka i primenu"),
    (r"graf|tabel|podat|statist|dijagram|procen|verovatn|grafik", "rad sa podacima i informacijama",
     "čitanje i tumačenje grafika, tabela i podataka"),
    (r"kalkulator|softver|racunar|digital|geogebr|aplikac|program", "digitalna kompetencija",
     "upotreba kalkulatora/softvera"),
    (r"obrazlo|diskut|matematick\w* jezik|argument|prezent|dokaz|tumac", "komunikacija",
     "obrazlaganje postupka i korišćenje stručnog jezika"),
    (r"saradn|grupn|grupi|u paru|timsk|vrsnjac", "saradnja", "rad u paru i grupi"),
    (r"kamat|kredit|finans|trosk|ekonom|preduz|ulag", "preduzimljivost i preduzetnička kompetencija",
     "finansijski i ekonomski primeri"),
    (r"zdrav|ishran|bolest|lek", "odgovoran odnos prema zdravlju", "primeri iz zdravlja"),
    (r"okolin|ekolo|zagadj|energij|klima|otpad", "odgovoran odnos prema okolini", "primeri iz životne sredine"),
    (r"simetr|umetn|estet|ornament|kompozic", "estetička kompetencija", "estetski aspekti oblika"),
    (r"drustv|demokrat|gradjan|prava\b|izbor", "odgovorno učešće u demokratskom društvu", "društveni primeri"),
]

# pominjanje predmeta u tekstu glasnika (padežni oblici) → naziv predmeta
PREDMETI_U_TEKSTU = {
    r"fizi[kcč]": "Fizika", r"hemij": "Hemija", r"biolog": "Biologija", r"geograf": "Geografija",
    r"istorij": "Istorija", r"informatik|racunarstv": "Računarstvo i informatika", r"ekonomij": "Ekonomija",
    r"likovn": "Likovna kultura", r"muzick": "Muzička kultura", r"srpsk\w* jezik": "Srpski jezik i književnost",
    r"engleskog|stranog jezik|strani jezik": "Strani jezik", r"fizick\w* vaspitanj": "Fizičko vaspitanje",
    r"matemat": "Matematika",
}

# logička pravila: (korenovi u temi) → [(predmet ili oblast stručnog predmeta, razlog)]
# „@saobracaj“ znači: stručni predmet čiji naziv sadrži taj koren (ako ga nastavnik navede)
KORELACIJA_PRAVILA = [
    (r"trigonometr|ugao|radijan|sinus|kosinus", [
        ("Fizika", "razlaganje sila, kretanje po kružnici, oscilacije i talasi"),
        ("@saobra|put|vozil|tehnik|mehan|geodez", "nagib puta, poluprečnik krivine, uglovi preglednosti"),
    ]),
    (r"kvadratn", [
        ("Fizika", "ravnomerno ubrzano kretanje: s = v₀t + at²/2"),
        ("@saobra|vozil|bezbed|kretanj", "zaustavni put vozila raste sa kvadratom brzine"),
    ]),
    (r"eksponencijal|logaritam", [
        ("Hemija", "pH vrednost (logaritam koncentracije)"),
        ("Biologija", "rast populacije i razmnožavanje bakterija"),
        ("Fizika", "radioaktivni raspad, intenzitet zvuka u decibelima"),
        ("Ekonomija", "složeni kamatni račun"),
        ("@ekonom|poslov|finans", "složeni kamatni račun"),
    ]),
    (r"stepen|korenovanj|pojam koren|operacij\w* sa koren|naucn\w* zapis", [
        ("Fizika", "naučni zapis i mernе jedinice (10ⁿ)"),
        ("Hemija", "Avogadrov broj, naučni zapis"),
    ]),
    (r"kompleksn", [("Fizika", "naizmenične struje i oscilacije"),
                    ("@elektro", "naizmenične struje")]),
    (r"funkcij|grafik|graf\b", [
        ("Računarstvo i informatika", "crtanje grafika funkcija u softveru (GeoGebra, tabele)"),
        ("Fizika", "grafici zavisnosti fizičkih veličina"),
    ]),
    (r"proporc|razmer|procent", [("Hemija", "rastvori i smeše"), ("Geografija", "razmer geografske karte"),
                                 ("@ekonom|poslov|saobra", "procenti, cene i troškovi")]),
    (r"vektor", [("Fizika", "sile, brzine i ubrzanja kao vektori")]),
    (r"verovatn|statist|kombinator", [("Biologija", "genetika i nasleđivanje"),
                                      ("Računarstvo i informatika", "obrada podataka")]),
    (r"geometr|povrsin|zapremin|telo|poliedar", [("Likovna kultura", "oblici i prostor"),
                                                 ("@tehnik|crt|konstrukc|grad", "tehničko crtanje i proračuni")]),
]


def _rx(koreni: str) -> re.Pattern:
    """Svaki koren mora biti početak reči („tim“ ne sme da se nađe u „zatim“)."""
    return re.compile(r"\b(?:" + koreni + ")")


def _koreni(t: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{5,}", normalizuj(t))}


def relevantni_pasusi(tema: Tema, uputstvo: list[str], koliko: int = 3) -> list[str]:
    """Pasusi uputstva o ovoj temi: moraju da pominju bar jednu reč iz naziva teme."""
    opste = {"funkc", "jedna", "osnov", "nejed"}  # reči zajedničke mnogim temama
    kn = _koreni(tema.naziv) - opste
    ks = _koreni(" ".join(tema.sadrzaji))
    ocene = []
    for i, p in enumerate(uputstvo):
        kp = _koreni(p)
        naziv = len(kp & kn)
        if naziv:
            ocene.append((2 * naziv + len(kp & ks), i, p))
    ocene.sort(key=lambda x: (-x[0], x[1]))
    return [p for o, _, p in ocene[:koliko] if o >= 3]


def _citat(pasus: str, kljuc, duzina: int = 120) -> str:
    n = normalizuj(pasus)
    m = (kljuc if isinstance(kljuc, re.Pattern) else _rx(kljuc)).search(n)
    if not m:
        return pasus[:duzina]
    # normalizacija čuva dužinu za latinicu/ćirilicu osim digrafa — dovoljno približno za citat
    pocetak = max(0, m.start() - duzina // 2)
    return ("…" if pocetak else "") + pasus[pocetak:pocetak + duzina].strip() + "…"


def _postoji(predmet: str, dostupni: list[str] | None) -> bool:
    if dostupni is None:
        return True
    n = normalizuj(predmet)
    return any(normalizuj(d).startswith(n[:6]) or n.startswith(normalizuj(d)[:6]) for d in dostupni)


def analiziraj_temu(tema: Tema, program: Program, dostupni_predmeti: list[str] | None = None,
                    strucni_predmeti: list[str] | None = None) -> Tema:
    """Vrati temu sa popunjenim kompetencijama, korelacijom i obrazloženjem."""
    pasusi = relevantni_pasusi(tema, program.uputstvo)
    tekst_teme = normalizuj(" ".join([tema.naziv] + tema.sadrzaji))
    tekst_ishoda = normalizuj(" ".join(tema.ishodi))
    tekst_uput = normalizuj(" ".join(pasusi))
    obr: list[str] = []

    mk = ["kompetencija za učenje"]
    for kljuc, komp, razlog in MK_PRAVILA:
        rx = _rx(kljuc)
        if komp in mk:
            continue
        if rx.search(tekst_uput):
            mk.append(komp)
            pasus = next(p for p in pasusi if rx.search(normalizuj(p)))
            obr.append(f"MK „{komp}“ — glasnik: {_citat(pasus, rx)}")
        elif rx.search(tekst_teme):
            mk.append(komp)
            obr.append(f"MK „{komp}“ — logika: {razlog}")
        elif rx.search(tekst_ishoda):
            mk.append(komp)
            ishod = next(i for i in tema.ishodi if rx.search(normalizuj(i)))
            obr.append(f"MK „{komp}“ — ishod iz glasnika: {ishod}")
    if tema.casova_utvrdjivanje and "saradnja" not in mk:
        mk.append("saradnja")
        obr.append("MK „saradnja“ — logika: rad u paru/grupi na časovima utvrđivanja")

    korel: list[str] = []
    sopstveni = normalizuj(program.predmet)
    for kljuc, predmet in PREDMETI_U_TEKSTU.items():
        for p in pasusi:
            if _rx(kljuc).search(normalizuj(p)) and not normalizuj(predmet).startswith(sopstveni[:6]):
                if predmet not in korel and _postoji(predmet, dostupni_predmeti):
                    korel.append(predmet)
                    obr.append(f"{predmet} — glasnik: {_citat(p, kljuc)}")
                break
    for kljuc, predlozi in KORELACIJA_PRAVILA:
        if not _rx(kljuc).search(tekst_teme):
            continue
        for predmet, razlog in predlozi:
            if predmet.startswith("@"):
                for sp in strucni_predmeti or []:
                    if _rx(predmet[1:]).search(normalizuj(sp)) and sp not in korel:
                        korel.append(sp)
                        obr.append(f"{sp} — logika: {razlog}")
            elif predmet not in korel and _postoji(predmet, dostupni_predmeti) and \
                    not normalizuj(predmet).startswith(sopstveni[:6]):
                korel.append(predmet)
                obr.append(f"{predmet} — logika: {razlog}")
    return tema.model_copy(update={"kompetencije": mk, "korelacija": korel[:4], "obrazlozenje": obr})


def analiziraj_program(program: Program, dostupni_predmeti: list[str] | None = None,
                       strucni_predmeti: list[str] | None = None) -> Program:
    p = program.model_copy(deep=True)
    p.teme = [analiziraj_temu(t, p, dostupni_predmeti, strucni_predmeti) for t in p.teme]
    return p


def predmeti_razreda(varijante: list, razred: int) -> list[str]:
    """Predmeti koji u ovom glasniku postoje za dati razred (samo kao pomoć — spisak nije potpun,
    jer se neki predmeti nalaze u drugim pravilnicima; filtrira se samo po spisku nastavnika)."""
    imena = []
    for v in varijante:
        if v.razred == razred:
            ime = v.predmet[:1] + v.predmet[1:].lower()
            if ime not in imena:
                imena.append(ime)
    return imena
