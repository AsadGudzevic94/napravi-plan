"""Preslovljavanje ćirilica ↔ latinica (za izvoz plana na pismu koje nastavnik izabere)."""
from __future__ import annotations

import re

_C2L = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I",
    "Ј": "J", "К": "K", "Л": "L", "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R",
    "С": "S", "Т": "T", "Ћ": "Ć", "У": "U", "Ф": "F", "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
}
_C2L.update({k.lower(): v.lower() for k, v in list(_C2L.items())})
_L2C_DIGRAF = {"Lj": "Љ", "LJ": "Љ", "lj": "љ", "Nj": "Њ", "NJ": "Њ", "nj": "њ", "Dž": "Џ", "DŽ": "Џ", "dž": "џ"}
_L2C = {v: k for k, v in _C2L.items() if len(v) == 1}
# formule i oznake koje ne treba preslovljavati (x2, sin, cos, log…)
_SLOVO = r"[^\W\d_]"
_OPER = r"[=<>≤≥+\-−·/^√±]"
# formule i oznake koje ne treba preslovljavati: funkcije, promenljive sa stepenom/indeksom,
# x/y/z, i jednoslovne promenljive uz matematički operator („a ≤ b“, „2a + b“)
_ZASTICENO = re.compile(
    r"\b(?:sin|cos|tg|ctg|arcsin|arccos|arctg|log|ln|lim|max|min)[₀-₉]*"
    r"|\b(?:Word|Excel|PDF|LLM)\b"
    r"|[A-Za-z](?=[⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁺⁻₀-₉])"
    rf"|(?<!{_SLOVO})[xyz](?!{_SLOVO})"
    rf"|(?<!{_SLOVO})[A-Za-z](?!{_SLOVO})(?=\s*(?:{_OPER}|\)))"
    rf"|(?<={_OPER})\s*[A-Za-z](?!{_SLOVO})"
    rf"|(?<=\d)[A-Za-z](?!{_SLOVO})"
)


def u_latinicu(t: str) -> str:
    return "".join(_C2L.get(c, c) for c in t)


def u_cirilicu(t: str) -> str:
    delovi, poz = [], 0
    for m in _ZASTICENO.finditer(t):
        delovi.append(_l2c(t[poz:m.start()]))
        delovi.append(m.group())
        poz = m.end()
    delovi.append(_l2c(t[poz:]))
    return "".join(delovi)


def _l2c(t: str) -> str:
    out, i = [], 0
    while i < len(t):
        dva = t[i:i + 2]
        if dva in _L2C_DIGRAF:
            out.append(_L2C_DIGRAF[dva])
            i += 2
        else:
            out.append(_L2C.get(t[i], t[i]))
            i += 1
    return "".join(out)


def preslovi(t: str, pismo: str) -> str:
    if not t:
        return t
    return u_cirilicu(t) if pismo.startswith("ć") or pismo.startswith("c") else u_latinicu(t)
