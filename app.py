"""Napravi plan — razgovor sa nastavnikom → godišnji i mesečni planovi po glasniku i ZUOV obrascima.

Pokretanje lokalno:  streamlit run app.py
Streamlit Community Cloud: vidi docs/OBJAVA.md
"""
from __future__ import annotations

import html
import os
import re
from pathlib import Path

import streamlit as st

from planer.agent import Agent
from planer.ekstrakcija import izvuci_program, nedeljni_fond_iz_teksta, pronadji_odeljak, stranice_iz_pdf
from planer.glasnik_parser import blokovi_iz_docx, naslov_izvora, parsiraj_blokove
from planer.intervju import Intervju
from planer.izvoz import globalni_docx, operativni_docx, plan_xlsx, preslovi
from planer.llm import LLM, LLMGreska
from planer.modeli import MESECI
from planer.raspodela import RB_INICIJALNI, RB_PISMENI, globalni_plan, meseci_u_godini, operativni_plan, rasporedi
from planer.sadrzaj import obogati_operativni, podrazumevano_operativno, popuni_jedinice

KOREN = Path(__file__).parent
st.set_page_config(page_title="Napravi plan", page_icon=str(KOREN / "ui" / "ikona.png"), layout="centered")
st.markdown(f"<style>{(KOREN / 'ui' / 'stil.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

AGENT, VODJENO = "Razgovor sa asistentom", "Korak po korak (bez AI)"
RIMSKI = {9: "IX", 10: "X", 11: "XI", 12: "XII", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}


# ---------------------------------------------------------------- pomoćno
def _kljucevi_iz_secrets() -> None:
    """Na Streamlit Cloud ključevi su u Secrets — prepiši ih u okruženje da ih LLM klijent nađe."""
    try:
        for k in ("LLM_PROVIDER", "LLM_MODEL", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:  # lokalno nema secrets.toml — u redu
        pass


@st.cache_resource
def llm_klijent() -> LLM | None:
    _kljucevi_iz_secrets()
    return LLM.iz_okruzenja()


_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF️]")


def ocisti(t: str) -> str:
    """Jezgro koristi emoji oznake; u aplikaciji ih menjamo mirnim tipografskim znakovima."""
    t = t.replace("✅", "✓").replace("❌", "✗").replace("⚠️", "Napomena:").replace("⚠", "Napomena:")
    return _EMOJI.sub("", t).replace("Napomena: Napomena:", "Napomena:").strip()


def tabela(kolone: list[str], redovi: list[list], klase: list[str], zbir_poslednji: bool = False) -> None:
    glava = "".join(f"<th>{html.escape(str(k))}</th>" for k in kolone)
    telo = []
    for i, red in enumerate(redovi):
        celije = []
        for v, kl in zip(red, klase):
            prazno = kl == "br" and v in ("", None, 0)
            celije.append(f'<td class="{kl}{" prazno" if prazno else ""}">{"·" if prazno else html.escape(str(v))}</td>')
        zbir = ' class="zbir"' if zbir_poslednji and i == len(redovi) - 1 else ""
        telo.append(f"<tr{zbir}>{''.join(celije)}</tr>")
    st.markdown(f'<div class="np-tabela-omot"><table class="np-tabela"><thead><tr>{glava}</tr></thead>'
                f'<tbody>{"".join(telo)}</tbody></table></div>', unsafe_allow_html=True)


def lista_provera(rez: list[tuple[str, str]]) -> None:
    znak = {"ok": ("✓", ""), "upozorenje": ("!", "upoz"), "greska": ("✗", "gres")}
    stavke = "".join(f'<li class="{znak[s][1]}"><span class="z">{znak[s][0]}</span>{html.escape(ocisti(p))}</li>'
                     for s, p in rez)
    st.markdown(f'<ul class="np-provera">{stavke}</ul>', unsafe_allow_html=True)


def poruka(uloga: str, tekst: str) -> None:
    with st.chat_message(uloga):
        st.markdown(ocisti(tekst))


# ---------------------------------------------------------------- stanje i okvir
llm = llm_klijent()
ss = st.session_state
if "iv" not in ss:
    ss.iv = Intervju(llm)
    ss.poruke = []
    ss.plan = None
iv: Intervju = ss.iv

st.markdown('<div class="np-glava"><h1>Napravi plan</h1>'
            '<p>Godišnji i mesečni planovi po službenom glasniku i ZUOV obrascima.</p></div>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Način rada")
    ss.rezim = st.radio("Način rada", [AGENT, VODJENO], index=0 if llm and ss.get("rezim") != VODJENO else 1,
                        disabled=not llm, label_visibility="collapsed",
                        help="Asistent razume slobodno napisane poruke; brojeve i datume uvek računa program.")
    st.caption(f"Model: {llm.provider} · {llm.model}" if llm else
               "Asistent nije podešen (nema API ključa) — radi način „korak po korak“.")
    st.markdown("### Zaglavlje dokumenata")
    ss.skola = st.text_input("Škola", ss.get("skola", ""))
    ss.nastavnik = st.text_input("Nastavnik", ss.get("nastavnik", ""))
    ss.odeljenje = st.text_input("Odeljenje", ss.get("odeljenje", ""), placeholder="npr. 3")
    ss.sa_datumima = st.checkbox("Datumi u mesečnom planu", ss.get("sa_datumima", False),
                                 help="ZUOV obrazac nema datume; uključite ako ih želite pored naziva jedinice.")
    st.write("")
    if st.button("Počni nov plan"):
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()


def postavi_pitanje(greska: str | None = None) -> None:
    if greska:
        ss.poruke.append(("assistant", "Napomena: " + greska))
    elif (tekst := iv.pitanje()) is not None:
        ss.poruke.append(("assistant", tekst))


# ---------------------------------------------------------------- razgovor sa asistentom
if ss.rezim == AGENT:
    if "agent" not in ss:
        ss.agent = Agent(llm)
        ss.agent_poruke = [("assistant", ss.agent.pocetak())]
    agent: Agent = ss.agent
    for uloga, tekst in ss.agent_poruke:
        poruka(uloga, tekst)
    if agent.koraci:
        with st.expander(f"Šta je asistent uradio · {len(agent.koraci)} koraka"):
            st.markdown("\n".join(f"- {ocisti(k)}" for k in agent.koraci))
    if not agent.gotovo:
        gl = None if agent.glasnik else st.file_uploader("Glasnik (DOCX)", type=["docx"], key="agent_glasnik",
                              help="Pravilnik o programu nastave i učenja, npr. preuzet sa paragraf.rs")
        if gl is not None and ss.get("agent_glasnik_ime") != gl.name:
            ss.agent_glasnik_ime = gl.name
            with st.spinner("Čitam glasnik…"):
                bl = blokovi_iz_docx(gl.getvalue())
                agent.posalji_glasnik(parsiraj_blokove(bl), naslov_izvora(bl) or gl.name)
            ss.agent_poruke.append(("user", f"Poslat glasnik: {gl.name}"))
            with st.spinner("Radim…"):
                ss.agent_poruke.append(("assistant", agent.korak("")))
            st.rerun()
        if odg := st.chat_input("Napišite odgovor…"):
            ss.agent_poruke.append(("user", odg))
            with st.spinner("Radim korak po korak…"):
                ss.agent_poruke.append(("assistant", agent.korak(odg)))
            st.rerun()
        st.stop()
    iv = agent.iv
    if ss.plan is None:
        ss.plan = agent.plan

# ---------------------------------------------------------------- korak po korak (bez AI)
else:
    if not ss.poruke:
        postavi_pitanje()
    for uloga, tekst in ss.poruke:
        poruka(uloga, tekst)
    p = iv.trenutno()
    if p and p.kljuc == "program":
        gl = st.file_uploader("Glasnik (DOCX ili PDF)", type=["docx", "pdf"])
        if gl is not None and ss.get("pdf_ime") != gl.name:
            ss.pdf_ime = gl.name
            ss.poruke.append(("user", f"Poslat glasnik: {gl.name}"))
            with st.spinner("Čitam glasnik…"):
                if gl.name.lower().endswith(".docx"):
                    bl = blokovi_iz_docx(gl.getvalue())
                    postavi_pitanje(iv.postavi_glasnik(parsiraj_blokove(bl), naslov_izvora(bl) or gl.name))
                else:
                    odeljak = pronadji_odeljak(stranice_iz_pdf(gl.getvalue()), iv.s["predmet"], iv.s["razred"])
                    if not odeljak.strip():
                        postavi_pitanje("PDF nema tekst (verovatno je skeniran). Pošaljite DOCX ili upišite "
                                        "teme ručno.")
                    elif not llm:
                        postavi_pitanje("Za čitanje PDF-a potreban je asistent (API ključ). Pošaljite DOCX ili "
                                        "upišite teme ručno.")
                    else:
                        try:
                            program = izvuci_program(llm, odeljak, iv.s["predmet"], iv.s["razred"],
                                                     iv.s["tip_skole"], iv.s.get("smer"))
                            program.nedeljni_fond = program.nedeljni_fond or nedeljni_fond_iz_teksta(odeljak) or 0
                            program.izvor = program.izvor or gl.name
                            iv.postavi_program(program)
                            postavi_pitanje()
                        except (LLMGreska, ValueError) as e:
                            postavi_pitanje(f"Nisam uspeo da pročitam program iz PDF-a: {e}")
            st.rerun()
    if p:
        if odg := st.chat_input("Napišite odgovor…"):
            ss.poruke.append(("user", odg))
            postavi_pitanje(iv.odgovori(odg))
            st.rerun()
        st.stop()
    if ss.plan is None:
        with st.spinner("Raspoređujem časove po kalendaru…"):
            teme, casovi, nije_stalo = iv.napravi()
        if llm:
            with st.spinner("Pišem nazive nastavnih jedinica…"):
                program = iv.s["program"]
                redovne = popuni_jedinice(llm, program, [t for t in teme if t.redni_broj not in
                                                         (RB_INICIJALNI, RB_PISMENI)], iv.s.get("udzbenik", ""))
                casovi, nije_stalo = rasporedi(redovne, iv.s.slotovi(), program,
                                               kraj_polugodista=iv.s["kalendar"].kraj_prvog_polugodista)
                po_rb = {t.redni_broj: t for t in redovne}
                teme = [po_rb.get(t.redni_broj, t) for t in teme]
        ss.plan = {"teme": teme, "casovi": podrazumevano_operativno(casovi, teme), "nije_stalo": nije_stalo}

# ---------------------------------------------------------------- gotov plan
program = iv.s["program"]
pismo = iv.s.get("pismo", "latinica")
teme, casovi = ss.plan["teme"], ss.plan["casovi"]
gp = globalni_plan(casovi, teme)
P = lambda v: preslovi(v, pismo) if isinstance(v, str) else v  # noqa: E731
godina = iv.s["skolska_godina"]
skolska = f"{godina}/{str(godina + 1)[2:]}"

naslov = f"{program.predmet} · {program.razred}. razred"
podnaslov = (f"{program.smer} · " if program.smer else "") + f"školska {skolska} · {gp['ukupno']} časova"
st.markdown(f'<div class="np-naslov">{html.escape(P(naslov))}</div>'
            f'<div class="np-sitno">{html.escape(P(podnaslov))}</div>', unsafe_allow_html=True)
st.write("")
provere = iv.provera(casovi)
napomena = sum(r[0] != "ok" for r in provere)
t_god, t_mes, t_pro = st.tabs(["Godišnji plan", "Mesečni plan", "Provera" + (f" · {napomena}" if napomena else " ✓")])

with t_god:
    meseci = list(gp["meseci"])
    redovi = [[r["rb"] if 0 < r["rb"] < RB_PISMENI else "", P(r["tema"])]
              + [r["po_mesecu"][x] for x in meseci] + [r["ukupno"]] for r in gp["redovi"]]
    redovi.append(["", P("Ukupno")] + [gp["ukupno_po_mesecu"][x] for x in meseci] + [gp["ukupno"]])
    tabela(["", "Tema"] + [RIMSKI.get(m, str(m)) for _, m in meseci] + ["Σ"], redovi,
           ["br", "tema"] + ["br"] * len(meseci) + ["br"], zbir_poslednji=True)
    nap = iv.napomena_rezerve()
    if nap:
        st.caption(nap)
    c1, c2 = st.columns(2)
    c1.download_button("Godišnji plan · Word",
                       globalni_docx(program, gp, ss.nastavnik, ss.skola, pismo, nap, ss.odeljenje, skolska),
                       file_name=f"godisnji_plan_{program.razred}_razred.docx")
    c2.download_button("Ceo plan · Excel", plan_xlsx(program, gp, casovi, pismo),
                       file_name=f"plan_{program.razred}_razred.xlsx")

with t_mes:
    izbor = st.selectbox("Mesec", meseci_u_godini(casovi), format_func=lambda x: f"{MESECI[x[1]]} {x[0]}",
                         label_visibility="collapsed")
    mesecni = operativni_plan(casovi, *izbor)
    tabela(["Čas", "Datum", "Nastavna jedinica", "Tip"],
           [[c.redni_broj, c.datum.strftime("%d.%m."), P(c.jedinica), P(c.tip)] for c in mesecni],
           ["br", "br", "", ""])
    c1, c2 = st.columns(2)
    c1.download_button(f"{MESECI[izbor[1]]} · Word",
                       operativni_docx(program, mesecni, izbor[1], ss.nastavnik, ss.skola, pismo, ss.odeljenje,
                                       iv.s.get("zelje", ""), ss.sa_datumima),
                       file_name=f"mesecni_plan_{MESECI[izbor[1]].lower()}.docx")
    if llm and c2.button("Dopuni ishode i metode (AI)"):
        with st.spinner("Popunjavam…"):
            obog = {c.redni_broj: c for c in obogati_operativni(llm, program, mesecni, teme, iv.s.get("zelje", ""))}
        ss.plan["casovi"] = [obog.get(c.redni_broj, c) for c in casovi]
        st.rerun()

with t_pro:
    lista_provera(provere)
