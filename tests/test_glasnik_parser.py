"""Parser na malom veštačkom DOCX-u istog oblika kao Pravilnik (Prosvetni glasnik 7/2023)."""
import io

import docx

from planer.glasnik_parser import blokovi_iz_docx, izaberi, naslov_izvora, parsiraj_blokove, u_program
from planer.pismo import u_cirilicu, u_latinicu
from planer.raspodela import napravi_plan
from planer.kalendar import slotovi_casova
from planer.podrazumevani_kalendar import kalendar_za


def _mini_glasnik() -> bytes:
    d = docx.Document()
    t = d.add_table(rows=1, cols=1)
    t.rows[0].cells[0].text = 'ПРАВИЛНИК\n("Сл. гласник РС - Просветни гласник", бр. 7/2023)'
    for opis, fond in (("(за образовне профиле у четворогодишњем трајању који имају 2 часа недељно)", "2 часа"),
                       ("(за образовне профиле у четворогодишњем трајању који имају 3 часа недељно)", "3 часа")):
        d.add_paragraph("МАТЕМАТИКА")
        d.add_paragraph(opis)
        d.add_paragraph("Циљ учења Математике је ...")
        t = d.add_table(rows=4, cols=2)
        t.cell(0, 0).text, t.cell(0, 1).text = "Разред", "Други"
        t.cell(1, 0).text, t.cell(1, 1).text = "Недељни фонд часова", fond
        t.cell(2, 0).text, t.cell(2, 1).text = "ИСХОДИ\nПо завршетку разреда ученик ће бити у стању да:", "ТЕМА"
        t.cell(3, 0).text = ("– скицира график квадратне функције;\n– реши тригонометријску једначину;\n"
                             "– израчуна степен комплексног броја;*")
        t.cell(3, 1).text = ("КВАДРАТНА ФУНКЦИЈА\nКвадратна функција и њен график. Вијетове формуле.\n"
                             "ТРИГОНОМЕТРИЈСКЕ ФУНКЦИЈЕ\nТригонометријски круг.\nМоаврова формула.*")
        d.add_paragraph("* само за образовне профиле у подручју рада Електротехника")
        d.add_paragraph("Ради лакшег планирања наставе даје се оријентациони предлог броја часова по темама.")
        d.add_paragraph("Други разред")
        d.add_paragraph("Квадратна функција (40)")
        d.add_paragraph("Тригонометријске функције (51)")
        d.add_paragraph("Напомена: за иницијално процењивање и анализу његових резултата планирана су 2 часа, "
                        "а за реализацију 4 писмена задатка (у трајању од по два часа), са исправкама, "
                        "планирано је 12 часова.")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def test_parser_bira_varijantu_i_cita_casove():
    bl = blokovi_iz_docx(_mini_glasnik())
    assert "7/2023" in naslov_izvora(bl)
    vs = parsiraj_blokove(bl)
    assert len(vs) == 2
    [v] = izaberi(vs, "Matematika", 2, nedeljni_fond=3, trajanje=4)
    assert v.nedeljni_fond == 3 and [t.casova_obrada for t in v.teme] == [40, 51]
    assert (v.inicijalni, v.pismeni_broj, v.pismeni_trajanje, v.pismeni_casova) == (2, 4, 2, 12)
    p = u_program(v, "Tehničar drumskog saobraćaja", tip_skole="srednja")
    assert p.ukupno_casova == 105
    assert p.teme[0].naziv == "Квадратна функција"
    assert not any("Моаврова" in s for t in p.teme for s in t.sadrzaji)  # * samo za Elektrotehniku
    assert any("Моаврова" in s for t in u_program(v, "Elektrotehničar računara").teme for s in t.sadrzaji)
    assert p.teme[0].ishodi and "квадратне" in p.teme[0].ishodi[0]


def test_ceo_plan_iz_glasnika_sa_pismenim_na_bloku():
    [v] = izaberi(parsiraj_blokove(blokovi_iz_docx(_mini_glasnik())), "Matematika", 2, 3, 4)
    p = u_program(v, "Tehničar drumskog saobraćaja", tip_skole="srednja")
    k = kalendar_za(2026, "srednja", 2)
    sl = slotovi_casova(k, {1: 1, 3: 2})  # utorak 1, četvrtak blok 2
    teme, casovi, nije_stalo = napravi_plan(p, sl, udeo_obrade=0.4, kraj_polugodista=k.kraj_prvog_polugodista)
    assert len(sl) > 105
    assert nije_stalo == 0 and len(casovi) == 105  # glasnik ima prednost nad kalendarom
    assert sum(t.casova_ukupno for t in teme) == 105
    # slobodni časovi su na kraju polugodišta, a ne usred godine
    planirani = {c.datum for c in casovi}
    assert sl[0] in planirani and casovi[-1].datum < sl[-1]
    pismeni = [c for c in casovi if c.tip == "pismeni"]
    assert len(pismeni) == 8
    for a, b in zip(pismeni[::2], pismeni[1::2]):
        assert a.datum == b.datum  # dvočas istog dana
    assert sum(c.datum <= k.kraj_prvog_polugodista for c in pismeni) == 4  # 2 pismena u I polugodištu
    isp = [c for c in casovi if c.tip == "ispravka"]
    assert len(isp) == 4 and all(i.redni_broj > pz.redni_broj for i, pz in zip(isp, pismeni[1::2]))
    assert casovi[0].tip == "inicijalni"


def test_preslovljavanje():
    assert u_cirilicu("Utvrđivanje: Ljubav i džep, a x2") == "Утврђивање: Љубав и џеп, а x2"
    assert u_latinicu("Њива ЉУБАВ") == "Njiva LjUBAV"
