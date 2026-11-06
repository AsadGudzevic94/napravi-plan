"""Modeli podataka: program predmeta, teme, časovi, kalendar."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TipCasa = Literal["obrada", "utvrđivanje", "provera", "sistematizacija", "rezerva", "pismeni", "ispravka",
                  "inicijalni"]

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
    jedinice: list[NastavnaJedinica] = Field(default_factory=list)
    kompetencije: list[str] = Field(default_factory=list)  # međupredmetne kompetencije
    korelacija: list[str] = Field(default_factory=list)  # predmeti za povezivanje
    obrazlozenje: list[str] = Field(default_factory=list)  # zašto su izabrane (izvor: glasnik / logika)

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
    # posebni časovi koje glasnik propisuje van tema
    inicijalni_casova: int = 0  # inicijalni test + analiza
    pismeni_broj: int = 0  # broj pismenih zadataka u godini
    pismeni_trajanje: int = 1  # časova po pismenom (npr. 2 = dvočas)
    pismeni_ispravka: bool = True  # posle svakog pismenog čas ispravke
    uputstvo: list[str] = Field(default_factory=list)  # uputstvo za ostvarivanje programa (za ovaj razred)
    fond_glasnika: int | None = None  # ukupno časova kako piše u glasniku (pre izmena nastavnika)

    @model_validator(mode="after")
    def _popuni_godisnji(self) -> Program:
        if self.godisnji_fond is None:
            self.godisnji_fond = (sum(t.casova_ukupno for t in self.teme) + self.posebnih_casova) or None
        return self

    @property
    def zbir_tema(self) -> int:
        return sum(t.casova_ukupno for t in self.teme)

    @property
    def posebnih_casova(self) -> int:
        return self.inicijalni_casova + self.pismeni_broj * (self.pismeni_trajanje + int(self.pismeni_ispravka))

    @property
    def ukupno_casova(self) -> int:
        return self.zbir_tema + self.posebnih_casova


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
    kraj_zavrsni: date | None = None  # kraj nastave za završni razred, ako se razlikuje
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
