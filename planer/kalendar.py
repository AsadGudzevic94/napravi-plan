"""Školski kalendar: praznici, raspusti i datumi časova (deterministički, bez LLM-a)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .modeli import NeradniDan, SkolskiKalendar


def pravoslavni_uskrs(godina: int) -> date:
    """Pravoslavni Uskrs (Meeus, julijanski kalendar → gregorijanski)."""
    a, b, c = godina % 4, godina % 7, godina % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    mesec = (d + e + 114) // 31
    dan = (d + e + 114) % 31 + 1
    julijanski = date(godina, mesec, dan)
    return julijanski + timedelta(days=13)  # važi za 1900–2099


def drzavni_praznici_srbija(godina: int) -> list[NeradniDan]:
    """Neradni državni praznici RS u kalendarskoj godini (bez pomeranja sa nedelje)."""
    uskrs = pravoslavni_uskrs(godina)
    p = [
        (date(godina, 1, 1), "Nova godina"),
        (date(godina, 1, 2), "Nova godina"),
        (date(godina, 1, 7), "Božić"),
        (date(godina, 2, 15), "Sretenje – Dan državnosti"),
        (date(godina, 2, 16), "Sretenje – Dan državnosti"),
        (uskrs - timedelta(days=2), "Veliki petak"),
        (uskrs - timedelta(days=1), "Velika subota"),
        (uskrs, "Uskrs"),
        (uskrs + timedelta(days=1), "Uskršnji ponedeljak"),
        (date(godina, 5, 1), "Praznik rada"),
        (date(godina, 5, 2), "Praznik rada"),
        (date(godina, 11, 11), "Dan primirja"),
    ]
    # Ako Nova godina / Sretenje / Praznik rada padne u nedelju, neradni je i ponedeljak.
    dodatno = []
    for d, naziv in p:
        if d.weekday() == 6 and naziv in {"Nova godina", "Sretenje – Dan državnosti", "Praznik rada"}:
            dodatno.append((d + timedelta(days=1), naziv + " (prenos)"))
    return [NeradniDan(datum=d, naziv=n) for d, n in p + dodatno]


PRAZNICI_PO_DRZAVI = {"srbija": drzavni_praznici_srbija}


def ucitaj_kalendar(putanja: str | Path) -> SkolskiKalendar:
    return SkolskiKalendar.model_validate(json.loads(Path(putanja).read_text(encoding="utf-8")))


def neradni_dani(k: SkolskiKalendar) -> dict[date, str]:
    rezultat: dict[date, str] = {}
    if k.ukljuci_drzavne_praznike:
        f = PRAZNICI_PO_DRZAVI.get(k.drzava)
        if f:
            for g in range(k.pocetak.year, k.kraj.year + 1):
                for nd in f(g):
                    rezultat[nd.datum] = nd.naziv
    for nd in k.dodatni_neradni:
        rezultat[nd.datum] = nd.naziv
    for r in k.raspusti:
        d = r.od
        while d <= r.do:
            rezultat.setdefault(d, r.naziv)
            d += timedelta(days=1)
    return rezultat


def nastavni_dani(k: SkolskiKalendar) -> list[tuple[date, int]]:
    """Lista (datum, dan_po_rasporedu) za sve nastavne dane. dan_po_rasporedu: 0=pon..4=pet."""
    neradni = neradni_dani(k)
    zamene = {z.datum: z.po_rasporedu_dana for z in k.zamene}
    dani = []
    d = k.pocetak
    while d <= k.kraj:
        if d in zamene and d not in neradni:
            dani.append((d, zamene[d]))
        elif d.weekday() < 5 and d not in neradni:
            dani.append((d, d.weekday()))
        d += timedelta(days=1)
    return dani


def slotovi_casova(k: SkolskiKalendar, raspored: dict[int, int]) -> list[date]:
    """Datum za svaki čas u godini.

    raspored: {dan_u_nedelji: broj_casova_tog_dana}, npr. {0: 1, 3: 1} = pon i čet po 1 čas.
    """
    slotovi: list[date] = []
    for d, dan in nastavni_dani(k):
        slotovi.extend([d] * raspored.get(dan, 0))
    return slotovi


def broj_nastavnih_nedelja(k: SkolskiKalendar) -> float:
    """Broj nastavnih nedelja = min broj pojavljivanja nekog radnog dana (kao u pravilnicima)."""
    brojac = [0] * 5
    for _, dan in nastavni_dani(k):
        brojac[dan] += 1
    return min(brojac)


def brojac_dana(k: SkolskiKalendar) -> dict[int, int]:
    brojac = {i: 0 for i in range(5)}
    for _, dan in nastavni_dani(k):
        brojac[dan] += 1
    return brojac
