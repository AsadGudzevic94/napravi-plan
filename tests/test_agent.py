"""Kontrolisani agent: LLM samo razume poruke, kod vodi korake i računa."""
from planer.agent import Agent
from planer.glasnik_parser import blokovi_iz_docx, parsiraj_blokove
from tests.test_glasnik_parser import _mini_glasnik


class LazniLLM:
    """Glumi model: za svaku poruku nastavnika vraća ono što bi pravi model izvukao."""
    def __init__(self, odgovori):
        self.odgovori = list(odgovori)
        self.upiti = []

    def chat_json(self, sistem, upit, **kw):
        self.upiti.append(upit)
        return self.odgovori.pop(0) if self.odgovori else {}


def _agent(odgovori):
    a = Agent(LazniLLM(odgovori))
    bl = blokovi_iz_docx(_mini_glasnik())
    a.posalji_glasnik(parsiraj_blokove(bl), "PG 7/2023")
    return a


def test_jedna_poruka_popunjava_vise_koraka_i_agent_sam_cita_glasnik():
    a = _agent([{"tip_skole": "srednja", "razred": "2", "predmet": "Matematika",
                 "smer": "Tehničar drumskog saobraćaja", "trajanje_srednje": "4", "nedeljni_fond": "3",
                 "raspored": "utorak 1, četvrtak 2", "skolska_godina": "2026/27"}])
    odg = a.korak("Matematika, srednja stručna, 2. razred TDS (4 god.), 3 časa, uto 1 i čet blok 2, 2026/27")
    assert "105" in odg and "Program" in odg  # program iz glasnika pokazan na potvrdu
    assert any("Program iz glasnika" in k for k in a.koraci)


def test_ceo_postupak_do_proverenog_plana():
    a = _agent([
        {"tip_skole": "srednja", "razred": "2", "predmet": "Matematika", "smer": "Tehničar drumskog saobraćaja",
         "trajanje_srednje": "4", "nedeljni_fond": "3"},
        {"komande": ["da"]},                                # „jeste, tako je“ → program ok
        {"udeo_obrade": "40"},                              # obrada 40 %
        # „u redu“ za pismene razume parser bez LLM-a
        {"raspored": "utorak 1, četvrtak 2", "skolska_godina": "2026/27"},
        {"komande": ["da"]},                                # kalendar ok
        {"broj_provera": "0", "udzbenik": "-", "zelje": "-", "strucni_predmeti": "Saobraćajna tehnika",
         "predmeti_odeljenja": "Fizika, Računarstvo i informatika"},
        {"komande": ["2: Fizika, Saobraćajna tehnika"]},   # izmena kompetencija slobodnim rečima
        {"komande": ["da"]},
        {"pismo": "ćirilica"},
    ])
    poruke = ["Matematika 2. razred TDS, četvorogodišnji, 3 časa", "jeste, tako je", "neka obrada bude 40 posto",
              "u redu", "utorkom jedan čas, četvrtkom blok, školska 2026/27", "kalendar je dobar",
              "nema kontrolnih, bez udžbenika, bez želja; stručni Saobraćajna tehnika; imaju Fiziku i Računarstvo",
              "za drugu temu stavi Fiziku i Saobraćajnu tehniku", "sad je dobro", "ćirilicom"]
    for p in poruke:
        odg = a.korak(p)
    assert a.gotovo, odg
    assert len(a.plan["casovi"]) == 105
    assert "❌" not in odg and "Ukupno 105" in odg
    assert a.iv.s["program"].teme[1].korelacija == ["Fizika", "Saobraćajna tehnika"]
    assert a.iv.s["pismo"] == "ćirilica"


def test_bez_llm_radi_kao_vodjeni_razgovor():
    a = Agent(None)
    assert "osnovna" in a.korak("")
    assert "razred" in a.korak("srednja")
