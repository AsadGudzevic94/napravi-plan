"""Agent sa „lažnim“ LLM-om koji izvodi isti postupak koji bi izveo pravi model (Groq/Gemini)."""
import json

from planer.agent import Agent
from planer.glasnik_parser import blokovi_iz_docx, parsiraj_blokove
from tests.test_glasnik_parser import _mini_glasnik


def _poziv(i, ime, **arg):
    return {"id": f"c{i}", "type": "function", "function": {"name": ime, "arguments": json.dumps(arg)}}


class ScenarioLLM:
    """Vraća unapred zadat niz odgovora i pamti šta je agent dobio od alata."""
    def __init__(self, koraci):
        self.koraci = list(koraci)
        self.rezultati_alata = []

    def chat_alati(self, poruke, alati):
        self.rezultati_alata += [m["content"] for m in poruke if m["role"] == "tool"][len(self.rezultati_alata):]
        sledeci = self.koraci.pop(0)
        if isinstance(sledeci, str):
            return {"role": "assistant", "content": sledeci}
        return {"role": "assistant", "content": None, "tool_calls": sledeci}


def test_agent_postupno_pravi_i_proverava_plan():
    llm = ScenarioLLM([
        [_poziv(1, "postavi_podatke", podaci={"tip_skole": "srednja", "razred": "2", "predmet": "Matematika",
                                              "smer": "Tehničar drumskog saobraćaja", "trajanje_srednje": "4",
                                              "nedeljni_fond": "3"})],
        [_poziv(2, "pronadji_program")],
        [_poziv(3, "pitaj_nastavnika", pitanje="Našao sam program (105 časova). Da li je tačno?")],
        [_poziv(4, "pitaj_nastavnika", pitanje="Kojim danima držite čas?")],
        [_poziv(5, "postavi_podatke", podaci={"raspored": "utorak 1, četvrtak 2", "skolska_godina": "2026/27",
                                              "udeo_obrade": "40", "strucni_predmeti": "Saobraćajna tehnika"}),
         ],
        [_poziv(6, "izracunaj_kalendar")],
        [_poziv(7, "analiziraj_kompetencije")],
        [_poziv(8, "napravi_plan")],
        [_poziv(9, "proveri_plan")],
        [_poziv(10, "zavrsi", poruka="Plan je gotov: 105 časova, sve provere prošle.")],
    ])
    a = Agent(llm)
    bl = blokovi_iz_docx(_mini_glasnik())
    a.posalji_glasnik(parsiraj_blokove(bl), "PG 7/2023")

    assert "105" in a.korak("Treba mi plan za matematiku, 2. razred TDS, 3 časa")
    assert a.ceka_odgovor
    assert "danima" in a.korak("da")
    kraj = a.korak("utorak 1, četvrtak blok 2, školska 2026/27, obrada 40%, stručni: Saobraćajna tehnika")
    assert a.gotovo and "105" in kraj
    assert len(a.plan["casovi"]) == 105
    izvestaj = llm.rezultati_alata[-1]
    assert "❌" not in izvestaj and "Ukupno 105" in izvestaj
    assert any("Saobraćajna tehnika" in r for r in llm.rezultati_alata)  # korelacija iz logike
    assert any(k.startswith("🔧 napravi_plan") for k in a.koraci)


def test_agent_bez_glasnika_trazi_glasnik():
    llm = ScenarioLLM([[_poziv(1, "pronadji_program")], "Pošaljite glasnik, molim."])
    a = Agent(llm)
    a.korak("plan")
    assert "nije poslat" in a.poruke[-2]["content"]
