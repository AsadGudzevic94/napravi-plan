"""Streamlit aplikacija: razgovor sa nastavnikom → globalni i operativni plan.

Pokretanje:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from planer.ekstrakcija import izvuci_program, nedeljni_fond_iz_teksta, pronadji_odeljak, stranice_iz_pdf
from planer.glasnik_parser import blokovi_iz_docx, naslov_izvora, parsiraj_blokove
from planer.intervju import Intervju
from planer.izvoz import globalni_docx, operativni_docx, plan_xlsx
from planer.llm import LLM, LLMGreska
from planer.modeli import MESECI
from planer.raspodela import RB_INICIJALNI, RB_PISMENI, globalni_plan, meseci_u_godini, operativni_plan, rasporedi
from planer.sadrzaj import obogati_operativni, podrazumevano_operativno, popuni_jedinice

st.set_page_config(page_title="Napravi plan", page_icon="📘", layout="wide")


@st.cache_resource
def llm_klijent() -> LLM | None:
    return LLM.iz_okruzenja()


llm = llm_klijent()
ss = st.session_state
if "iv" not in ss:
    ss.iv = Intervju(llm)
    ss.poruke = []
    ss.plan = None
iv: Intervju = ss.iv


def postavi_pitanje(greska: str | None = None) -> None:
    if greska:
        ss.poruke.append(("assistant", "⚠️ " + greska))
    elif (tekst := iv.pitanje()) is not None:
        ss.poruke.append(("assistant", tekst))


# ---------------------------------------------------------------- bočna traka
with st.sidebar:
    st.header("📘 Napravi plan")
    if llm:
        st.success(f"LLM: {llm.provider} · {llm.model}")
    else:
        st.warning("LLM nije podešen — plan radi, ali sa generičkim nazivima jedinica i bez čitanja PDF-a. "
                   "Dodajte besplatan ključ u `.env` (vidi README).")
    ss.skola = st.text_input("Škola", ss.get("skola", ""))
    ss.nastavnik = st.text_input("Nastavnik", ss.get("nastavnik", ""))
    if st.button("🔄 Novi plan"):
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()

if not ss.poruke:
    postavi_pitanje()

# ---------------------------------------------------------------- razgovor
for uloga, tekst in ss.poruke:
    with st.chat_message(uloga):
        st.markdown(tekst)

p = iv.trenutno()
if p and p.kljuc == "program":
    pdf = st.file_uploader("Službeni / prosvetni glasnik (DOCX ili PDF)", type=["docx", "pdf"])
    if pdf is not None and ss.get("pdf_ime") != pdf.name and pdf.name.lower().endswith(".docx"):
        ss.pdf_ime = pdf.name
        with st.spinner("Čitam glasnik (bez LLM-a)…"):
            blokovi = blokovi_iz_docx(pdf.getvalue())
            greska = iv.postavi_glasnik(parsiraj_blokove(blokovi), naslov_izvora(blokovi) or pdf.name)
        ss.poruke.append(("user", f"📎 {pdf.name}"))
        postavi_pitanje(greska)
        st.rerun()
    if pdf is not None and ss.get("pdf_ime") != pdf.name:
        ss.pdf_ime = pdf.name
        with st.spinner("Čitam glasnik…"):
            stranice = stranice_iz_pdf(pdf.getvalue())
            odeljak = pronadji_odeljak(stranice, iv.s["predmet"], iv.s["razred"])
        if not odeljak.strip():
            ss.poruke.append(("assistant", "⚠️ PDF nema tekst (verovatno je skeniran). Upišite teme ručno."))
        elif not llm:
            ss.poruke.append(("assistant", "⚠️ Za čitanje PDF-a potreban je LLM ključ. Upišite teme ručno "
                              "ili dodajte ključ u `.env`."))
        else:
            try:
                with st.spinner(f"Izvlačim teme i ishode ({llm.provider})…"):
                    program = izvuci_program(llm, odeljak, iv.s["predmet"], iv.s["razred"], iv.s["tip_skole"],
                                             iv.s.get("smer"))
                if not program.nedeljni_fond:
                    program.nedeljni_fond = nedeljni_fond_iz_teksta(odeljak) or 0
                program.izvor = program.izvor or pdf.name
                ss.poruke.append(("user", f"📎 {pdf.name}"))
                iv.postavi_program(program)
                postavi_pitanje()
            except (LLMGreska, ValueError) as e:
                ss.poruke.append(("assistant", f"⚠️ Nisam uspeo da izvučem program: {e}"))
        st.rerun()

if p:
    if odg := st.chat_input("Vaš odgovor…"):
        ss.poruke.append(("user", odg))
        greska = iv.odgovori(odg)
        postavi_pitanje(greska)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------- plan
if ss.plan is None:
    with st.spinner("Raspoređujem časove po kalendaru…"):
        teme, casovi, nije_stalo = iv.napravi()
    if llm:
        with st.spinner("Pišem nazive nastavnih jedinica…"):
            program = iv.s["program"]
            redovne = [t for t in teme if t.redni_broj not in (RB_INICIJALNI, RB_PISMENI)]
            redovne = popuni_jedinice(llm, program, redovne, iv.s.get("udzbenik", ""))
            casovi, nije_stalo = rasporedi(redovne, iv.s.slotovi(), program,
                                           kraj_polugodista=iv.s["kalendar"].kraj_prvog_polugodista)
            po_rb = {t.redni_broj: t for t in redovne}
            teme = [po_rb.get(t.redni_broj, t) for t in teme]
    casovi = podrazumevano_operativno(casovi, teme)
    ss.plan = {"teme": teme, "casovi": casovi, "nije_stalo": nije_stalo}

program = iv.s["program"]
pismo = iv.s.get("pismo", "latinica")
teme, casovi = ss.plan["teme"], ss.plan["casovi"]
gp = globalni_plan(casovi, teme)

st.header(f"Globalni plan — {program.predmet}, {program.razred}. razred")
if ss.plan["nije_stalo"]:
    st.error(f"{ss.plan['nije_stalo']} časova iz programa nije stalo u kalendar. Kliknite „Novi plan“ i "
             "izaberite proporcionalno usklađivanje.")
df = pd.DataFrame([{"R.b.": r["rb"] if 0 < r["rb"] < 900 else "", "Tema": r["tema"],
                    **{MESECI[m][:3]: r["po_mesecu"][(g, m)] for g, m in gp["meseci"]},
                    "Obrada": r["obrada"], "Utvrđ.": r["utvrdjivanje"], "Ostalo": r["ostalo"],
                    "Ukupno": r["ukupno"]} for r in gp["redovi"]])
st.dataframe(df, hide_index=True, width="stretch")
st.caption(f"Ukupno {gp['ukupno']} časova · " + " · ".join(
    f"{MESECI[m][:3]} {n}" for (g, m), n in gp["ukupno_po_mesecu"].items()))

c1, c2 = st.columns(2)
c1.download_button("⬇️ Globalni plan (.docx)", globalni_docx(program, gp, ss.nastavnik, ss.skola, pismo),
                   file_name=f"globalni_{program.predmet}_{program.razred}.docx")
c2.download_button("⬇️ Ceo plan (.xlsx)", plan_xlsx(program, gp, casovi, pismo),
                   file_name=f"plan_{program.predmet}_{program.razred}.xlsx")

st.header("Operativni (mesečni) plan")
meseci = meseci_u_godini(casovi)
izbor = st.selectbox("Mesec", meseci, format_func=lambda x: f"{MESECI[x[1]]} {x[0]}")
mesecni = operativni_plan(casovi, *izbor)
if llm and st.button("✨ Dopuni ishode, metode, oblike rada i korelaciju"):
    with st.spinner("Popunjavam operativni plan…"):
        obogaceni = {c.redni_broj: c for c in obogati_operativni(llm, program, mesecni, teme, iv.s.get("zelje", ""))}
    ss.plan["casovi"] = [obogaceni.get(c.redni_broj, c) for c in casovi]
    st.rerun()
st.dataframe(pd.DataFrame([{"Č.": c.redni_broj, "Datum": c.datum.strftime("%d.%m."), "Tema": c.tema,
                            "Nastavna jedinica": c.jedinica, "Tip": c.tip, "Ishodi": c.ishodi,
                            "Metode": c.metode, "Oblici rada": c.oblici_rada, "Korelacija": c.korelacija}
                           for c in mesecni]), hide_index=True, width="stretch")
st.download_button(f"⬇️ Operativni plan — {MESECI[izbor[1]]} (.docx)",
                   operativni_docx(program, mesecni, izbor[1], ss.nastavnik, ss.skola, pismo),
                   file_name=f"operativni_{program.predmet}_{MESECI[izbor[1]]}.docx")
