import pytest

from planer.ekstrakcija import nedeljni_fond_iz_teksta, normalizuj, pronadji_odeljak
from planer.intervju import Intervju, Stanje, parsiraj_raspored, parsiraj_teme_tekst


def test_raspored():
    s = Stanje({"nedeljni_fond": 3})
    assert parsiraj_raspored("utorak 2, petak", s) == {1: 2, 4: 1}
    assert parsiraj_raspored("pon, sre i čet", s) == {0: 1, 2: 1, 3: 1}
    with pytest.raises(ValueError):
        parsiraj_raspored("ponedeljak", s)  # zbir 1 ≠ fond 3


def test_rucne_teme():
    teme = parsiraj_teme_tekst("Uvod ; 4\nRazlomci ; 20 ; 10\nloš red")
    assert [t.casova_ukupno for t in teme] == [4, 30]


def test_ceo_intervju_srednja_bez_llm():
    iv = Intervju()
    odgovori = ["srednja", "II", "Fizika", "gimnazija opšti smer", "4", "2",
                "Kinematika ; 20 ; 10\nDinamika ; 25 ; 11", "da", "ponedeljak, četvrtak",
                "2026/27", "da"]
    for o in odgovori:
        assert iv.pitanje() is not None
        assert iv.odgovori(o) is None, (iv.pitanje(), o)
    # broj časova iz kalendara se razlikuje od 66 → pita za strategiju
    assert "Šta da uradim" in iv.pitanje()
    for o in ["1", "2", "-", "-", "ćirilica"]:
        assert iv.odgovori(o) is None
    assert iv.pitanje() is None
    teme, casovi, nije_stalo = iv.napravi()
    assert nije_stalo == 0 and len(casovi) == len(iv.s.slotovi())


def test_izmena_programa_i_kalendara():
    iv = Intervju()
    for o in ["osnovna", "5", "Matematika", "4", "primer"]:
        iv.odgovori(o)
    assert iv.odgovori("1 ; 30") is None  # izmena → ponovo pita
    assert "Program" in iv.pitanje()
    assert iv.s["program"].teme[0].casova_ukupno == 30
    assert iv.odgovori("redosled 2,1,3,4,5,6") is None
    assert iv.s["program"].teme[0].naziv == "Osnovni geometrijski pojmovi"
    for o in ["da", "pon uto sre pet", "2026"]:
        assert iv.odgovori(o) is None
    pre = len(iv.s.slotovi())
    assert iv.odgovori("kraj 2027-06-04") is None
    assert len(iv.s.slotovi()) < pre


def test_pronadji_odeljak_i_normalizacija():
    assert normalizuj("МАТЕМАТИКА Ђак") == "matematika djak"
    strane = ["Srpski jezik ...", "MATEMATIKA peti razred ishodi tema", "Matematika nastavak", "Fizika"]
    od = pronadji_odeljak(strane, "Matematika", 5, max_znakova=1000)
    assert "MATEMATIKA" in od and "Fizika" not in od
    assert nedeljni_fond_iz_teksta("Godišnji fond 144, 4 časa nedeljno") == 4
