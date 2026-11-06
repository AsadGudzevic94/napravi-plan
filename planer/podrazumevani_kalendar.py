"""Približan školski kalendar kada zvanični JSON nije dostupan.

UVEK se prikazuje nastavniku na potvrdu — datumi raspusta se svake godine
propisuju Pravilnikom o kalendaru obrazovno-vaspitnog rada.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .kalendar import pravoslavni_uskrs, ucitaj_kalendar
from .modeli import Raspust, SkolskiKalendar

DATA = Path(__file__).resolve().parent.parent / "data" / "kalendari"


def _radni_dan_od(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _petak_pre(d: date) -> date:
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def zavrsni_razred(tip_skole: str, razred: int, trajanje_srednje: int = 4) -> bool:
    return (tip_skole == "osnovna" and razred == 8) or (tip_skole == "srednja" and razred == trajanje_srednje)


def kalendar_za(godina: int, tip_skole: str, razred: int, drzava: str = "srbija",
                trajanje_srednje: int = 4) -> SkolskiKalendar:
    """godina = početna godina školske godine, npr. 2026 za 2026/27."""
    oznaka = f"{drzava}_{godina}-{str(godina + 1)[2:]}"
    for ime in (f"{oznaka}_{tip_skole}_{razred}.json", f"{oznaka}_{tip_skole}.json", f"{oznaka}.json"):
        p = DATA / ime
        if p.exists():
            k = ucitaj_kalendar(p)
            if zavrsni_razred(tip_skole, razred, trajanje_srednje) and k.kraj_zavrsni:
                k.kraj = k.kraj_zavrsni
                k.naziv += " – završni razred (proveriti datum za svoj profil)"
            return k

    pocetak = _radni_dan_od(date(godina, 9, 1))
    zimski_od = date(godina, 12, 31)
    zimski_do = _petak_pre(date(godina + 1, 1, 16))
    uskrs = pravoslavni_uskrs(godina + 1)
    prolecni_od = uskrs - timedelta(days=2)
    prolecni_do = uskrs + timedelta(days=5)
    if zavrsni_razred(tip_skole, razred, trajanje_srednje):
        kraj = _petak_pre(date(godina + 1, 6, 6) if tip_skole == "osnovna" else date(godina + 1, 5, 31))
    else:
        kraj = _petak_pre(date(godina + 1, 6, 20))
    return SkolskiKalendar(
        naziv=f"Školska {godina}/{str(godina + 1)[2:]} – PRIBLIŽAN kalendar (proveriti sa Pravilnikom)",
        drzava=drzava,
        pocetak=pocetak,
        kraj_prvog_polugodista=zimski_od - timedelta(days=1),
        kraj=kraj,
        raspusti=[
            Raspust(naziv="Zimski raspust", od=zimski_od, do=zimski_do),
            Raspust(naziv="Prolećni raspust", od=prolecni_od, do=prolecni_do),
        ],
    )
