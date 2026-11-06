from datetime import date, timedelta

import pytest

from planer.intervju import ucitaj_primer
from planer.raspodela import (globalni_plan, napravi_plan, operativni_plan, postavi_provere,
                              sekvenca_jedinica, uskladi_fond)


def slotovi(n):
    d = date(2026, 9, 1)
    return [d + timedelta(days=i) for i in range(n)]


@pytest.mark.parametrize("n", [100, 144, 150, 160])
def test_proporcionalno_zbir_tacan(n):
    teme = uskladi_fond(ucitaj_primer().teme, n, "proporcionalno")
    assert sum(t.casova_ukupno for t in teme) == n
    assert all(t.casova_obrada >= 1 or t.casova_ukupno == 0 or t.naziv == "Sistematizacija" for t in teme)


def test_rezerva_dodaje_temu():
    teme = uskladi_fond(ucitaj_primer().teme, 150, "rezerva")
    assert teme[-1].naziv == "Sistematizacija i rezerva" and teme[-1].casova_ukupno == 6


def test_provere_ne_menjaju_zbir():
    p = ucitaj_primer()
    teme = postavi_provere(p.teme, 4)
    assert sum(t.casova_ukupno for t in teme) == p.zbir_tema
    assert sum(t.casova_ostalo for t in teme) == 4


def test_sekvenca_duzina_i_tipovi():
    t = ucitaj_primer().teme[0]
    s = sekvenca_jedinica(t)
    assert len(s) == t.casova_ukupno
    assert s[0].tip == "obrada"
    assert sum(j.tip == "utvrđivanje" for j in s) == t.casova_utvrdjivanje


def test_plan_bez_gubitaka():
    p = ucitaj_primer()
    sl = slotovi(144)
    teme, casovi, nije_stalo = napravi_plan(p, sl, "bez_izmena", broj_provera=3)
    assert nije_stalo == 0 and len(casovi) == 144
    assert [c.datum for c in casovi] == sl
    gp = globalni_plan(casovi, teme)
    assert gp["ukupno"] == 144
    assert sum(r["ukupno"] for r in gp["redovi"]) == 144
    mesec = operativni_plan(casovi, 2026, 9)
    assert len(mesec) == 30


def test_manjak_casova_prijavljen():
    _, casovi, nije_stalo = napravi_plan(ucitaj_primer(), slotovi(100), "bez_izmena")
    assert len(casovi) == 100 and nije_stalo == 44
