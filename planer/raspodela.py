"""Raspodela tema po časovima i mesecima — čista matematika, bez LLM-a."""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from datetime import date
from typing import Literal

from .modeli import MESECI, Cas, NastavnaJedinica, Program, Tema

Strategija = Literal["glasnik", "proporcionalno", "rezerva", "bez_izmena"]


def slotovi_po_glasniku(slotovi: list[date], potrebno: int,
                        kraj_polugodista: date | None = None) -> tuple[list[date], list[date]]:
    """Glasnik ima prednost: od svih časova iz kalendara planira se tačno `potrebno`.
    Višak ostaje slobodan (rezerva za nadoknadu/ponavljanje), na kraju svakog polugodišta
    srazmerno njegovoj dužini. Vraća (planirani, slobodni)."""
    visak = len(slotovi) - potrebno
    if visak <= 0:
        return list(slotovi), []
    if kraj_polugodista:
        prvo = [d for d in slotovi if d <= kraj_polugodista]
        drugo = [d for d in slotovi if d > kraj_polugodista]
    else:
        prvo, drugo = [], list(slotovi)
    v1, v2 = _najveci_ostatak([float(len(prvo)), float(len(drugo))], visak) if prvo and drugo else (0, visak)
    planirani = prvo[:len(prvo) - v1] + drugo[:len(drugo) - v2]
    slobodni = prvo[len(prvo) - v1:] + drugo[len(drugo) - v2:]
    return planirani, slobodni


def _najveci_ostatak(tezine: list[float], ukupno: int, minimum: int = 0) -> list[int]:
    """Podeli `ukupno` celih jedinica proporcionalno težinama (metoda najvećeg ostatka)."""
    n = len(tezine)
    if n == 0:
        return []
    baza = [minimum] * n
    ostaje = ukupno - minimum * n
    if ostaje < 0:
        raise ValueError("Premalo časova za minimum po temi.")
    if sum(tezine) <= 0:
        tezine = [1.0] * n
    zbir = sum(tezine)
    tacno = [ostaje * t / zbir for t in tezine]
    celi = [math.floor(x) for x in tacno]
    visak = ostaje - sum(celi)
    redosled = sorted(range(n), key=lambda i: tacno[i] - celi[i], reverse=True)
    for i in redosled[:visak]:
        celi[i] += 1
    return [b + c for b, c in zip(baza, celi)]


def _podeli_temu(t: Tema, novo_ukupno: int) -> Tema:
    """Promeni ukupan broj časova teme, čuvajući odnos obrada/utvrđivanje/ostalo."""
    delovi = [t.casova_obrada, t.casova_utvrdjivanje, t.casova_ostalo]
    if sum(delovi) == 0:
        delovi = [1, 0, 0]
    o, u, r = _najveci_ostatak([float(x) for x in delovi], novo_ukupno)
    if o == 0 and novo_ukupno > 0:  # svaka tema mora imati bar jednu obradu
        if u > 0:
            u -= 1
        else:
            r -= 1
        o = 1
    return t.model_copy(update={"casova_obrada": o, "casova_utvrdjivanje": u,
                                "casova_ostalo": r, "jedinice": []}, deep=True)


def uskladi_fond(teme: list[Tema], broj_slotova: int, strategija: Strategija) -> list[Tema]:
    """Uskladi zbir časova tema sa stvarnim brojem časova iz kalendara."""
    teme = [t.model_copy(deep=True) for t in teme]
    potrebno = sum(t.casova_ukupno for t in teme)
    if strategija == "bez_izmena" or potrebno == broj_slotova:
        return teme
    if strategija == "rezerva" and broj_slotova > potrebno:
        teme.append(Tema(
            redni_broj=max((t.redni_broj for t in teme), default=0) + 1,
            naziv="Sistematizacija i rezerva",
            casova_ostalo=broj_slotova - potrebno,
        ))
        return teme
    # proporcionalno (i "rezerva" kada časova nedostaje)
    nova = _najveci_ostatak([float(t.casova_ukupno) for t in teme], broj_slotova,
                            minimum=1 if broj_slotova >= len(teme) else 0)
    return [_podeli_temu(t, n) for t, n in zip(teme, nova)]


def postavi_provere(teme: list[Tema], broj_provera: int) -> list[Tema]:
    """Pretvori po jedan čas utvrđivanja u proveru znanja u `broj_provera` ravnomerno raspoređenih tema."""
    teme = [t.model_copy(deep=True) for t in teme]
    kandidati = [t for t in teme if (t.casova_utvrdjivanje > 0 or t.casova_obrada > 1)
                 and "sistematizacij" not in t.naziv.lower()]
    if broj_provera <= 0 or not kandidati:
        return teme
    broj_provera = min(broj_provera, len(kandidati))
    korak = len(kandidati) / broj_provera
    izabrane = {kandidati[min(len(kandidati) - 1, math.floor((i + 1) * korak) - 1)].redni_broj
                for i in range(broj_provera)}
    for t in teme:
        if t.redni_broj in izabrane:
            if t.casova_utvrdjivanje > 0:
                t.casova_utvrdjivanje -= 1
            else:
                t.casova_obrada -= 1
            t.casova_ostalo += 1
            t.jedinice = []
    return teme


def stavke_sadrzaja(sadrzaji: list[str]) -> list[str]:
    """'Појам корена. Операције са коренима.' → ['Појам корена', 'Операције са коренима']"""
    out = []
    for s in sadrzaji:
        for deo in re.split(r"(?<=[.;])\s+", s.strip()):
            deo = deo.strip().rstrip(".;").strip()
            if len(deo) > 2:
                out.append(deo)
    return out


def _sekvenca_po_sadrzajima(stavke: list[str], o: int, u: int) -> list[NastavnaJedinica]:
    """Bez LLM-a: nazivi jedinica iz sadržaja programa. Svaka stavka dobija bar jedan čas obrade
    (ako ima mesta), a utvrđivanje ide odmah posle obrade te stavke."""
    if o < len(stavke):  # premalo časova → spoji susedne stavke
        velicine = _najveci_ostatak([1.0] * o, len(stavke))
        spojene, k = [], 0
        for v in velicine:
            spojene.append("; ".join(stavke[k:k + v]))
            k += v
        stavke = spojene
    obrade = _najveci_ostatak([1.0] * len(stavke), o)
    utvrde = _najveci_ostatak([float(x) for x in obrade], u) if u else [0] * len(stavke)
    niz: list[NastavnaJedinica] = []
    stavke = [s[:1].upper() + s[1:] for s in stavke]
    for st, no, nu in zip(stavke, obrade, utvrde):
        for i in range(no):
            niz.append(NastavnaJedinica(naziv=st if i == 0 else f"{st} (наставак)" if _cir(st) else f"{st} (nastavak)",
                                        tip="obrada"))
        for i in range(nu):
            pref = (UTVRDJIVANJE_CIR if _cir(st) else UTVRDJIVANJE_LAT)[min(i, 2)]
            niz.append(NastavnaJedinica(naziv=pref + st, tip="utvrđivanje"))
    return niz


UTVRDJIVANJE_CIR = ("Утврђивање: ", "Вежбање: ", "Решавање задатака: ")
UTVRDJIVANJE_LAT = ("Utvrđivanje: ", "Vežbanje: ", "Rešavanje zadataka: ")


def _cir(t: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in t)


def podeli_obradu_utvrdjivanje(teme: list[Tema], udeo_obrade: float) -> list[Tema]:
    """Za teme gde glasnik daje samo ukupan broj časova: podeli na obradu i utvrđivanje."""
    nove = []
    for t in teme:
        t = t.model_copy(deep=True)
        if t.casova_utvrdjivanje == 0 and t.casova_obrada > 1:
            ukupno = t.casova_obrada
            t.casova_obrada = max(1, round(ukupno * udeo_obrade))
            t.casova_utvrdjivanje = ukupno - t.casova_obrada
            t.jedinice = []
        nove.append(t)
    return nove


def sekvenca_jedinica(t: Tema) -> list[NastavnaJedinica]:
    """Redosled časova u temi. Koristi jedinice ako postoje, inače generiše šablon."""
    if t.jedinice and len(t.jedinice) == t.casova_ukupno:
        return list(t.jedinice)
    o, u, r = t.casova_obrada, t.casova_utvrdjivanje, t.casova_ostalo
    niz: list[NastavnaJedinica] = []
    stavke = stavke_sadrzaja(t.sadrzaji)
    if stavke and o:
        niz = _sekvenca_po_sadrzajima(stavke, o, u)
    else:
        # utvrđivanje ravnomerno umetnuto posle grupa obrade
        grupa = math.ceil(o / u) if u else o + 1
        ui = 0
        for i in range(1, o + 1):
            niz.append(NastavnaJedinica(naziv=f"{t.naziv} – obrada ({i}/{o})", tip="obrada"))
            if u and i % grupa == 0 and ui < u:
                ui += 1
                niz.append(NastavnaJedinica(naziv=f"{t.naziv} – utvrđivanje ({ui}/{u})", tip="utvrđivanje"))
        while ui < u:
            ui += 1
            niz.append(NastavnaJedinica(naziv=f"{t.naziv} – utvrđivanje ({ui}/{u})", tip="utvrđivanje"))
    if t.naziv == "Sistematizacija i rezerva":
        niz += [NastavnaJedinica(naziv="Sistematizacija / rezervni čas", tip="rezerva") for _ in range(r)]
    else:
        for i in range(r):
            poslednji = i == r - 1
            niz.append(NastavnaJedinica(
                naziv=f"{t.naziv} – {'provera znanja' if poslednji else 'sistematizacija'}",
                tip="provera" if poslednji else "sistematizacija"))
    return niz


def _ciljevi_pismenih(n: int, slotovi: list[date], kraj_pol: date | None, pre: int, po_pismenom: int,
                     L: int) -> list[int]:
    """Indeksi redovnih časova posle kojih ide pismeni: podjednako po polugodištima
    (npr. 2 + 2), u svakom na ~35% i ~72% polugodišta, da ispravka stigne pre raspusta."""
    if not n:
        return []
    S = len(slotovi)
    if kraj_pol and slotovi:
        S1 = sum(1 for d in slotovi if d <= kraj_pol)
        delovi = [(0, S1, n // 2), (S1, S, n - n // 2)] if S1 and S1 < S else [(0, S, n)]
    else:
        delovi = [(0, S, n)]
    ciljevi, k = [], 0
    for od, do, m in delovi:
        for j in range(m):
            udeo = 0.7 if m == 1 else 0.35 + 0.37 * j / (m - 1)
            slot = od + (do - od) * udeo
            ciljevi.append(max(0, min(L, round(slot - pre - k * po_pismenom))))
            k += 1
    return ciljevi


RB_INICIJALNI = 0
RB_PISMENI = 900


def posebne_teme(program: Program) -> list[Tema]:
    """Redovi globalnog plana za časove van tema (inicijalni test, pismeni zadaci)."""
    out = []
    if program.inicijalni_casova:
        out.append(Tema(redni_broj=RB_INICIJALNI, naziv="Inicijalni test i analiza",
                        casova_ostalo=program.inicijalni_casova))
    if program.pismeni_broj:
        out.append(Tema(redni_broj=RB_PISMENI, naziv="Pismeni zadaci i ispravke",
                        casova_ostalo=program.pismeni_broj * (program.pismeni_trajanje + program.pismeni_ispravka)))
    return out


def rasporedi(teme: list[Tema], slotovi: list[date], program: Program | None = None,
              razmak_ispravke: int = 3, kraj_polugodista: date | None = None) -> tuple[list[Cas], int]:
    """Dodeli časove datumima redom. Vraća (časovi, broj časova koji nisu stali).

    Ako je dat `program`, dodaju se inicijalni test (na početku) i pismeni zadaci, ravnomerno
    kroz godinu, po mogućstvu odmah posle završene teme; dvočasovni pismeni se stavlja na dan
    kada nastavnik ima blok čas (ako takav dan postoji). Ispravka ide `razmak_ispravke` časova kasnije.
    """
    redovni: list[tuple[Tema, NastavnaJedinica]] = [(t, j) for t in teme for j in sekvenca_jedinica(t)]
    kraj_teme = {i for i in range(len(redovni)) if i == len(redovni) - 1 or redovni[i][0] is not redovni[i + 1][0]}
    niz: list[tuple[int, str, NastavnaJedinica]] = []
    if program and program.inicijalni_casova:
        naz = "Inicijalni test i analiza"
        niz.append((RB_INICIJALNI, naz, NastavnaJedinica(naziv="Inicijalni test", tip="inicijalni")))
        for _ in range(program.inicijalni_casova - 1):
            niz.append((RB_INICIJALNI, naz, NastavnaJedinica(naziv="Analiza rezultata inicijalnog testa",
                                                             tip="inicijalni")))
    n_pz = program.pismeni_broj if program else 0
    trajanje = program.pismeni_trajanje if program else 1
    ispravka = program.pismeni_ispravka if program else False
    L = len(redovni)
    ciljevi = _ciljevi_pismenih(n_pz, slotovi, kraj_polugodista, len(niz),
                                trajanje + int(ispravka), L)
    # pomeri cilj na kraj najbliže teme (±4 časa)
    for k, c in enumerate(ciljevi):
        blizu = [i + 1 for i in kraj_teme if abs(i + 1 - c) <= 4]
        if blizu:
            ciljevi[k] = min(blizu, key=lambda x: abs(x - c))
    ima_blok = any(slotovi[i] == slotovi[i + 1] for i in range(len(slotovi) - 1))
    ispravke: list[tuple[int, int]] = []  # (posle koliko redovnih, broj pismenog)
    naz_pz = "Pismeni zadaci i ispravke"
    pz = 0
    odlozeno = 0

    def ubaci_pismeni():
        nonlocal pz
        pz += 1
        for d in range(trajanje):
            deo = f" ({d + 1}/{trajanje})" if trajanje > 1 else ""
            niz.append((RB_PISMENI, naz_pz, NastavnaJedinica(naziv=f"{pz}. pismeni zadatak{deo}", tip="pismeni")))
        if ispravka:
            ispravke.append((ri + razmak_ispravke, pz))

    ri = 0
    while ri <= L:
        while ispravke and ispravke[0][0] <= ri:
            _, br = ispravke.pop(0)
            niz.append((RB_PISMENI, naz_pz, NastavnaJedinica(naziv=f"Ispravka {br}. pismenog zadatka", tip="ispravka")))
        if pz < n_pz and ri >= ciljevi[pz]:
            poz = len(niz)
            na_bloku = poz + trajanje - 1 < len(slotovi) and len(set(slotovi[poz:poz + trajanje])) == 1
            if trajanje == 1 or not ima_blok or na_bloku or odlozeno >= 4 or ri == L:
                ubaci_pismeni()
                odlozeno = 0
                continue
            odlozeno += 1
        if ri == L:
            break
        t, j = redovni[ri]
        niz.append((t.redni_broj, t.naziv, j))
        ri += 1
    while pz < n_pz:
        ubaci_pismeni()
    for _, br in ispravke:
        niz.append((RB_PISMENI, naz_pz, NastavnaJedinica(naziv=f"Ispravka {br}. pismenog zadatka", tip="ispravka")))

    casovi = [Cas(redni_broj=i + 1, datum=slotovi[i], tema_rb=rb, tema=naz, jedinica=j.naziv, tip=j.tip)
              for i, (rb, naz, j) in enumerate(niz[:len(slotovi)])]
    return casovi, max(0, len(niz) - len(slotovi))


def meseci_u_godini(casovi: list[Cas]) -> list[tuple[int, int]]:
    """(godina, mesec) redom kako se pojavljuju."""
    return list(OrderedDict.fromkeys((c.datum.year, c.datum.month) for c in casovi))


def globalni_plan(casovi: list[Cas], teme: list[Tema]) -> dict:
    """Tabela: tema × mesec, plus zbir po tipu časa."""
    meseci = meseci_u_godini(casovi)
    redovi = []
    for t in teme:
        ct = [c for c in casovi if c.tema_rb == t.redni_broj]
        po_mesecu = {m: sum(1 for c in ct if (c.datum.year, c.datum.month) == m) for m in meseci}
        redovi.append({
            "rb": t.redni_broj,
            "tema": t.naziv,
            "po_mesecu": po_mesecu,
            "obrada": sum(1 for c in ct if c.tip == "obrada"),
            "utvrdjivanje": sum(1 for c in ct if c.tip == "utvrđivanje"),
            "ostalo": sum(1 for c in ct if c.tip not in ("obrada", "utvrđivanje")),
            "ukupno": len(ct),
        })
    return {
        "meseci": meseci,
        "nazivi_meseci": [MESECI[m] for _, m in meseci],
        "redovi": redovi,
        "ukupno_po_mesecu": {m: sum(r["po_mesecu"][m] for r in redovi) for m in meseci},
        "ukupno": len(casovi),
    }


def operativni_plan(casovi: list[Cas], godina: int, mesec: int) -> list[Cas]:
    return [c for c in casovi if c.datum.year == godina and c.datum.month == mesec]


def napravi_plan(program: Program, slotovi: list[date], strategija: Strategija = "glasnik",
                 broj_provera: int = 0, udeo_obrade: float | None = None,
                 kraj_polugodista: date | None = None) -> tuple[list[Tema], list[Cas], int]:
    """Vraća (teme za globalni plan — uključujući posebne redove, časovi, broj koji nije stao)."""
    teme = program.teme
    if udeo_obrade is not None:
        teme = podeli_obradu_utvrdjivanje(teme, udeo_obrade)
    if strategija == "glasnik":
        if len(slotovi) >= program.ukupno_casova:
            slotovi, _ = slotovi_po_glasniku(slotovi, program.ukupno_casova, kraj_polugodista)
        else:  # časova u kalendaru je manje od glasnika → mora da se skrati srazmerno
            strategija = "proporcionalno"
    teme = uskladi_fond(teme, max(0, len(slotovi) - program.posebnih_casova),
                        "bez_izmena" if strategija == "glasnik" else strategija)
    teme = postavi_provere(teme, broj_provera)
    casovi, nije_stalo = rasporedi(teme, slotovi, program, kraj_polugodista=kraj_polugodista)
    posebne = posebne_teme(program)
    return [t for t in posebne if t.redni_broj == RB_INICIJALNI] + teme + \
        [t for t in posebne if t.redni_broj != RB_INICIJALNI], casovi, nije_stalo
