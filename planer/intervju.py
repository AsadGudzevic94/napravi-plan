"""Razgovor sa nastavnikom: kod vodi listu pitanja (ništa se ne preskoči),
a LLM se koristi samo da protumači slobodan odgovor kada ga kod ne razume.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .ekstrakcija import normalizuj
from .kalendar import slotovi_casova
from .llm import LLM, LLMGreska
from .modeli import DANI, Program, Raspust, SkolskiKalendar, Tema
from .podrazumevani_kalendar import kalendar_za
from .raspodela import napravi_plan

DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- parseri odgovora


def _da_ne(t: str) -> bool | None:
    n = normalizuj(t).strip(" .!")
    if n in {"da", "d", "yes", "y", "ok", "moze", "tacno", "potvrdjujem", "jeste", "u redu", "uredu"}:
        return True
    if n in {"ne", "n", "no", "nije"}:
        return False
    return None


def parsiraj_tip(t: str, s: "Stanje") -> str:
    n = normalizuj(t)
    if "osnov" in n or n.strip() == "o":
        return "osnovna"
    if "sredn" in n or n.strip() == "s" or "gimnaz" in n or "strucn" in n:
        return "srednja"
    raise ValueError("Napišite „osnovna“ ili „srednja“.")


def parsiraj_razred(t: str, s: "Stanje") -> int:
    n = normalizuj(t)
    rimski = {"viii": 8, "vii": 7, "vi": 6, "iv": 4, "v": 5, "iii": 3, "ii": 2, "i": 1}
    m = re.search(r"\d+", n)
    r = int(m.group()) if m else next((v for k, v in rimski.items() if re.search(rf"\b{k}\b", n)), None)
    maks = 8 if s.get("tip_skole") == "osnovna" else 4
    if not r or not 1 <= r <= maks:
        raise ValueError(f"Razred mora biti broj od 1 do {maks}.")
    return r


def parsiraj_tekst(t: str, s: "Stanje") -> str:
    t = t.strip()
    if len(t) < 2:
        raise ValueError("Odgovor je prekratak.")
    return t


def parsiraj_opciono(t: str, s: "Stanje") -> str:
    t = t.strip()
    return "" if normalizuj(t) in {"", "-", "ne", "nema", "preskoci", "nista"} else t


def parsiraj_broj(t: str, s: "Stanje") -> float:
    m = re.search(r"\d+(?:[.,]\d+)?", t)
    if not m:
        raise ValueError("Upišite broj.")
    return float(m.group().replace(",", "."))


def parsiraj_ceo(t: str, s: "Stanje") -> int:
    if normalizuj(t).strip() in {"nijedna", "nijednu", "ne", "nema"}:
        return 0
    return int(parsiraj_broj(t, s))


_DANI_NORM = {normalizuj(d)[:3]: i for i, d in enumerate(DANI[:5])}


def parsiraj_raspored(t: str, s: "Stanje") -> dict[int, int]:
    """'pon, čet' | 'ponedeljak 2, sreda 1' | 'pon uto sre čet' → {dan: broj_časova}"""
    n = normalizuj(t)
    raspored: dict[int, int] = {}
    for m in re.finditer(r"(pon|uto|sre|cet|pet)[a-z]*\s*(?:[x×*:-]?\s*(\d))?(?:\s*cas[a-z]*)?", n):
        dan = _DANI_NORM[m.group(1)]
        raspored[dan] = raspored.get(dan, 0) + (int(m.group(2)) if m.group(2) else 1)
    if not raspored:
        raise ValueError("Nisam prepoznao dane. Primer: „ponedeljak i četvrtak“ ili „utorak 2, petak 1“.")
    fond = s.get("nedeljni_fond")
    if fond and sum(raspored.values()) != round(fond):
        raise ValueError(f"Po rasporedu je {sum(raspored.values())} čas(a) nedeljno, a nedeljni fond je "
                         f"{fond:g}. Navedite dane tako da zbir bude {fond:g} (npr. „utorak 2“ za blok čas).")
    return raspored


def parsiraj_godinu(t: str, s: "Stanje") -> int:
    m = re.search(r"(20\d\d)", t)
    if not m:
        raise ValueError("Napišite školsku godinu, npr. 2026/27.")
    return int(m.group(1))


def parsiraj_teme_tekst(t: str) -> list[Tema]:
    """Redovi oblika 'Naziv teme ; 30' ili 'Naziv teme ; 20 ; 10' (obrada ; utvrđivanje)."""
    teme = []
    for red in t.splitlines():
        delovi = [d.strip() for d in re.split(r"[;|\t]", red) if d.strip()]
        if len(delovi) < 2 or not delovi[1].isdigit():
            continue
        o = int(delovi[1])
        u = int(delovi[2]) if len(delovi) > 2 and delovi[2].isdigit() else 0
        teme.append(Tema(redni_broj=len(teme) + 1, naziv=delovi[0], casova_obrada=o, casova_utvrdjivanje=u))
    return teme


def ucitaj_primer() -> Program:
    return Program.model_validate(json.loads((DATA / "program_primer_matematika_5.json").read_text(encoding="utf-8")))


def parsiraj_program(t: str, s: "Stanje") -> Program:
    if normalizuj(t).strip() in {"primer", "demo"}:
        return ucitaj_primer()
    teme = parsiraj_teme_tekst(t)
    if not teme:
        raise ValueError("Pošaljite PDF glasnika, napišite „primer“, ili upišite teme, svaku u novom redu:\n"
                         "`Naziv teme ; broj časova obrade ; broj časova utvrđivanja`")
    return Program(predmet=s.get("predmet", ""), razred=s.get("razred", 1),
                   tip_skole=s.get("tip_skole", "osnovna"), smer=s.get("smer") or None,
                   nedeljni_fond=0, izvor="ručni unos", teme=teme)


def parsiraj_potvrdu_programa(t: str, s: "Stanje") -> bool:
    """'da' | '3 ; 25' (tema 3 ima 25 časova) | '3 ; 20 ; 5' | 'redosled 2,1,3' | 'obriši 4'"""
    if _da_ne(t) is True:
        return True
    p: Program = s["program"]
    n = normalizuj(t)
    izmenjeno = False
    if m := re.search(r"redosled\D*([\d,\s]+)", n):
        red = [int(x) for x in re.findall(r"\d+", m.group(1))]
        po_rb = {tm.redni_broj: tm for tm in p.teme}
        if sorted(red) != sorted(po_rb):
            raise ValueError(f"Redosled mora sadržati sve teme: {sorted(po_rb)}.")
        p.teme = [po_rb[i].model_copy(update={"redni_broj": k + 1}) for k, i in enumerate(red)]
        izmenjeno = True
    if m := re.search(r"obrisi\D*(\d+)", n):
        p.teme = [tm for tm in p.teme if tm.redni_broj != int(m.group(1))]
        for k, tm in enumerate(p.teme):
            tm.redni_broj = k + 1
        izmenjeno = True
    for m in re.finditer(r"(?:^|\n)\s*(\d+)\s*[;=:]\s*(\d+)(?:\s*;\s*(\d+))?", t):
        rb, o, u = int(m.group(1)), int(m.group(2)), m.group(3)
        for tm in p.teme:
            if tm.redni_broj == rb:
                if u is None:  # samo ukupno: zadrži odnos obrada/utvrđivanje
                    staro = tm.casova_ukupno or 1
                    tm.casova_utvrdjivanje = round(o * tm.casova_utvrdjivanje / staro)
                    tm.casova_ostalo = round(o * tm.casova_ostalo / staro)
                    tm.casova_obrada = o - tm.casova_utvrdjivanje - tm.casova_ostalo
                else:
                    tm.casova_obrada, tm.casova_utvrdjivanje, tm.casova_ostalo = o, int(u), 0
                tm.jedinice = []
                izmenjeno = True
    if not izmenjeno:
        raise ValueError("Napišite „da“ ako je tačno, ili izmene: `3 ; 25` (tema 3 → 25 časova), "
                         "`3 ; 20 ; 5` (obrada ; utvrđivanje), `redosled 2,1,3,...`, `obriši 4`.")
    p.godisnji_fond = p.ukupno_casova
    return False  # izmenjeno → pitaj ponovo za potvrdu


def parsiraj_kalendar(t: str, s: "Stanje") -> bool:
    """'da' | 'početak 2026-09-01' | 'kraj 2027-06-04' | 'raspust 2027-04-26 2027-05-03' | 'neradni 2026-11-11'"""
    if _da_ne(t) is True:
        return True
    k: SkolskiKalendar = s["kalendar"]
    datumi = lambda x: [date.fromisoformat(d) for d in re.findall(r"\d{4}-\d{2}-\d{2}", x)]  # noqa: E731
    izmenjeno = False
    for red in re.split(r"[\n;]", t):
        n = normalizuj(red)
        d = datumi(red) or [_datum_dmy(x) for x in re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", red)]
        if not d:
            continue
        if "pocet" in n:
            k.pocetak = d[0]
        elif "polugod" in n:
            k.kraj_prvog_polugodista = d[0]
        elif "kraj" in n:
            k.kraj = d[0]
        elif "raspust" in n and len(d) >= 2:
            k.raspusti.append(Raspust(naziv="Raspust (nastavnik)", od=d[0], do=d[1]))
        elif "neradn" in n or "slobod" in n:
            from .modeli import NeradniDan
            k.dodatni_neradni += [NeradniDan(datum=x, naziv="Neradni dan (nastavnik)") for x in d]
        else:
            continue
        izmenjeno = True
    if not izmenjeno:
        raise ValueError("Napišite „da“ ili izmene, npr. `kraj 2027-06-04`, `raspust 2027-04-26 2027-05-03`, "
                         "`neradni 2027-01-27`, `početak 2026-09-01`.")
    s.pop("slotovi", None)
    return False


def _datum_dmy(x: str) -> date:
    d, m, g = (int(v) for v in x.split("."))
    return date(g, m, d)


def parsiraj_strategiju(t: str, s: "Stanje") -> str:
    n = normalizuj(t)
    if "1" in n or "propor" in n or "skrat" in n:
        return "proporcionalno"
    if "2" in n or "bez" in n:
        return "bez_izmena"
    raise ValueError("Odgovorite sa 1 ili 2.")


# ---------------------------------------------------------------- pitanja


@dataclass
class Pitanje:
    kljuc: str
    tekst: Callable[["Stanje"], str]
    parser: Callable[[str, "Stanje"], Any]
    uslov: Callable[["Stanje"], bool] = lambda s: True
    format_za_llm: str = ""  # opis formata kada LLM treba da prevede slobodan odgovor
    potvrda: bool = False  # parser vraća True kad je potvrđeno, False → pitaj opet


def _tekst_programa(s: "Stanje") -> str:
    p: Program = s["program"]
    redovi = [f"{t.redni_broj}. {t.naziv} — {t.casova_ukupno} č. "
              f"(obrada {t.casova_obrada}, utvrđivanje {t.casova_utvrdjivanje}, ostalo {t.casova_ostalo})"
              for t in p.teme]
    upozorenje = ""
    if any(t.casova_ukupno == 0 for t in p.teme):
        upozorenje = "\n⚠️ Neke teme nemaju broj časova — unesite ih (npr. `2 ; 18 ; 6`)."
    return (f"Program: **{p.predmet}**, {p.razred}. razred{', smer ' + p.smer if p.smer else ''} "
            f"({p.izvor or 'izvor nepoznat'})\n\n" + "\n".join(redovi) +
            (f"\n\nPosebni časovi (inicijalni, pismeni): {p.posebnih_casova}" if p.posebnih_casova else "") +
            f"\n\n**Ukupno: {p.ukupno_casova} časova.**{upozorenje}\n\n"
            "Da li je ovo tačno? Napišite „da“, ili izmene: `3 ; 25`, `3 ; 20 ; 5`, `redosled 2,1,3,...`, `obriši 4`.")


def _tekst_kalendara(s: "Stanje") -> str:
    k: SkolskiKalendar = s["kalendar"]
    slotovi = s.slotovi()
    raspusti = "\n".join(f"- {r.naziv}: {r.od:%d.%m.%Y.} – {r.do:%d.%m.%Y.}" for r in k.raspusti)
    dodatni = "\n".join(f"- {d.naziv}: {d.datum:%d.%m.%Y.}" for d in k.dodatni_neradni)
    return (f"**{k.naziv}**\n\n- Početak: {k.pocetak:%d.%m.%Y.}\n- Kraj I polugodišta: "
            f"{k.kraj_prvog_polugodista:%d.%m.%Y.}\n- Kraj nastave: {k.kraj:%d.%m.%Y.}\n{raspusti}\n{dodatni}\n"
            f"- Državni praznici se automatski izuzimaju.\n\n"
            f"Po ovom kalendaru i vašem rasporedu imate **{len(slotovi)} časova** u godini." +
            _poruka_fonda(s) + "\n\n"
            "Da li je kalendar tačan? „da“ ili izmene: `kraj 2027-06-04`, `raspust 2027-04-26 2027-05-03`, "
            "`neradni 2027-01-27`.")


def _poruka_fonda(s: "Stanje") -> str:
    p = s.get("program")
    if not p:
        return ""
    n, g = len(s.slotovi()), p.ukupno_casova
    if n > g:
        return (f" Glasnik propisuje **{g}** — plan će imati tačno **{g}** časova (glasnik ima prednost), a "
                f"preostalih {n - g} ostaju slobodni kao rezerva (nadoknada, ponavljanje) na kraju polugodišta.")
    if n < g:
        return f" To je **manje** od {g} koliko propisuje glasnik — pitaću vas kako da skratim."
    return f" To je tačno koliko propisuje glasnik ({g})."


def _treba_uskladjivanje(s: "Stanje") -> bool:
    """Pitamo samo kad časova u kalendaru ima MANJE nego u glasniku; višak se ne planira."""
    return len(s.slotovi()) < s["program"].ukupno_casova


def _samo_ukupno(s: "Stanje") -> bool:
    p = s.get("program")
    return bool(p) and all(t.casova_utvrdjivanje == 0 and t.casova_ostalo == 0 for t in p.teme) and \
        any(t.casova_obrada > 2 for t in p.teme)


def _tekst_varijanti(s: "Stanje") -> str:
    redovi = "\n".join(f"{i + 1}) {v.naziv()}" for i, v in enumerate(s["kandidati"]))
    return f"U glasniku ima više programa koji odgovaraju. Koji je vaš? Napišite broj.\n\n{redovi}"


def parsiraj_varijantu(t: str, s: "Stanje"):
    k = s["kandidati"]
    m = re.search(r"\d+", t)
    if not m or not 1 <= int(m.group()) <= len(k):
        raise ValueError(f"Napišite broj od 1 do {len(k)}.")
    return k[int(m.group()) - 1]


def _tekst_pismenih(s: "Stanje") -> str:
    p: Program = s["program"]
    delovi = []
    if p.inicijalni_casova:
        delovi.append(f"- inicijalni test i analiza: **{p.inicijalni_casova}** časa, na početku godine")
    if p.pismeni_broj:
        delovi.append(f"- **{p.pismeni_broj}** pismena zadatka po **{p.pismeni_trajanje}** časa"
                      + (" + ispravka (1 čas)" if p.pismeni_ispravka else "")
                      + f" = **{p.pismeni_broj * (p.pismeni_trajanje + p.pismeni_ispravka)}** časova, ravnomerno kroz godinu")
    return ("Glasnik predviđa i časove van tema:\n" + "\n".join(delovi) +
            "\n\nDa li je tako? „da“, ili izmene: `pismeni 2`, `trajanje 1`, `inicijalni 0`, `bez ispravke`.")


def parsiraj_pismene(t: str, s: "Stanje") -> bool:
    if _da_ne(t) is True:
        return True
    p: Program = s["program"]
    n = normalizuj(t)
    izm = False
    if m := re.search(r"pismen\D*(\d+)", n):
        p.pismeni_broj, izm = int(m.group(1)), True
    if m := re.search(r"trajanj\D*(\d+)", n):
        p.pismeni_trajanje, izm = max(1, int(m.group(1))), True
    if m := re.search(r"inicijal\D*(\d+)", n):
        p.inicijalni_casova, izm = int(m.group(1)), True
    if "bez ispravk" in n:
        p.pismeni_ispravka, izm = False, True
    if not izm:
        raise ValueError("Napišite „da“ ili izmene, npr. `pismeni 2`, `trajanje 1`, `inicijalni 0`, `bez ispravke`.")
    return False


def parsiraj_procenat(t: str, s: "Stanje") -> float:
    v = parsiraj_broj(t, s)
    v = v * 100 if v <= 1 else v
    if not 10 <= v <= 90:
        raise ValueError("Napišite procenat između 10 i 90.")
    return v / 100


def parsiraj_listu(t: str, s: "Stanje") -> list[str]:
    if normalizuj(t).strip(" .") in {"", "-", "ne", "nema", "ne znam", "preskoci"}:
        return []
    return [x.strip(" .") for x in re.split(r"[,;\n]", t) if x.strip(" .")]


def _analiziraj(s: "Stanje") -> None:
    from .kompetencije import analiziraj_program
    if not s.get("analizirano"):
        s["program"] = analiziraj_program(s["program"], s.get("predmeti_odeljenja") or None,
                                          s.get("strucni_predmeti") or [])
        s["analizirano"] = True


def _tekst_kompetencija(s: "Stanje") -> str:
    _analiziraj(s)
    p: Program = s["program"]
    delovi = []
    for t in p.teme:
        obr = "\n".join(f"   · {o}" for o in t.obrazlozenje[:8])
        delovi.append(f"**{t.redni_broj}. {t.naziv}**\n- MK: {', '.join(t.kompetencije)}\n"
                      f"- Povezivanje: {', '.join(t.korelacija) or '—'}\n{obr}")
    return ("Analizirao sam glasnik i sadržaje tema. Predlog **međupredmetnih kompetencija** i **predmeta za "
            "povezivanje** (uz izvor: glasnik / ishod / logika):\n\n" + "\n\n".join(delovi) +
            "\n\nDa li je tako? „da“, ili izmene: `4: Fizika, Saobraćajna tehnika` (povezivanje za temu 4), "
            "`dodaj 3: Fizika`, `mk 2: komunikacija, saradnja`, `bez 3: Hemija`.")


def parsiraj_kompetencije(t: str, s: "Stanje") -> bool:
    if _da_ne(t) is True:
        return True
    p: Program = s["program"]
    po_rb = {tm.redni_broj: tm for tm in p.teme}
    izm = False
    for red in t.splitlines():
        n = normalizuj(red)
        m = re.match(r"\s*(mk|bez|dodaj)?\s*(\d+)\s*[:=]\s*(.+)", red, re.I)
        if not m or int(m.group(2)) not in po_rb:
            continue
        tm = po_rb[int(m.group(2))]
        lista = [x.strip(" .") for x in re.split(r"[,;]", m.group(3)) if x.strip(" .")]
        vrsta = (m.group(1) or "").lower()
        if vrsta == "mk":
            tm.kompetencije = lista
        elif vrsta == "dodaj":
            tm.korelacija += [x for x in lista if normalizuj(x) not in {normalizuj(k) for k in tm.korelacija}]
        elif vrsta == "bez" or n.startswith("bez"):
            tm.korelacija = [k for k in tm.korelacija if normalizuj(k) not in {normalizuj(x) for x in lista}]
        else:
            tm.korelacija = lista
        tm.obrazlozenje.append("izmenio nastavnik")
        izm = True
    if not izm:
        raise ValueError("Napišite „da“ ili izmene, npr. `4: Fizika, Saobraćajna tehnika`, "
                         "`dodaj 3: Fizika`, `mk 2: komunikacija, saradnja`, `bez 3: Hemija`.")
    return False


def parsiraj_pismo(t: str, s: "Stanje") -> str:
    n = normalizuj(t)
    if n.startswith("c") or "cir" in n:
        return "ćirilica"
    if n.startswith("l") or "lat" in n:
        return "latinica"
    raise ValueError("Napišite „ćirilica“ ili „latinica“.")


PITANJA: list[Pitanje] = [
    Pitanje("tip_skole", lambda s: "Zdravo! Pravimo globalni i operativni plan. Da li je u pitanju "
            "**osnovna** ili **srednja** škola?", parsiraj_tip, format_za_llm="'osnovna' ili 'srednja'"),
    Pitanje("razred", lambda s: "Koji **razred**?", parsiraj_razred, format_za_llm="ceo broj razreda"),
    Pitanje("predmet", lambda s: "Koji **predmet**?", parsiraj_tekst),
    Pitanje("smer", lambda s: "Koji je **smer / obrazovni profil** (npr. opšti smer gimnazije, "
            "elektrotehničar računara)?", parsiraj_tekst, uslov=lambda s: s.get("tip_skole") == "srednja"),
    Pitanje("trajanje_srednje", lambda s: "Koliko godina traje taj smer (3 ili 4)?", parsiraj_ceo,
            uslov=lambda s: s.get("tip_skole") == "srednja", format_za_llm="broj 3 ili 4"),
    Pitanje("nedeljni_fond", lambda s: "Koliko časova **nedeljno** ima predmet u ovom odeljenju?",
            parsiraj_broj, format_za_llm="broj časova nedeljno"),
    Pitanje("varijanta", _tekst_varijanti, parsiraj_varijantu,
            uslov=lambda s: bool(s.get("kandidati")) and "program" not in s.podaci),
    Pitanje("program", lambda s: "Pošaljite **službeni glasnik** sa programom — **DOCX** (najbolje, čita se "
            "odmah i bez LLM-a, npr. sa paragraf.rs) ili PDF (dugme ispod), "
            "ili napišite **primer** za probu, ili upišite teme ručno, svaku u svom redu:\n"
            "`Naziv teme ; časova obrade ; časova utvrđivanja`", parsiraj_program),
    Pitanje("program_ok", _tekst_programa, parsiraj_potvrdu_programa, potvrda=True),
    Pitanje("udeo_obrade", lambda s: "Glasnik daje samo **ukupan** broj časova po temi. Koliki deo časova da "
            "bude **obrada** novog gradiva, a ostatak utvrđivanje i vežbanje? Napišite procenat (npr. **40** → "
            "40% obrada, 60% utvrđivanje).", parsiraj_procenat, uslov=_samo_ukupno,
            format_za_llm="procenat obrade, ceo broj 10-90"),
    Pitanje("pismeni_ok", _tekst_pismenih, parsiraj_pismene, potvrda=True,
            uslov=lambda s: "program" in s.podaci and (s["program"].pismeni_broj or s["program"].inicijalni_casova)),
    Pitanje("raspored", lambda s: "Kojim **danima** držite ovaj čas u ovom odeljenju? "
            "(npr. „ponedeljak i četvrtak“, ili „utorak 2, petak 1“ za blok čas)"
            + (" — pismeni zadaci traju 2 časa, pa je važno da navedete blok čas ako ga imate."
               if s.get("program") and s["program"].pismeni_trajanje > 1 else ""), parsiraj_raspored,
            format_za_llm="dani skraćeno sa brojem časova, npr. 'pon 1, cet 2'"),
    Pitanje("skolska_godina", lambda s: f"Za koju **školsku godinu**? (npr. {date.today().year if date.today().month >= 7 else date.today().year - 1}/"
            f"{str((date.today().year if date.today().month >= 7 else date.today().year - 1) + 1)[2:]})",
            parsiraj_godinu, format_za_llm="početna godina, npr. 2026"),
    Pitanje("kalendar_ok", _tekst_kalendara, parsiraj_kalendar, potvrda=True),
    Pitanje("strategija", lambda s: f"Po kalendaru imate samo **{len(s.slotovi())}** časova, a glasnik propisuje "
            f"**{s['program'].ukupno_casova}**. Šta da uradim?\n\n1) **proporcionalno** skratim svaku temu\n"
            "2) **bez izmena** — zadržim broj časova iz glasnika, a časovi koji ne stanu ostaju na kraju kao "
            "neodržani (za nadoknadu)",
            parsiraj_strategiju, uslov=_treba_uskladjivanje, format_za_llm="1 ili 2"),
    Pitanje("broj_provera", lambda s: ("Koliko **kontrolnih provera** (pored pismenih zadataka) planirate? "
            if s["program"].pismeni_broj else "Koliko **pismenih / kontrolnih provera** planirate tokom godine? ")
            + "(0 ako ih nema; raspodeliću ih ravnomerno po temama)", parsiraj_ceo,
            format_za_llm="ceo broj"),
    Pitanje("udzbenik", lambda s: "Koji **udžbenik** (izdavač/autor) koristite? (ili „-“ za preskakanje)",
            parsiraj_opciono),
    Pitanje("zelje", lambda s: "Imate li želje za **metode i oblike rada** ili korelaciju sa drugim "
            "predmetima? (ili „-“)", parsiraj_opciono),
    Pitanje("strucni_predmeti", lambda s: "Koje **stručne predmete** imaju učenici ovog odeljenja ove godine? "
            "Treba mi za međupredmetno povezivanje (npr. „Saobraćajna tehnika, Bezbednost saobraćaja“), "
            "ili „-“.", parsiraj_listu,
            uslov=lambda s: s.get("tip_skole") == "srednja" and "gimnaz" not in normalizuj(s.get("smer") or "")),
    Pitanje("predmeti_odeljenja", lambda s: "Koje **opšteobrazovne predmete** učenici imaju ove godine (pored "
            "vašeg)? Iz glasnika ne može uvek da se zna koje predmete ima baš vaš profil. Napišite ih zarezom "
            "(npr. „Fizika, Hemija, Računarstvo i informatika“), ili „-“ ako nisu poznati (tada ih predlažem "
            "logički, a vi potvrdite u sledećem koraku).", parsiraj_listu),
    Pitanje("kompetencije_ok", lambda s: _tekst_kompetencija(s), parsiraj_kompetencije, potvrda=True),
    Pitanje("pismo", lambda s: "Na kom **pismu** da napravim plan — **ćirilica** ili **latinica**?",
            parsiraj_pismo, format_za_llm="'ćirilica' ili 'latinica'"),
]


# ---------------------------------------------------------------- stanje i tok


@dataclass
class Stanje:
    podaci: dict = field(default_factory=dict)

    def get(self, k, d=None):
        return self.podaci.get(k, d)

    def __getitem__(self, k):
        return self.podaci[k]

    def __setitem__(self, k, v):
        self.podaci[k] = v

    def pop(self, k, d=None):
        return self.podaci.pop(k, d)

    def slotovi(self):
        if "slotovi" not in self.podaci:
            self.podaci["slotovi"] = slotovi_casova(self["kalendar"], self["raspored"])
        return self.podaci["slotovi"]


class Intervju:
    def __init__(self, llm: LLM | None = None):
        self.llm = llm
        self.s = Stanje()
        self.zavrseno: set[str] = set()

    # --- tok
    def trenutno(self) -> Pitanje | None:
        for p in PITANJA:
            if p.kljuc not in self.zavrseno and p.uslov(self.s):
                return p
        return None

    def pitanje(self) -> str | None:
        p = self.trenutno()
        if p is None:
            return None
        return p.tekst(self.s)

    def odgovori(self, tekst: str) -> str | None:
        """Obradi odgovor. Vraća poruku o grešci (pa se isto pitanje ponavlja) ili None."""
        p = self.trenutno()
        if p is None:
            return None
        try:
            vrednost = self._parsiraj(p, tekst)
        except ValueError as e:
            return str(e)
        if p.potvrda:
            if vrednost:
                self.zavrseno.add(p.kljuc)
            return None
        if p.kljuc == "varijanta":
            self.zavrseno.add(p.kljuc)
            self._postavi_varijantu(vrednost)
            return None
        self.s[p.kljuc] = vrednost
        self.zavrseno.add(p.kljuc)
        self._posle(p.kljuc)
        return None

    def postavi_glasnik(self, varijante: list, izvor: str = "") -> str | None:
        """Aplikacija prosleđuje programe pročitane iz DOCX glasnika. Vraća poruku ako nema poklapanja."""
        from .glasnik_parser import izaberi
        kand = izaberi(varijante, self.s["predmet"], self.s["razred"], self.s.get("nedeljni_fond"),
                       self.s.get("trajanje_srednje"))
        if not kand:
            return (f"U glasniku nisam našao predmet „{self.s['predmet']}“ za {self.s['razred']}. razred. "
                    "Proverite naziv predmeta ili pošaljite drugi glasnik.")
        self.s["izvor"] = izvor
        if len(kand) == 1:
            self._postavi_varijantu(kand[0])
        else:
            self.s["kandidati"] = kand
        return None

    def _postavi_varijantu(self, v) -> None:
        from .glasnik_parser import u_program
        self.postavi_program(u_program(v, self.s.get("smer"), self.s.get("izvor", ""), self.s.get("tip_skole")))

    def postavi_program(self, program: Program) -> None:
        """Koristi aplikacija kada je program izvučen iz PDF-a."""
        self.s["program"] = program
        self.zavrseno.add("program")
        self._posle("program")

    # --- interno
    def _parsiraj(self, p: Pitanje, tekst: str):
        try:
            return p.parser(tekst, self.s)
        except ValueError:
            if not (self.llm and p.format_za_llm):
                raise
            try:
                odg = self.llm.chat_json(
                    "Prevedi odgovor nastavnika u traženi format. Vrati JSON {\"vrednost\": \"...\"}. "
                    "Ako odgovor nema traženu informaciju, vrati {\"vrednost\": null}.",
                    f"Pitanje: {p.tekst(self.s)}\nTraženi format: {p.format_za_llm}\nOdgovor: {tekst}",
                    max_tokena=100)
            except LLMGreska:
                raise ValueError("Nisam razumeo odgovor, pokušajte ponovo.") from None
            if odg.get("vrednost") in (None, ""):
                raise
            return p.parser(str(odg["vrednost"]), self.s)

    def _posle(self, kljuc: str) -> None:
        if kljuc == "program":
            p: Program = self.s["program"]
            p.tip_skole = self.s.get("tip_skole", p.tip_skole)
            p.razred = self.s.get("razred", p.razred)
            p.predmet = p.predmet or self.s.get("predmet", "")
            p.smer = p.smer or self.s.get("smer")
            if self.s.get("nedeljni_fond"):
                p.nedeljni_fond = self.s["nedeljni_fond"]
        if kljuc == "raspored":
            self.s.pop("slotovi")
        if kljuc == "skolska_godina":
            self._napravi_kalendar()

    def _napravi_kalendar(self) -> None:
        self.s["kalendar"] = kalendar_za(self.s["skolska_godina"], self.s["tip_skole"], self.s["razred"],
                                         trajanje_srednje=self.s.get("trajanje_srednje", 4) or 4)
        self.s.pop("slotovi")

    def provera(self, casovi) -> list[tuple[str, str]]:
        from .provera import proveri_plan
        return proveri_plan(self.s["program"], casovi, self.s["kalendar"], len(self.s.slotovi()))

    def napomena_rezerve(self) -> str:
        """Tekst za globalni plan: koji datumi iz kalendara ostaju slobodni (glasnik ima prednost)."""
        from .raspodela import slotovi_po_glasniku
        if self.s.get("strategija", "glasnik") != "glasnik":
            return ""
        _, slobodni = slotovi_po_glasniku(self.s.slotovi(), self.s["program"].ukupno_casova,
                                          self.s["kalendar"].kraj_prvog_polugodista)
        if not slobodni:
            return ""
        return (f"Napomena: plan sadrži {self.s['program'].ukupno_casova} časova, koliko propisuje glasnik. "
                f"Po kalendaru ima još {len(slobodni)} časova koji nisu planirani (rezerva za nadoknadu i "
                "ponavljanje): " + ", ".join(
                    d.strftime("%d.%m.") + (f" ({n} časa)" if n > 1 else "")
                    for d, n in Counter(slobodni).items()))

    def napravi(self):
        """Posle intervjua: (teme, časovi, broj časova koji nisu stali)."""
        return napravi_plan(self.s["program"], self.s.slotovi(),
                            strategija=self.s.get("strategija", "glasnik"),
                            broj_provera=self.s.get("broj_provera", 0),
                            udeo_obrade=self.s.get("udeo_obrade"),
                            kraj_polugodista=self.s["kalendar"].kraj_prvog_polugodista)
