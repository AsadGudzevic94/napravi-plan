"""Raspodela tema po časovima i mesecima — čista matematika, bez LLM-a."""
from __future__ import annotations

import math
from collections import OrderedDict
from datetime import date
from typing import Literal

from .modeli import MESECI, Cas, NastavnaJedinica, Program, Tema

Strategija = Literal["proporcionalno", "rezerva", "bez_izmena"]


def _najveci_ostatak(tezine: list[float], ukupno: int, minimum: int = 0) -> list[int]:
    """Podeli `ukupno` celih jedinica proporcionalno težinama (metoda najvećeg ostatka)."""
    n = len(tezine)
    if n == 0:
        return []
    baza = [minimum] * n
    ostaje = ukupno - minimum * n
    if ostaje < 0:
        raise ValueError("Premalo časova za minimum po temi.")
    if sum(tezine) <= 0:
        tezine = [1.0] * n
    zbir = sum(tezine)
    tacno = [ostaje * t / zbir for t in tezine]
    celi = [math.floor(x) for x in tacno]
    visak = ostaje - sum(celi)
    redosled = sorted(range(n), key=lambda i: tacno[i] - celi[i], reverse=True)
    for i in redosled[:visak]:
        celi[i] += 1
    return [b + c for b, c in zip(baza, celi)]


def _podeli_temu(t: Tema, novo_ukupno: int) -> Tema:
    """Promeni ukupan broj časova teme, čuvajući odnos obrada/utvrđivanje/ostalo."""
    delovi = [t.casova_obrada, t.casova_utvrdjivanje, t.casova_ostalo]
    if sum(delovi) == 0:
        delovi = [1, 0, 0]
    o, u, r = _najveci_ostatak([float(x) for x in delovi], novo_ukupno)
    if o == 0 and novo_ukupno > 0:  # svaka tema mora imati bar jednu obradu
        if u > 0:
            u -= 1
        else:
            r -= 1
        o = 1
    return t.model_copy(update={"casova_obrada": o, "casova_utvrdjivanje": u,
                                "casova_ostalo": r, "jedinice": []}, deep=True)


def uskladi_fond(teme: list[Tema], broj_slotova: int, strategija: Strategija) -> list[Tema]:
    """Uskladi zbir časova tema sa stvarnim brojem časova iz kalendara."""
    teme = [t.model_copy(deep=True) for t in teme]
    potrebno = sum(t.casova_ukupno for t in teme)
    if strategija == "bez_izmena" or potrebno == broj_slotova:
        return teme
    if strategija == "rezerva" and broj_slotova > potrebno:
        teme.append(Tema(
            redni_broj=max((t.redni_broj for t in teme), default=0) + 1,
            naziv="Sistematizacija i rezerva",
            casova_ostalo=broj_slotova - potrebno,
        ))
        return teme
    # proporcionalno (i "rezerva" kada časova nedostaje)
    nova = _najveci_ostatak([float(t.casova_ukupno) for t in teme], broj_slotova,
                            minimum=1 if broj_slotova >= len(teme) else 0)
    return [_podeli_temu(t, n) for t, n in zip(teme, nova)]


def postavi_provere(teme: list[Tema], broj_provera: int) -> list[Tema]:
    """Pretvori po jedan čas utvrđivanja u proveru znanja u `broj_provera` ravnomerno raspoređenih tema."""
    teme = [t.model_copy(deep=True) for t in teme]
    kandidati = [t for t in teme if (t.casova_utvrdjivanje > 0 or t.casova_obrada > 1)
                 and "sistematizacij" not in t.naziv.lower()]
    if broj_provera <= 0 or not kandidati:
        return teme
    broj_provera = min(broj_provera, len(kandidati))
    korak = len(kandidati) / broj_provera
    izabrane = {kandidati[min(len(kandidati) - 1, math.floor((i + 1) * korak) - 1)].redni_broj
                for i in range(broj_provera)}
    for t in teme:
        if t.redni_broj in izabrane:
            if t.casova_utvrdjivanje > 0:
                t.casova_utvrdjivanje -= 1
            else:
                t.casova_obrada -= 1
            t.casova_ostalo += 1
            t.jedinice = []
    return teme


def sekvenca_jedinica(t: Tema) -> list[NastavnaJedinica]:
    """Redosled časova u temi. Koristi jedinice ako postoje, inače generiše šablon."""
    if t.jedinice and len(t.jedinice) == t.casova_ukupno:
        return list(t.jedinice)
    o, u, r = t.casova_obrada, t.casova_utvrdjivanje, t.casova_ostalo
    niz: list[NastavnaJedinica] = []
    # utvrđivanje ravnomerno umetnuto posle grupa obrade
    grupa = math.ceil(o / u) if u else o + 1
    ui = 0
    for i in range(1, o + 1):
        niz.append(NastavnaJedinica(naziv=f"{t.naziv} – obrada ({i}/{o})", tip="obrada"))
        if u and i % grupa == 0 and ui < u:
            ui += 1
            niz.append(NastavnaJedinica(naziv=f"{t.naziv} – utvrđivanje ({ui}/{u})", tip="utvrđivanje"))
    while ui < u:
        ui += 1
        niz.append(NastavnaJedinica(naziv=f"{t.naziv} – utvrđivanje ({ui}/{u})", tip="utvrđivanje"))
    if t.naziv == "Sistematizacija i rezerva":
        niz += [NastavnaJedinica(naziv="Sistematizacija / rezervni čas", tip="rezerva") for _ in range(r)]
    else:
        for i in range(r):
            poslednji = i == r - 1
            niz.append(NastavnaJedinica(
                naziv=f"{t.naziv} – {'provera znanja' if poslednji else 'sistematizacija'}",
                tip="provera" if poslednji else "sistematizacija"))
    return niz


def rasporedi(teme: list[Tema], slotovi: list[date]) -> tuple[list[Cas], int]:
    """Dodeli časove tema datumima redom. Vraća (časovi, broj časova koji nisu stali)."""
    casovi: list[Cas] = []
    i = 0
    nije_stalo = 0
    for t in teme:
        for j in sekvenca_jedinica(t):
            if i >= len(slotovi):
                nije_stalo += 1
                continue
            casovi.append(Cas(redni_broj=i + 1, datum=slotovi[i], tema_rb=t.redni_broj,
                              tema=t.naziv, jedinica=j.naziv, tip=j.tip))
            i += 1
    return casovi, nije_stalo


def meseci_u_godini(casovi: list[Cas]) -> list[tuple[int, int]]:
    """(godina, mesec) redom kako se pojavljuju."""
    return list(OrderedDict.fromkeys((c.datum.year, c.datum.month) for c in casovi))


def globalni_plan(casovi: list[Cas], teme: list[Tema]) -> dict:
    """Tabela: tema × mesec, plus zbir po tipu časa."""
    meseci = meseci_u_godini(casovi)
    redovi = []
    for t in teme:
        ct = [c for c in casovi if c.tema_rb == t.redni_broj]
        po_mesecu = {m: sum(1 for c in ct if (c.datum.year, c.datum.month) == m) for m in meseci}
        redovi.append({
            "rb": t.redni_broj,
            "tema": t.naziv,
            "po_mesecu": po_mesecu,
            "obrada": sum(1 for c in ct if c.tip == "obrada"),
            "utvrdjivanje": sum(1 for c in ct if c.tip == "utvrđivanje"),
            "ostalo": sum(1 for c in ct if c.tip not in ("obrada", "utvrđivanje")),
            "ukupno": len(ct),
        })
    return {
        "meseci": meseci,
        "nazivi_meseci": [MESECI[m] for _, m in meseci],
        "redovi": redovi,
        "ukupno_po_mesecu": {m: sum(r["po_mesecu"][m] for r in redovi) for m in meseci},
        "ukupno": len(casovi),
    }


def operativni_plan(casovi: list[Cas], godina: int, mesec: int) -> list[Cas]:
    return [c for c in casovi if c.datum.year == godina and c.datum.month == mesec]


def napravi_plan(program: Program, slotovi: list[date], strategija: Strategija = "proporcionalno",
                 broj_provera: int = 0) -> tuple[list[Tema], list[Cas], int]:
    teme = uskladi_fond(program.teme, len(slotovi), strategija)
    teme = postavi_provere(teme, broj_provera)
    casovi, nije_stalo = rasporedi(teme, slotovi)
    return teme, casovi, nije_stalo
