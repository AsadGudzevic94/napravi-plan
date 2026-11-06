"""Modeli podataka: program predmeta, teme, časovi, kalendar."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TipCasa = Literal["obrada", "utvrđivanje", "provera", "sistematizacija", "rezerva"]

MESECI = {
    9: "Septembar", 10: "Oktobar", 11: "Novembar", 12: "Decembar",
    1: "Januar", 2: "Februar", 3: "Mart", 4: "April", 5: "Maj", 6: "Jun",
    7: "Jul", 8: "Avgust",
}
DANI = ["ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota", "nedelja"]


class Tema(BaseModel):
    redni_broj: int
    naziv: str
    ishodi: list[str] = Field(default_factory=list)
    sadrzaji: list[str] = Field(default_factory=list)
    casova_obrada: int = 0
    casova_utvrdjivanje: int = 0
    casova_ostalo: int = 0  # provere, sistematizacija...
    jedinice: list["NastavnaJedinica"] = Field(default_factory=list)

    @property
    def casova_ukupno(self) -> int:
        return self.casova_obrada + self.casova_utvrdjivanje + self.casova_ostalo


class NastavnaJedinica(BaseModel):
    naziv: str
    tip: TipCasa = "obrada"


class Program(BaseModel):
    """Plan i program nastave i učenja za jedan predmet/razred/smer."""

    predmet: str
    razred: int
    tip_skole: Literal["osnovna", "srednja"] = "osnovna"
    smer: str | None = None
    nedeljni_fond: float
    godisnji_fond: int | None = None
    izvor: str = ""  # npr. "Službeni glasnik RS – Prosvetni glasnik br. X/20YY"
    teme: list[Tema] = Field(default_factory=list)

    @model_validator(mode="after")
    def _popuni_godisnji(self) -> "Program":
        if self.godisnji_fond is None:
            self.godisnji_fond = sum(t.casova_ukupno for t in self.teme) or None
        return self

    @property
    def zbir_tema(self) -> int:
        return sum(t.casova_ukupno for t in self.teme)


class Raspust(BaseModel):
    naziv: str
    od: date
    do: date


class NeradniDan(BaseModel):
    datum: date
    naziv: str


class Zamena(BaseModel):
    """Npr. radna subota koja se radi po rasporedu petka."""

    datum: date
    po_rasporedu_dana: int  # 0=ponedeljak ... 4=petak


class SkolskiKalendar(BaseModel):
    naziv: str
    drzava: str = "srbija"
    pocetak: date
    kraj_prvog_polugodista: date
    kraj: date
    raspusti: list[Raspust] = Field(default_factory=list)
    dodatni_neradni: list[NeradniDan] = Field(default_factory=list)
    zamene: list[Zamena] = Field(default_factory=list)
    ukljuci_drzavne_praznike: bool = True


class Cas(BaseModel):
    redni_broj: int  # redni broj časa u godini
    datum: date
    tema_rb: int
    tema: str
    jedinica: str
    tip: TipCasa
    # obogaćuje LLM za operativni plan
    ishodi: str = ""
    metode: str = ""
    oblici_rada: str = ""
    korelacija: str = ""

    @property
    def mesec(self) -> int:
        return self.datum.month
