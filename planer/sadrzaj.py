"""LLM generiše tekstualni sadržaj: nazive nastavnih jedinica i kolone operativnog plana.

Brojevi časova su već određeni kodom — LLM samo daje nazive, i mora poštovati broj i tip.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .llm import LLM, LLMGreska
from .modeli import Cas, NastavnaJedinica, Program, Tema
from .raspodela import sekvenca_jedinica

SISTEM_JEDINICE = """Ti si iskusan nastavnik i metodičar. Za datu temu napravi tačno zadati niz
nastavnih jedinica (jedna jedinica = jedan čas). Tipovi i redosled su ZADATI i ne smeju se menjati;
ti samo daješ kratak, konkretan naziv svake jedinice (na srpskom, latinicom), u skladu sa ishodima,
sadržajima i udžbenikom ako je naveden. Vrati JSON: {"jedinice": [{"naziv": str, "tip": str}]}"""

SISTEM_OPERATIVNI = """Ti si iskusan nastavnik. Za svaki čas operativnog (mesečnog) plana popuni:
ishodi (šta će učenik moći na kraju časa, 1–2 kratka ishoda), metode (npr. dijaloška, monološka,
demonstrativna, rad na tekstu), oblici_rada (frontalni, grupni, rad u paru, individualni),
korelacija (drugi predmeti, ili prazno). Kratko i konkretno, srpski, latinica.
Vrati JSON: {"casovi": [{"redni_broj": int, "ishodi": str, "metode": str, "oblici_rada": str,
"korelacija": str}]} — za SVAKI dati redni broj."""


def generisi_jedinice(llm: LLM, program: Program, tema: Tema, udzbenik: str = "") -> list[NastavnaJedinica]:
    sablon = sekvenca_jedinica(tema)
    if not sablon:
        return []
    upit = (
        f"Predmet: {program.predmet}, {program.razred}. razred"
        f"{', smer ' + program.smer if program.smer else ''}\n"
        f"Tema: {tema.naziv}\nIshodi: {'; '.join(tema.ishodi) or '-'}\n"
        f"Sadržaji: {'; '.join(tema.sadrzaji) or '-'}\nUdžbenik: {udzbenik or '-'}\n"
        f"Zadati niz tipova ({len(sablon)} časova): {[j.tip for j in sablon]}"
    )
    try:
        odg = llm.chat_json(SISTEM_JEDINICE, upit, temperatura=0.4)
        nazivi = [j.get("naziv", "").strip() for j in odg.get("jedinice", [])]
    except (LLMGreska, ValueError):
        return sablon
    # tip uvek iz šablona; ako LLM vrati manje naziva, ostatak ostaje šablonski
    return [NastavnaJedinica(naziv=(nazivi[i] if i < len(nazivi) and nazivi[i] else s.naziv), tip=s.tip)
            for i, s in enumerate(sablon)]


def popuni_jedinice(llm: LLM, program: Program, teme: list[Tema], udzbenik: str = "",
                    paralelno: int = 3) -> list[Tema]:
    """Generiše nazive jedinica za sve teme (paralelno, ali umereno zbog limita besplatnih API-ja)."""
    with ThreadPoolExecutor(max_workers=paralelno) as ex:
        rezultati = list(ex.map(lambda t: generisi_jedinice(llm, program, t, udzbenik), teme))
    return [t.model_copy(update={"jedinice": j}) for t, j in zip(teme, rezultati)]


def obogati_operativni(llm: LLM, program: Program, casovi: list[Cas], teme: list[Tema],
                       zelje: str = "") -> list[Cas]:
    if not casovi:
        return casovi
    ishodi_tema = {t.redni_broj: t.ishodi for t in teme}
    redovi = "\n".join(
        f"{c.redni_broj}. [{c.tip}] tema: {c.tema} | jedinica: {c.jedinica} | "
        f"ishodi teme: {'; '.join(ishodi_tema.get(c.tema_rb, [])[:4]) or '-'}" for c in casovi)
    upit = (f"Predmet: {program.predmet}, {program.razred}. razred\n"
            f"Želje nastavnika: {zelje or '-'}\n\nČasovi:\n{redovi}")
    try:
        odg = llm.chat_json(SISTEM_OPERATIVNI, upit, temperatura=0.3)
    except (LLMGreska, ValueError):
        return casovi
    po_rb = {int(x.get("redni_broj", -1)): x for x in odg.get("casovi", []) if str(x.get("redni_broj", "")).isdigit()
             or isinstance(x.get("redni_broj"), int)}
    novi = []
    for c in casovi:
        x = po_rb.get(c.redni_broj, {})
        novi.append(c.model_copy(update={k: str(x.get(k, "") or "") for k in
                                         ("ishodi", "metode", "oblici_rada", "korelacija")}))
    return novi
