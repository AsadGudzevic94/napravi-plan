import io

from docx import Document
from openpyxl import load_workbook

from planer.ekstrakcija import izvuci_program
from planer.intervju import ucitaj_primer
from planer.izvoz import globalni_docx, operativni_docx, plan_xlsx
from planer.llm import izvuci_json
from planer.raspodela import globalni_plan, napravi_plan, operativni_plan, sekvenca_jedinica
from planer.sadrzaj import generisi_jedinice, obogati_operativni
from tests.test_raspodela import slotovi


class LaznLLM:
    """Zamena za LLM u testovima — vraća unapred zadat JSON."""
    def __init__(self, odgovor):
        self.odgovor = odgovor

    def chat_json(self, sistem, korisnik, **kw):
        return self.odgovor(korisnik) if callable(self.odgovor) else self.odgovor


def test_izvuci_json_iz_markdowna():
    assert izvuci_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert izvuci_json('Evo: {"a": 2} hvala') == {"a": 2}


def test_ekstrakcija_programa():
    llm = LaznLLM({"predmet": "Fizika", "razred": 2, "nedeljni_fond": 2, "izvor": "PG 5/2020",
                   "teme": [{"naziv": "Kinematika", "casova_obrada": 10, "casova_utvrdjivanje": 6,
                             "casova_ostalo": 0, "ishodi": ["x"]}]})
    p = izvuci_program(llm, "tekst", "Fizika", 2, "srednja")
    assert p.teme[0].redni_broj == 1 and p.zbir_tema == 16 and p.tip_skole == "srednja"


def test_jedinice_cuvaju_tipove_i_broj():
    p = ucitaj_primer()
    t = p.teme[1]
    llm = LaznLLM({"jedinice": [{"naziv": f"J{i}", "tip": "pogrešno"} for i in range(5)]})  # premalo
    j = generisi_jedinice(llm, p, t)
    assert len(j) == t.casova_ukupno
    assert j[0].naziv == "J0" and j[0].tip == "obrada"
    assert j[-1].naziv == sekvenca_jedinica(t)[-1].naziv  # ostatak šablonski


def test_obogati_i_izvoz():
    p = ucitaj_primer()
    teme, casovi, _ = napravi_plan(p, slotovi(144), "bez_izmena")
    mesec = operativni_plan(casovi, 2026, 9)
    llm = LaznLLM(lambda upit: {"casovi": [{"redni_broj": c.redni_broj, "metode": "dijaloška"} for c in mesec]})
    mesec = obogati_operativni(llm, p, mesec, teme)
    assert all(c.metode == "dijaloška" for c in mesec)
    gp = globalni_plan(casovi, teme)
    d = Document(io.BytesIO(globalni_docx(p, gp)))
    assert len(d.tables[0].rows) == len(teme) + 3  # ZUOV: dva reda zaglavlja (MESEC / IX…VI) + Ukupno
    assert [c.text for c in d.tables[0].rows[1].cells[2:12]] == ["IX", "X", "XI", "XII", "I", "II", "III", "IV",
                                                                   "V", "VI"]
    assert "MEĐUPREDMETNE KOMPETENCIJE" in d.tables[1].rows[0].cells[2].text
    d = Document(io.BytesIO(operativni_docx(p, mesec, 9)))
    assert len(d.tables[0].rows) == len(mesec) + 1
    assert "EVALUACIJA ISPLANIRANOG" in d.tables[0].rows[0].cells[5].text
    wb = load_workbook(io.BytesIO(plan_xlsx(p, gp, casovi)))
    assert wb.sheetnames[0] == "Globalni plan" and "Septembar" in wb.sheetnames
