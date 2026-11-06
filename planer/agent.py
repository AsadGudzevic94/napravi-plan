"""Kontrolisani agent: pravi plan korak po korak, kao iskusan asistent — pouzdano i sa besplatnim LLM-om.

Prva verzija je pustila besplatni model da sam vodi ceo razgovor (slobodno pozivanje alata). U pravoj
probi sa Groq-om model se „vrteo u krug“ (ponavljao pitanja, nije beležio odgovore) i brzo trošio
besplatni limit. Zato je podela posla ovakva:

- **Kod vodi postupak** (isti redosled kojim je napravljen prvi plan) i sam izvršava korake čim ima
  podatke: pronalazi program u glasniku, računa kalendar, analizira kompetencije, pravi plan i
  pokreće provere. Nijedan korak ne može da se preskoči, a brojevi su uvek tačni.
- **LLM razume nastavnika**: iz slobodno napisane poruke izvlači SVE podatke koje sadrži (npr.
  „matematika, 2. razred TDS, 3 časa, utorak i četvrtak blok“ popunjava šest pitanja odjednom) i
  prevodi slobodne izmene („teme 3 neka bude 25 časova“) u format koji kod razume.
  Jedan mali poziv po poruci → brzo i u okviru besplatnog limita.
- Posle plana **automatske provere**; ako nešto ne valja, agent to kaže nastavniku.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .intervju import (PITANJA, Intervju, parsiraj_broj, parsiraj_ceo, parsiraj_godinu, parsiraj_listu,
                       parsiraj_opciono, parsiraj_pismo, parsiraj_procenat, parsiraj_raspored, parsiraj_razred,
                       parsiraj_tekst, parsiraj_tip)
from .llm import LLM, LLMGreska

# polja koja LLM sme da popuni iz slobodne poruke → (opis za LLM, parser koji proverava vrednost)
POLJA = {
    "tip_skole": ("'osnovna' ili 'srednja'", parsiraj_tip),
    "razred": ("razred kao broj (1–8)", parsiraj_razred),
    "predmet": ("naziv predmeta, npr. 'Matematika'", parsiraj_tekst),
    "smer": ("obrazovni profil/smer srednje škole", parsiraj_tekst),
    "trajanje_srednje": ("trajanje smera u godinama: 3 ili 4", parsiraj_ceo),
    "nedeljni_fond": ("broj časova nedeljno", parsiraj_broj),
    "raspored": ("dani i broj časova tog dana, npr. 'utorak 1, četvrtak 2'", parsiraj_raspored),
    "skolska_godina": ("školska godina, npr. '2026/27'", parsiraj_godinu),
    "udeo_obrade": ("procenat časova obrade, npr. '40'", parsiraj_procenat),
    "broj_provera": ("broj kontrolnih provera pored pismenih (ceo broj)", parsiraj_ceo),
    "udzbenik": ("udžbenik (izdavač/autor) ili '-'", parsiraj_opciono),
    "zelje": ("želje za metode, oblike rada, korelaciju ili '-'", parsiraj_opciono),
    "strucni_predmeti": ("stručni predmeti odeljenja, zarezom ili '-'", parsiraj_listu),
    "predmeti_odeljenja": ("opšteobrazovni predmeti odeljenja, zarezom ili '-'", parsiraj_listu),
    "pismo": ("'ćirilica' ili 'latinica'", parsiraj_pismo),
}

# format odgovora za pitanja-potvrde (LLM prevodi slobodan tekst u ovaj format)
POTVRDE = {
    "program_ok": "'da' ako je program tačan; inače izmene, svaka u svom redu: '3 ; 25' (tema 3 ima 25 časova), "
                  "'3 ; 20 ; 5' (obrada ; utvrđivanje), 'redosled 2,1,3', 'obriši 4'",
    "pismeni_ok": "'da'; ili izmene: 'pismeni 2', 'trajanje 1', 'inicijalni 0', 'bez ispravke'",
    "kalendar_ok": "'da'; ili izmene, svaka u svom redu: 'kraj 2027-06-04', 'raspust 2027-04-26 2027-05-03', "
                   "'neradni 2027-01-27', 'početak 2026-09-01'",
    "kompetencije_ok": "'da'; ili izmene, svaka u svom redu: '4: Fizika, Saobraćajna tehnika' (zameni predmete "
                       "za povezivanje teme 4), 'dodaj 3: Fizika', 'bez 1: Hemija', 'mk 2: komunikacija, saradnja'",
    "varijanta": "redni broj izabrane varijante (samo broj)",
    "strategija": "'1' (proporcionalno skrati) ili '2' (bez izmena)",
}

SISTEM_IZVLACENJE = """Ti si asistent koji iz poruke nastavnika izvlači podatke za plan rada.
Vrati ISKLJUČIVO JSON objekat {"polje": "vrednost", ...} samo za polja koja poruka STVARNO sadrži
(ne pogađaj, ne izmišljaj). Vrednost piši kao kratak tekst u traženom formatu.
Ako trenutno pitanje ima „Format potvrde“, OBAVEZNO vrati "potvrda": "<odgovor u tom formatu>"
(više izmena — svaka u novom redu). Redne brojeve tema piši ciframa („treća tema“ → 3)."""


SISTEM_KOMANDE = """Pretvori odgovor nastavnika u komande koje program razume.
Vrati ISKLJUČIVO JSON {"komande": ["...", "..."]}.
- Ako nastavnik prihvata predlog bez izmena (npr. „ok“, „super“, „slažem se“), vrati {"komande": ["da"]}.
- Ako traži izmene, vrati po jednu komandu za svaku izmenu, tačno u dozvoljenom formatu;
  redni broj teme piši ciframa („treća tema“ → 3), nazive predmeta sa velikim početnim slovom.
- Ne dodaj ništa što nastavnik nije tražio."""


@dataclass
class Agent:
    llm: LLM | None
    iv: Intervju = field(default_factory=Intervju)
    koraci: list[str] = field(default_factory=list)
    glasnik: tuple[list, str] | None = None
    plan: dict | None = None
    gotovo: bool = False

    def __post_init__(self):
        self.iv.llm = self.llm

    # ------------------------------------------------------------ javni interfejs
    def posalji_glasnik(self, varijante: list, izvor: str) -> None:
        self.glasnik = (varijante, izvor)
        self.koraci.append(f"📎 Glasnik učitan: {izvor} ({len(varijante)} programa)")

    def pocetak(self) -> str:
        return ("Zdravo! Napišite mi slobodno za koji plan je potreban — npr. „Matematika, srednja stručna, "
                "2. razred, Tehničar drumskog saobraćaja, 3 časa, utorak 1 i četvrtak blok 2, 2026/27“ — i "
                "pošaljite glasnik (DOCX). Dalje idemo korak po korak; pitaću samo ono što ne znam.")

    def korak(self, tekst: str) -> str:
        """Obradi poruku nastavnika, izvrši sve korake za koje ima podataka i vrati sledeće pitanje."""
        poruke: list[str] = []
        if tekst.strip():
            poruke += self._razumi(tekst)
        poruke += self._automatski_koraci()
        if self.gotovo:
            return "\n\n".join(poruke)
        sledece = self.iv.pitanje()
        broj = len(self.iv.zavrseno) + 1
        return "\n\n".join(poruke + [f"**Korak {broj}** — {sledece}"])

    # ------------------------------------------------------------ razumevanje nastavnika
    def _razumi(self, tekst: str) -> list[str]:
        trenutno = self.iv.trenutno()
        if trenutno is None:
            return []
        if trenutno.kljuc in POTVRDE:
            return self._potvrda(tekst, trenutno)
        upisano: list[str] = []
        potvrda = None
        if self.llm:
            izvuceno = self._izvuci(tekst, trenutno)
            potvrda = izvuceno.pop("potvrda", None)
            for k, v in izvuceno.items():
                if k not in POLJA or k in self.iv.zavrseno or v in (None, ""):
                    continue
                try:
                    self.iv.s[k] = POLJA[k][1](str(v), self.iv.s)
                except ValueError:
                    continue
                self.iv.zavrseno.add(k)
                self.iv._posle(k)
                upisano.append(f"{k} = {self.iv.s[k]}")
            if upisano:
                self.koraci.append("🧠 Razumeo: " + "; ".join(upisano))
        if trenutno.kljuc in self.iv.zavrseno:  # LLM je već popunio trenutno pitanje
            return []
        greska = self.iv.odgovori(tekst)  # deterministički parser (+ LLM pomoć za format)
        if greska and potvrda:
            greska = self.iv.odgovori(str(potvrda))
        if greska and not upisano:
            return [f"⚠️ {greska}"]
        return []

    def _potvrda(self, tekst: str, trenutno) -> list[str]:
        """Pitanje-potvrda: prvo parser bez LLM-a, a ako ne razume — LLM prevodi u komande."""
        greska = self.iv.odgovori(tekst)
        if not greska or not self.llm:
            return [f"⚠️ {greska}"] if greska else []
        upit = (f"Pitanje koje je agent postavio nastavniku:\n{trenutno.tekst(self.iv.s)[:1500]}\n\n"
                f"Dozvoljene komande: {POTVRDE[trenutno.kljuc]}\n\nOdgovor nastavnika: {tekst}")
        try:
            odg = self.llm.chat_json(SISTEM_KOMANDE, upit, max_tokena=2000)
        except (LLMGreska, ValueError):
            return [f"⚠️ {greska}"]
        komande = odg.get("komande") or []
        if isinstance(komande, str):
            komande = [komande]
        if not komande:
            return [f"⚠️ {greska}"]
        self.koraci.append("🧠 Razumeo izmenu: " + " | ".join(map(str, komande)))
        izmene = [str(k) for k in komande if str(k).strip().lower() != "da"]
        if izmene:
            greska = self.iv.odgovori("\n".join(izmene))
            if greska:
                return [f"⚠️ {greska}"]
            if any(str(k).strip().lower() == "da" for k in komande):
                return []  # izmenjeno → pitanje se ponavlja sa novim stanjem, pa nastavnik potvrđuje
            return []
        greska = self.iv.odgovori("da")
        return [f"⚠️ {greska}"] if greska else []

    def _izvuci(self, tekst: str, trenutno) -> dict:
        nedostaju = {k: opis for k, (opis, _) in POLJA.items() if k not in self.iv.zavrseno}
        upit = (f"Trenutno pitanje ({trenutno.kljuc}): {trenutno.tekst(self.iv.s)[:600]}\n"
                + (f"Format potvrde: {POTVRDE[trenutno.kljuc]}\n" if trenutno.kljuc in POTVRDE else "")
                + "Polja koja još nedostaju:\n" + "\n".join(f"- {k}: {o}" for k, o in nedostaju.items())
                + f"\n\nPoruka nastavnika: {tekst}")
        try:
            return self.llm.chat_json(SISTEM_IZVLACENJE, upit, max_tokena=2000)
        except (LLMGreska, ValueError) as e:
            self.koraci.append(f"⚠️ LLM nije uspeo ({str(e)[:80]}) — koristim parser bez LLM-a")
            return {}

    # ------------------------------------------------------------ koraci koje kod radi sam
    def _automatski_koraci(self) -> list[str]:
        out: list[str] = []
        for _ in range(len(PITANJA) + 2):
            p = self.iv.trenutno()
            if p is None:
                out += self._zavrsi()
                break
            if p.kljuc == "program" and self.glasnik:
                greska = self.iv.postavi_glasnik(*self.glasnik)
                if greska:
                    out.append(f"⚠️ {greska}")
                    break
                prog = self.iv.s.get("program")
                self.koraci.append("🔎 Program iz glasnika: " + (
                    f"{prog.predmet}, {prog.razred}. razred, {prog.ukupno_casova} časova" if prog else
                    f"{len(self.iv.s.get('kandidati', []))} varijanti — pitam nastavnika"))
                continue
            if p.kljuc == "kalendar_ok" and "kalendar_izracunat" not in self.iv.s.podaci:
                self.iv.s["kalendar_izracunat"] = True
                self.koraci.append(f"📅 Kalendar: {len(self.iv.s.slotovi())} časova po rasporedu, glasnik "
                                   f"{self.iv.s['program'].ukupno_casova}")
            if p.kljuc == "kompetencije_ok" and not self.iv.s.get("analizirano"):
                p.tekst(self.iv.s)  # pokreće analizu
                self.koraci.append("🧩 Analizirane kompetencije i povezivanje (glasnik + logika)")
            break
        return out

    def _zavrsi(self) -> list[str]:
        from .provera import izvestaj
        from .raspodela import globalni_plan
        from .sadrzaj import podrazumevano_operativno
        teme, casovi, nije_stalo = self.iv.napravi()
        casovi = podrazumevano_operativno(casovi, teme)
        self.plan = {"teme": teme, "casovi": casovi, "nije_stalo": nije_stalo}
        gp = globalni_plan(casovi, teme)
        self.koraci.append(f"🗓️ Plan napravljen: {gp['ukupno']} časova")
        rez = self.iv.provera(casovi)
        self.koraci.append(f"🔎 Provera: {sum(r[0] == 'ok' for r in rez)}/{len(rez)} u redu")
        self.gotovo = True
        return [f"✅ Plan je gotov: **{gp['ukupno']} časova**. Proverio sam ga:\n\n" + izvestaj(rez)
                + ("\n\n" + self.iv.napomena_rezerve() if self.iv.napomena_rezerve() else "")
                + "\n\nIspod su godišnji plan i mesečni planovi po ZUOV obrascima za preuzimanje."]
