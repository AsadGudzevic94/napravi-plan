"""Formatiranje matematičkih zapisa u tekstu plana: x2 → x², log2 → log₂, sqrt(x) → √x, <= → ≤ …

Koristi Unicode znakove, pa formule izgledaju ispravno u Wordu, Excelu, na telefonu i u pregledaču,
bez posebnog editora jednačina.
"""
from __future__ import annotations

import re

_GORE = str.maketrans("0123456789+-()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ")
_DOLE = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def formatiraj(t: str) -> str:
    if not t:
        return t
    # promenljiva y napisana ćiriličnim „у“ u glasniku: „у = x2“ → „y = x2“
    t = re.sub(r"(?<![^\W\d_])[уu](?=\s*=)", "y", t)
    # osnova logaritma: log2 x → log₂ x
    t = re.sub(r"\blog(\d+)", lambda m: "log" + m.group(1).translate(_DOLE), t)
    # eksplicitni stepen: x^2, a^(n+1), 2^n
    t = re.sub(r"\^\(([0-9+\-n]+)\)", lambda m: m.group(1).translate(_GORE), t)
    t = re.sub(r"\^([0-9n]+)", lambda m: m.group(1).translate(_GORE), t)
    # stepen bez ^ samo uz jednoslovnu latiničnu promenljivu: x2, y3 (ne „2. razred“, ne „PG7“)
    # (samo mala slova x, y, z, a, b, c, n, m, k, t — da „B2“ za nivo jezika ostane kako jeste)
    t = re.sub(r"(?<![\w])([xyzabcnmkt])(\d{1,2})(?![\w])", lambda m: m.group(1) + m.group(2).translate(_GORE), t)
    # koren
    t = re.sub(r"sqrt\(([^()]+)\)", r"√(\1)", t)
    t = re.sub(r"√\((\w)\)", r"√\1", t)
    # relacije i operacije
    for a, b in (("<=", "≤"), (">=", "≥"), ("!=", "≠"), ("+-", "±"), ("->", "→")):
        t = t.replace(a, b)
    t = re.sub(r"(?<=\w)\s*\*\s*(?=\w)", "·", t)
    t = re.sub(r"\bpi\b", "π", t)
    return t
