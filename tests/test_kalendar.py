from datetime import date

from planer.kalendar import (brojac_dana, drzavni_praznici_srbija, neradni_dani, pravoslavni_uskrs,
                             slotovi_casova)
from planer.modeli import Raspust, SkolskiKalendar, Zamena
from planer.podrazumevani_kalendar import kalendar_za


def test_pravoslavni_uskrs_poznati_datumi():
    assert pravoslavni_uskrs(2024) == date(2024, 5, 5)
    assert pravoslavni_uskrs(2025) == date(2025, 4, 20)
    assert pravoslavni_uskrs(2026) == date(2026, 4, 12)
    assert pravoslavni_uskrs(2027) == date(2027, 5, 2)


def test_praznici_ukljucuju_dan_primirja_i_prenos_sa_nedelje():
    datumi = {p.datum for p in drzavni_praznici_srbija(2027)}
    assert date(2027, 11, 11) in datumi
    assert date(2027, 5, 3) in datumi  # 2. maj 2027 je nedelja → ponedeljak neradni


def _k(**kw):
    return SkolskiKalendar(naziv="t", pocetak=date(2026, 9, 1), kraj_prvog_polugodista=date(2026, 12, 30),
                           kraj=date(2026, 9, 30), **kw)


def test_slotovi_samo_radnim_danima_po_rasporedu():
    sl = slotovi_casova(_k(), {0: 1, 3: 2})  # pon 1 čas, čet 2 časa
    assert all(d.weekday() in (0, 3) for d in sl)
    assert sl.count(date(2026, 9, 3)) == 2
    assert len(sl) == 4 * 1 + 4 * 2  # sept. 2026: 4 ponedeljka, 4 četvrtka


def test_raspust_i_zamena():
    k = _k(raspusti=[Raspust(naziv="r", od=date(2026, 9, 7), do=date(2026, 9, 11))],
           zamene=[Zamena(datum=date(2026, 9, 12), po_rasporedu_dana=0)])  # subota po rasporedu ponedeljka
    sl = slotovi_casova(k, {0: 1})
    assert date(2026, 9, 7) not in sl
    assert date(2026, 9, 12) in sl


def test_dan_primirja_nije_nastavni():
    k = kalendar_za(2026, "osnovna", 5)
    assert date(2026, 11, 11) in neradni_dani(k)
    sl = slotovi_casova(k, {2: 1})  # sreda
    assert date(2026, 11, 11) not in sl


def test_podrazumevani_kalendar_ima_oko_36_nedelja():
    k = kalendar_za(2026, "osnovna", 5)
    assert 34 <= min(brojac_dana(k).values()) <= 40
    k8 = kalendar_za(2026, "osnovna", 8)
    assert k8.kraj < k.kraj
