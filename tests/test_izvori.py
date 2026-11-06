"""Pronalaženje glasnika — bez interneta (lažni preuzimač vraća unapred zadate odgovore)."""
import planer.izvori as izvori
from planer.glasnik_parser import (
    _predlog_casova,
    blokovi_iz_docx,
    blokovi_iz_html,
    izaberi,
    parsiraj_blokove,
    u_program,
)
from planer.intervju import Intervju
from planer.izvori import (
    Pravilnik,
    Predlog,
    Provera,
    Referenca,
    izaberi_katalog,
    pravilnici_iz_linija,
    predlozi,
    prilozi_iz_html,
    proveri_pravilnik,
)
from tests.test_glasnik_parser import _mini_glasnik

KATALOG = [
    "ПРАВНО ИНФОРМАЦИОНИ СИСТЕМ Републике Србије",
    "2.8 Саобраћај",
    "1 Правилник о степену и врсти образовања наставника у стручним школама у подручју рада",
    "Саобраћај : 14/2023-255, 2/2025-216",
    "2 Правилник о плану и програму наставе и учења стручних предмета средњег стручног образовања у подручју рада",
    "Саобраћај : 8/2018-340, 15/2020-259 (исправка), 2/2022-",
    "333",
    "3 Правилник о плану и програму наставе и учења општеобразовних предмета средњег стручног образовања и васпитања у",
    "подручју рада Саобраћај : 8/2018-1, 12/2022-1, 7/2023-3 (др. правилник), 13/2024-419",
    "4 Правилник о наставном плану и програму општеобразовних предмета средњег стручног образовања у подручју рада",
    "Саобраћај : 10/2015-1, 7/2023-3 (др. правилник)",
    "Правилник је престао да важи за образовни профил: возач моторних возила.",
]
LINKOVI = [f"https://pravno-informacioni-sistem.rs/viewAct/{i}" for i in range(4)]

OSNOVNA_HTML = """<p>PRAVILNIK O PROGRAMU NASTAVE I UČENJA ZA DRUGI RAZRED (br. 5/2021)</p>
<table><tr><td>Naziv predmeta</td><td>MATEMATIKA</td></tr><tr><td>Cilj</td><td>Cilj nastave...</td></tr>
<tr><td>Razred</td><td>Drugi</td></tr><tr><td>Godišnji fond časova</td><td>180 časova</td></tr></table>
<table><tr><td>ISHODI<br>Po završetku razreda učenik će biti u stanju da:</td><td>OBLAST/TEMA</td><td>SADRŽAJI</td></tr>
<tr><td>- usmeno sabira i oduzima brojeve do 100;</td><td>BROJEVI</td><td>Prvi deo<br>Sabiranje i oduzimanje.</td></tr>
<tr><td>- razlikuje duž, polupravu i pravu;</td><td>GEOMETRIJA</td><td>Duž, prava i poluprava.</td></tr></table>
<p>Radi lakšeg planiranja nastave, daje se orijentacioni predlog broja časova po temama</p>
<p>Brojevi (150; 60 + 90) Geometrija (30; 10+20)</p>"""


def test_katalog_spaja_redove_i_linkove():
    pr = pravilnici_iz_linija(KATALOG, LINKOVI, "2.8 Саобраћај")
    assert [p.rb for p in pr] == [1, 2, 3, 4]
    assert [r.oznaka for r in pr[1].reference] == ["8/2018-340", "15/2020-259", "2/2022-333"]
    assert pr[1].reference[1].napomena == "исправка"
    assert pr[2].reference[2] == Referenca(7, 2023, 3, "др. правилник")
    assert pr[2].reference[2].pg_id == "PG_007_2023_003"
    assert pr[3].pis_url.endswith("/3") and "престао" in pr[3].napomena


def test_predlozi_biraju_vazeci_pravilnik_za_predmet():
    pr = pravilnici_iz_linija(KATALOG, LINKOVI)
    pp = predlozi(pr, "Matematika", 2, "srednja", "tehničar drumskog saobraćaja")
    assert pp[0].pravilnik.rb == 3 and "opšteobrazovni" in pp[0].razlog
    assert all(p.pravilnik.rb != 1 for p in pp)  # stepen i vrsta obrazovanja nije program
    strucni = predlozi(pr, "Saobraćajna tehnika", 2, "srednja", "tehničar drumskog saobraćaja")
    assert strucni[0].pravilnik.rb == 2


def test_izbor_kataloga_po_smeru():
    k = [("2.5 Електротехника и информатика", "u5"), ("2.8 Саобраћај", "u8"), ("1. Гимназије", "u1"),
         ("2. Основно образовање и васпитање", "uo")]
    assert izaberi_katalog(k, "srednja", "Tehničar drumskog saobraćaja") == ("2.8 Саобраћај", "u8")
    assert izaberi_katalog(k, "srednja", "elektrotehničar računara")[1] == "u5"
    assert izaberi_katalog(k, "srednja", "gimnazija, opšti smer")[1] == "u1"
    assert izaberi_katalog(k, "osnovna", None)[1] == "uo"
    assert izaberi_katalog(k, "srednja", "frizer") is None  # nema takvog kataloga, a nema ni modela


def test_osnovna_skola_iz_html():
    v = izaberi(parsiraj_blokove(blokovi_iz_html(OSNOVNA_HTML)), "Matematika", 2)[0]
    assert v.nedeljni_fond == 5  # 180 / 36
    p = u_program(v, None, "PG 5/2021", "osnovna")
    assert [(t.naziv, t.casova_obrada, t.casova_utvrdjivanje) for t in p.teme] == [("Brojevi", 60, 90),
                                                                                  ("Geometrija", 10, 20)]
    assert p.teme[0].ishodi == ["usmeno sabira i oduzima brojeve do 100"]
    assert "Prvi deo" not in p.teme[0].sadrzaji


def test_predlog_casova_vise_tema_u_pasusu():
    assert _predlog_casova("Угао (17;7+10) Разломци (55; 23+32)") == [("Угао", 17, 7, 10),
                                                                       ("Разломци", 55, 23, 32)]
    assert _predlog_casova("Линеарне једначине, неједначине и системи (18)") == [
        ("Линеарне једначине, неједначине и системи", 18, None, None)]
    assert _predlog_casova("за реализацију 4 писмена задатка (у трајању од по два часа)") == []


class LazniPreuzimac:
    def __init__(self, odgovori):
        self.odgovori = odgovori

    def __call__(self, url):
        return self.odgovori.get(url, (404, b""))


def test_provera_preuzima_prilog_i_nalazi_program():
    prilog = "http://www.eupropisi.com/dokumenti/PG_007_2023_003.pdf"
    html = f'<p>PRAVILNIK O PROGRAMU (br. 7/2023)</p><a href="{prilog}">prilog</a>'
    assert prilozi_iz_html(html) == [prilog]
    preuzimac = LazniPreuzimac({
        "http://demo.paragraf.rs/demo/combined/Old/t/t2023_08/PG_007_2023_003.htm": (200, html.encode()),
        prilog: (200, _mini_glasnik()),  # „.pdf“ je zapravo DOCX, kao na pravom sajtu
    })
    p = Pravilnik(3, "Правилник о плану и програму…", [Referenca(8, 2018, 1), Referenca(7, 2023, 3)])
    pr = proveri_pravilnik(p, "Matematika", 2, 3, 4, preuzimac)
    assert pr.status == "provereno" and pr.referenca.oznaka == "7/2023-3"
    assert izaberi(pr.varijante, "Matematika", 2, 3, 4)


def test_provera_nedostupno_daje_link():
    p = Pravilnik(1, "Правилник…", [Referenca(1, 2020, 1)], "https://pravno-informacioni-sistem.rs/viewAct/x")
    pr = proveri_pravilnik(p, "Matematika", 2, 3, 4, LazniPreuzimac({}))
    assert pr.status == "nedostupno" and "pravno-informacioni-sistem" in pr.poruka


def test_intervju_pronadji_i_izaberi(monkeypatch):
    varijante = parsiraj_blokove(blokovi_iz_docx(_mini_glasnik()))
    pravilnik = Pravilnik(3, "Правилник о плану и програму…", [Referenca(7, 2023, 3)])
    monkeypatch.setattr(izvori, "pronadji_predloge",
                        lambda *a, **k: ([Predlog(pravilnik, 7, "opšteobrazovni")], "ZUOV katalog „2.8“"))
    monkeypatch.setattr(izvori, "proveri_pravilnik", lambda *a, **k: Provera(
        "provereno", "Glasnik 7/2023-3 sadrži program.", Referenca(7, 2023, 3), "url", varijante, "PG 7/2023"))
    iv = Intervju()
    for o in ["srednja", "2", "Matematika", "Tehničar drumskog saobraćaja", "4", "3"]:
        assert iv.odgovori(o) is None
    assert "pronađi" in iv.pitanje()
    assert iv.odgovori("pronađi") is None
    assert "Koji da koristim" in iv.pitanje()
    assert iv.odgovori("1") is None
    assert iv.s["program"].ukupno_casova == 105 and "7/2023" in iv.s["program"].izvor
    assert "Program" in iv.pitanje()  # sledeće: potvrda programa


def test_intervju_ne_vodi_na_slanje_fajla(monkeypatch):
    p = Pravilnik(1, "Правилник…", [Referenca(1, 2020, 1)])
    monkeypatch.setattr(izvori, "pronadji_predloge", lambda *a, **k: ([Predlog(p, 5, "")], "katalog"))
    iv = Intervju()
    for o in ["osnovna", "5", "Matematika", "4", "pronađi", "ne"]:
        assert iv.odgovori(o) is None
    assert "ošaljite **službeni glasnik**" in iv.pitanje()
