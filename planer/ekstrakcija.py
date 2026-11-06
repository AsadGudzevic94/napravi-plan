"""Izvlačenje programa predmeta iz PDF-a Službenog/Prosvetnog glasnika.

Da bi bilo brzo i staje u besplatne limite, prvo se BEZ LLM-a pronađu stranice
koje se odnose na traženi predmet i razred, pa se samo taj deo šalje LLM-u.
"""
from __future__ import annotations

import io
import re
import unicodedata

from pypdf import PdfReader

from .llm import LLM
from .modeli import Program, Tema

_CIR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџш",
                ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n",
                 "nj", "o", "p", "r", "s", "t", "ć", "u", "f", "h", "c", "č", "dž", "š"]))

RIMSKI = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii"}
REDNI = {1: "prvi", 2: "drugi", 3: "treći", 4: "četvrti", 5: "peti", 6: "šesti", 7: "sedmi",
         8: "osmi"}


def normalizuj(tekst: str) -> str:
    """Mala slova, ćirilica → latinica, bez dijakritika (za pretragu)."""
    t = "".join(_CIR.get(ch, ch) for ch in tekst.lower())
    t = t.replace("đ", "dj")
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def stranice_iz_pdf(sadrzaj: bytes) -> list[str]:
    citac = PdfReader(io.BytesIO(sadrzaj))
    return [(s.extract_text() or "") for s in citac.pages]


def pronadji_odeljak(stranice: list[str], predmet: str, razred: int | None = None,
                     max_znakova: int = 30000) -> str:
    """Izaberi uzastopne stranice sa najviše pominjanja predmeta (i razreda)."""
    if not stranice:
        return ""
    p = normalizuj(predmet)
    kljucne = [p] + [w for w in p.split() if len(w) > 3]
    raz = []
    if razred:
        raz = [f"{RIMSKI.get(razred, '')} razred", normalizuj(REDNI.get(razred, "")) + " razred",
               f"{razred}. razred"]
    ocene = []
    for s in stranice:
        n = normalizuj(s)
        o = 5 * n.count(p) + sum(n.count(k) for k in kljucne[1:])
        o += 3 * sum(n.count(r) for r in raz if r.strip() != "razred")
        o += 2 * (("ishodi" in n) + ("tema" in n or "oblast" in n))
        ocene.append(o)
    if max(ocene) == 0:
        return "\n".join(stranice)[:max_znakova]
    # najbolja stranica, pa širi prozor dok ima mesta i susedne stranice su relevantne
    najbolja = max(range(len(stranice)), key=lambda i: ocene[i])
    lo = hi = najbolja
    duzina = len(stranice[najbolja])
    while True:
        kand = []
        if lo > 0:
            kand.append((ocene[lo - 1], lo - 1))
        if hi < len(stranice) - 1:
            kand.append((ocene[hi + 1], hi + 1))
        if not kand:
            break
        o, i = max(kand)
        if o == 0 or duzina + len(stranice[i]) > max_znakova:
            break
        duzina += len(stranice[i])
        lo, hi = min(lo, i), max(hi, i)
    return "\n".join(stranice[lo:hi + 1])


SISTEM_EKSTRAKCIJA = """Ti si stručnjak za planove i programe nastave i učenja u Srbiji i regionu.
Iz datog teksta službenog glasnika izvuci program za TRAŽENI predmet i razred (i smer ako je dat).
Vrati ISKLJUČIVO JSON ovog oblika:
{
 "predmet": str, "razred": int, "smer": str|null,
 "nedeljni_fond": number, "godisnji_fond": int|null,
 "izvor": str,
 "teme": [
   {"redni_broj": int, "naziv": str,
    "ishodi": [str], "sadrzaji": [str],
    "casova_obrada": int, "casova_utvrdjivanje": int, "casova_ostalo": int}
 ]
}
Pravila:
- Prepiši nazive tema/oblasti i ishode tačno kako su u tekstu (latinicom).
- Ako je za temu dat samo ukupan broj časova, stavi ga u casova_obrada, ostalo 0, i NE izmišljaj podelu.
- Ako broj časova po temi NIJE naveden, stavi sve brojeve 0 (nastavnik će ih uneti).
- Nedeljni i godišnji fond uzmi iz tabele plana nastave ako postoji.
- Ne izmišljaj teme kojih nema u tekstu."""


def izvuci_program(llm: LLM, tekst: str, predmet: str, razred: int, tip_skole: str,
                   smer: str | None = None) -> Program:
    upit = (f"Predmet: {predmet}\nRazred: {razred}\nTip škole: {tip_skole}\n"
            f"Smer: {smer or '-'}\n\nTEKST GLASNIKA:\n{tekst}")
    podaci = llm.chat_json(SISTEM_EKSTRAKCIJA, upit, max_tokena=8000)
    podaci["tip_skole"] = tip_skole
    podaci.setdefault("predmet", predmet)
    podaci.setdefault("razred", razred)
    podaci["teme"] = [Tema.model_validate({**t, "redni_broj": t.get("redni_broj") or i + 1})
                      for i, t in enumerate(podaci.get("teme", []))]
    if not podaci.get("nedeljni_fond"):
        podaci["nedeljni_fond"] = 0
    return Program.model_validate(podaci)


def nedeljni_fond_iz_teksta(tekst: str) -> float | None:
    """Pokušaj bez LLM-a: '4 časa nedeljno', 'nedeljni fond: 2'."""
    n = normalizuj(tekst)
    m = re.search(r"(\d+(?:[.,]\d)?)\s*(?:cas|casa|casova)\s+nedeljno", n) or \
        re.search(r"nedeljni\s+fond[^\d]{0,20}(\d+(?:[.,]\d)?)", n)
    return float(m.group(1).replace(",", ".")) if m else None
