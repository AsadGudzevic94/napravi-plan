"""Automatska provera gotovog plana — ono što bi iskusan nastavnik/pedagog proverio pre predaje.

Svaka provera vraća (status, poruka): status je "ok", "upozorenje" ili "greska".
Agent posle pravljenja plana pokreće provere i, ako ima grešaka, ispravlja plan ili pita nastavnika.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from .kalendar import neradni_dani
from .modeli import Cas, Program, SkolskiKalendar
from .raspodela import RB_INICIJALNI, RB_PISMENI


def proveri_plan(program: Program, casovi: list[Cas], kalendar: SkolskiKalendar,
                 broj_slotova: int | None = None) -> list[tuple[str, str]]:
    rez: list[tuple[str, str]] = []

    def dodaj(uslov: bool, ok: str, lose: str, nivo: str = "greska"):
        rez.append(("ok", ok) if uslov else (nivo, lose))

    ukupno = program.ukupno_casova
    if broj_slotova is not None and broj_slotova < ukupno:
        dodaj(len(casovi) == broj_slotova, f"Kalendar ima {broj_slotova} časova (manje od glasnika {ukupno}) — "
              "plan je skraćen na raspoložive časove.", f"Plan ima {len(casovi)} časova, a u kalendaru ih ima "
              f"{broj_slotova}.", "upozorenje")
    else:
        dodaj(len(casovi) == ukupno, f"Ukupno {len(casovi)} časova — tačno koliko propisuje glasnik.",
              f"Plan ima {len(casovi)} časova, a glasnik propisuje {ukupno}.")

    po_temi = Counter(c.tema_rb for c in casovi)
    for t in program.teme:
        if broj_slotova is None or broj_slotova >= ukupno:
            dodaj(po_temi.get(t.redni_broj, 0) == t.casova_ukupno,
                  f"Tema „{t.naziv}“: {t.casova_ukupno} časova kao u glasniku.",
                  f"Tema „{t.naziv}“ ima {po_temi.get(t.redni_broj, 0)} časova, glasnik: {t.casova_ukupno}.")

    neradni = neradni_dani(kalendar)
    losi = [c for c in casovi if c.datum in neradni or c.datum < kalendar.pocetak or c.datum > kalendar.kraj
            or (c.datum.weekday() >= 5 and c.datum not in {z.datum for z in kalendar.zamene})]
    dodaj(not losi, "Nijedan čas nije na praznik, raspust ili vikend.",
          "Časovi na neradne dane: " + ", ".join(f"{c.datum:%d.%m.} ({neradni.get(c.datum, 'vikend')})"
                                                 for c in losi[:5]))

    redovni = [c.tema_rb for c in casovi if 0 < c.tema_rb < RB_PISMENI]
    dodaj(redovni == sorted(redovni), "Teme idu redosledom iz programa.",
          "Teme nisu redosledom iz programa.", "upozorenje")

    if program.inicijalni_casova:
        prvi = [c for c in casovi[:program.inicijalni_casova]]
        dodaj(all(c.tip == "inicijalni" for c in prvi), "Inicijalni test je na početku godine.",
              "Inicijalni test nije na prvim časovima.")

    pismeni = [c for c in casovi if c.tip == "pismeni"]
    if program.pismeni_broj:
        dodaj(len(pismeni) == program.pismeni_broj * program.pismeni_trajanje,
              f"Planirano {program.pismeni_broj} pismena zadatka.",
              f"Planirano {len(pismeni) // max(1, program.pismeni_trajanje)} pismenih, glasnik: {program.pismeni_broj}.")
        if program.pismeni_trajanje > 1:
            po_pz: dict[str, list[date]] = {}
            for c in pismeni:
                po_pz.setdefault(c.jedinica.split(" (")[0], []).append(c.datum)
            razdvojeni = [k for k, d in po_pz.items() if len(set(d)) > 1]
            dodaj(not razdvojeni, f"Svaki pismeni ({program.pismeni_trajanje} časa) je u jednom danu — na blok času.",
                  "Pismeni nisu na blok času (delovi u različitim danima): " + ", ".join(razdvojeni) +
                  ". Proverite raspored — da li imate blok čas?", "upozorenje")
        kp = kalendar.kraj_prvog_polugodista
        prvo = len({c.jedinica.split(" (")[0] for c in pismeni if c.datum <= kp})
        dodaj(prvo == program.pismeni_broj // 2,
              f"Pismeni podjednako po polugodištima ({prvo} + {program.pismeni_broj - prvo}).",
              f"U I polugodištu je {prvo} pismenih, očekivano {program.pismeni_broj // 2}.", "upozorenje")
        if program.pismeni_ispravka:
            ispravke = [c for c in casovi if c.tip == "ispravka"]
            van = []
            for isp in ispravke:
                br = isp.jedinica.split(".")[0].split()[-1]
                pz = [c for c in pismeni if c.jedinica.startswith(f"{br}.")]
                if pz and ((pz[-1].datum <= kp) != (isp.datum <= kp)):
                    van.append(isp.jedinica)
            dodaj(len(ispravke) == program.pismeni_broj and not van,
                  "Ispravke su posle pismenih i u istom polugodištu.",
                  "Ispravka nije u istom polugodištu kao pismeni: " + ", ".join(van) if van else
                  f"Broj ispravki ({len(ispravke)}) ≠ broj pismenih ({program.pismeni_broj}).", "upozorenje")

    bez_mk = [t.naziv for t in program.teme if not t.kompetencije]
    dodaj(not bez_mk, "Svaka tema ima međupredmetne kompetencije.",
          "Teme bez međupredmetnih kompetencija: " + ", ".join(bez_mk), "upozorenje")
    bez_kor = [t.naziv for t in program.teme if not t.korelacija]
    dodaj(not bez_kor, "Svaka tema ima predmete za povezivanje.",
          "Teme bez predmeta za povezivanje: " + ", ".join(bez_kor), "upozorenje")

    po_mesecu = Counter((c.datum.year, c.datum.month) for c in casovi)
    prazni = [f"{m:02d}." for (g, m) in _meseci(kalendar) if not po_mesecu.get((g, m))]
    dodaj(not prazni, "Svaki nastavni mesec ima časove.", "Meseci bez časova: " + ", ".join(prazni), "upozorenje")
    _ = RB_INICIJALNI
    return rez


def _meseci(k: SkolskiKalendar) -> list[tuple[int, int]]:
    out, g, m = [], k.pocetak.year, k.pocetak.month
    while (g, m) <= (k.kraj.year, k.kraj.month):
        out.append((g, m))
        g, m = (g + 1, 1) if m == 12 else (g, m + 1)
    return out


def izvestaj(rez: list[tuple[str, str]]) -> str:
    znak = {"ok": "✅", "upozorenje": "⚠️", "greska": "❌"}
    return "\n".join(f"{znak[s]} {p}" for s, p in rez)
