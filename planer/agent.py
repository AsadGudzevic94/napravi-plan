"""Agent koji pravi plan korak po korak — onako kako bi to uradio iskusan nastavnik sa asistentom.

LLM (besplatan: Groq / Gemini / OpenRouter / Ollama) **vodi** posao: odlučuje koji je sledeći korak,
šta da pita nastavnika i kako da protumači odgovor. **Sve brojeve i datume računa kod** preko alata
(kalendar, raspodela, pismeni, provere), pa LLM ne može da pogreši u računu ni da izmisli fond.

Postupak (isti kojim je napravljen prvi plan):
 1. utvrdi školu, razred, predmet, smer, trajanje i nedeljni fond;
 2. pronađi u glasniku pravi program (varijanta po fondu i trajanju) i pročitaj teme, ishode, časove,
    inicijalni test i pismene zadatke; pokaži nastavniku i potvrdi;
 3. utvrdi raspored (dani, blok čas) i školski kalendar; uporedi broj časova sa glasnikom
    (glasnik ima prednost);
 4. podeli časove tema na obradu i utvrđivanje;
 5. analiziraj međupredmetne kompetencije i predmete za povezivanje (glasnik + logika) i potvrdi;
 6. napravi plan, pokreni sve provere, ispravi ili pitaj ako nešto ne valja;
 7. pripremi dokumente po ZUOV obrascima.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .intervju import (Intervju, parsiraj_broj, parsiraj_ceo, parsiraj_godinu, parsiraj_listu, parsiraj_opciono,
                       parsiraj_pismo, parsiraj_procenat, parsiraj_raspored, parsiraj_razred, parsiraj_tekst,
                       parsiraj_tip)
from .llm import LLM, LLMGreska

SISTEM = """Ti si agent koji nastavniku u Srbiji pravi GODIŠNJI (globalni) i OPERATIVNE (mesečne) planove
po službenom glasniku i ZUOV obrascima. Radiš POSTUPNO, korak po korak, i posle svakog koraka proveriš rezultat.

PRAVILA:
- Brojeve, datume i raspodelu NIKAD ne računaš sam — uvek koristiš alate. Ne izmišljaj fond ni teme.
- Glasnik ima prednost: plan ima tačno onoliko časova koliko propisuje glasnik.
- Kad ti nešto fali ili nisi siguran, pozovi `pitaj_nastavnika` sa JEDNIM jasnim, kratkim pitanjem
  (možeš ponuditi predlog). Ne pitaj ono što već znaš ili što piše u glasniku.
- Rezultat svakog važnog koraka (program iz glasnika, kalendar, kompetencije) pokaži nastavniku
  i traži potvrdu pre nego što nastaviš.
- Posle `napravi_plan` UVEK pozovi `proveri_plan`. Ako ima ❌, ispravi (alati) ili pitaj nastavnika.
- Piši na srpskom, kratko i ljubazno.

KORACI: 1) osnovni podaci (postavi_podatke) → 2) pronadji_program (ako glasnik nije poslat, zamoli
nastavnika da ga pošalje dugmetom) → potvrda → 3) raspored i školska godina → izracunaj_kalendar → potvrda
→ 4) udeo obrade ako glasnik daje samo ukupne časove → 5) stručni i drugi predmeti odeljenja →
analiziraj_kompetencije → potvrda → 6) napravi_plan → proveri_plan → 7) pismo (ćirilica/latinica)
→ zavrsi."""

POLJA = {
    "tip_skole": parsiraj_tip, "razred": parsiraj_razred, "predmet": parsiraj_tekst, "smer": parsiraj_tekst,
    "trajanje_srednje": parsiraj_ceo, "nedeljni_fond": parsiraj_broj, "raspored": parsiraj_raspored,
    "skolska_godina": parsiraj_godinu, "udeo_obrade": parsiraj_procenat, "broj_provera": parsiraj_ceo,
    "udzbenik": parsiraj_opciono, "zelje": parsiraj_opciono, "pismo": parsiraj_pismo,
    "strucni_predmeti": parsiraj_listu, "predmeti_odeljenja": parsiraj_listu,
}


def _alat(ime: str, opis: str, svojstva: dict | None = None, obavezna: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": ime, "description": opis, "parameters": {
        "type": "object", "properties": svojstva or {}, "required": obavezna or []}}}


ALATI = [
    _alat("postavi_podatke", "Upiši podatke koje je nastavnik rekao. Vrednosti su tekst kako ih je nastavnik "
          "rekao (npr. raspored: 'utorak 1, četvrtak 2'). Polja: " + ", ".join(POLJA),
          {"podaci": {"type": "object", "description": "polje → vrednost"}}, ["podaci"]),
    _alat("pronadji_program", "Pronađi u poslatom glasniku program za predmet/razred/fond/trajanje i vrati teme, "
          "časove, inicijalni test i pismene. Ako ima više varijanti, vrati spisak.",
          {"varijanta": {"type": "integer", "description": "redni broj varijante ako ih je više"}}),
    _alat("izmeni_program", "Izmeni program po želji nastavnika (isti format kao u razgovoru), npr. "
          "'3 ; 25', 'redosled 2,1,3', 'pismeni 2', 'inicijalni 0'.", {"izmena": {"type": "string"}}, ["izmena"]),
    _alat("izracunaj_kalendar", "Izračunaj školski kalendar i broj časova po rasporedu i uporedi sa glasnikom."),
    _alat("izmeni_kalendar", "Izmeni kalendar, npr. 'kraj 2027-06-04', 'raspust 2027-04-26 2027-05-03', "
          "'neradni 2027-01-27'.", {"izmena": {"type": "string"}}, ["izmena"]),
    _alat("analiziraj_kompetencije", "Predlog međupredmetnih kompetencija i predmeta za povezivanje po temama, "
          "iz glasnika i logički, sa obrazloženjem."),
    _alat("izmeni_kompetencije", "Izmena predloga, npr. '4: Fizika, Saobraćajna tehnika' ili "
          "'mk 2: komunikacija, saradnja' ili 'bez 3: Hemija'.", {"izmena": {"type": "string"}}, ["izmena"]),
    _alat("napravi_plan", "Napravi godišnji plan i sve mesečne planove (raspodela po kalendaru)."),
    _alat("proveri_plan", "Pokreni automatske provere gotovog plana i vrati izveštaj (✅/⚠️/❌)."),
    _alat("pitaj_nastavnika", "Postavi nastavniku jedno pitanje i sačekaj odgovor.",
          {"pitanje": {"type": "string"}}, ["pitanje"]),
    _alat("zavrsi", "Plan je gotov i proveren; kratko rezimiraj nastavniku.", {"poruka": {"type": "string"}},
          ["poruka"]),
]


@dataclass
class Agent:
    llm: LLM
    iv: Intervju = field(default_factory=Intervju)
    poruke: list[dict] = field(default_factory=lambda: [{"role": "system", "content": SISTEM}])
    koraci: list[str] = field(default_factory=list)  # dnevnik rada za prikaz u aplikaciji
    ceka_odgovor: str | None = None  # id poziva `pitaj_nastavnika` koji čeka odgovor
    glasnik: tuple[list, str] | None = None  # (varijante, izvor)
    plan: dict | None = None
    gotovo: bool = False

    # ------------------------------------------------------------ javni interfejs
    def posalji_glasnik(self, varijante: list, izvor: str) -> None:
        self.glasnik = (varijante, izvor)
        self.koraci.append(f"📎 Glasnik učitan: {izvor} ({len(varijante)} programa)")

    def korak(self, tekst_nastavnika: str, max_koraka: int = 14) -> str:
        """Obradi poruku nastavnika i radi dok ne treba nešto da pita ili dok ne završi."""
        if self.ceka_odgovor:
            self.poruke.append({"role": "tool", "tool_call_id": self.ceka_odgovor,
                                "content": f"Nastavnik odgovara: {tekst_nastavnika}"})
            self.ceka_odgovor = None
        else:
            self.poruke.append({"role": "user", "content": tekst_nastavnika})
        for _ in range(max_koraka):
            try:
                odg = self.llm.chat_alati(self.poruke, ALATI)
            except LLMGreska as e:
                return f"⚠️ LLM trenutno nije dostupan ({e}). Pokušajte ponovo za minut ili koristite vođeni razgovor."
            self.poruke.append({k: v for k, v in odg.items() if k in ("role", "content", "tool_calls")} |
                               {"role": "assistant"})
            pozivi = odg.get("tool_calls") or []
            if not pozivi:
                return odg.get("content") or ""
            for poziv in pozivi:
                ime = poziv["function"]["name"]
                try:
                    arg = json.loads(poziv["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arg = {}
                if ime == "pitaj_nastavnika":
                    self.ceka_odgovor = poziv["id"]
                    pitanje = arg.get("pitanje", "")
                    # ostali pozivi iz iste poruke dobijaju prazan odgovor (protokol traži odgovor na svaki)
                    for drugi in pozivi:
                        if drugi is not poziv and not any(m.get("tool_call_id") == drugi["id"] for m in self.poruke):
                            self.poruke.append({"role": "tool", "tool_call_id": drugi["id"], "content": "preskočeno"})
                    return (odg.get("content") + "\n\n" if odg.get("content") else "") + pitanje
                rezultat = self._izvrsi(ime, arg)
                self.koraci.append(f"🔧 {ime}: {rezultat.splitlines()[0][:120] if rezultat else ''}")
                self.poruke.append({"role": "tool", "tool_call_id": poziv["id"], "content": rezultat})
                if ime == "zavrsi":
                    self.gotovo = True
                    return arg.get("poruka", "Plan je gotov.")
        return "Radim na planu… napišite „nastavi“ ako treba da nastavim."

    # ------------------------------------------------------------ alati
    def _izvrsi(self, ime: str, arg: dict) -> str:
        s = self.iv.s
        try:
            if ime == "postavi_podatke":
                return self._postavi(arg.get("podaci") or {})
            if ime == "pronadji_program":
                return self._program(arg.get("varijanta"))
            if ime == "izmeni_program":
                from .intervju import parsiraj_pismene, parsiraj_potvrdu_programa
                izm = arg.get("izmena", "")
                try:
                    parsiraj_potvrdu_programa(izm, s)
                except ValueError:
                    parsiraj_pismene(izm, s)
                return "Izmenjeno.\n" + self._opis_programa()
            if ime == "izracunaj_kalendar":
                from .intervju import _tekst_kalendara
                return _tekst_kalendara(s)
            if ime == "izmeni_kalendar":
                from .intervju import _tekst_kalendara, parsiraj_kalendar
                parsiraj_kalendar(arg.get("izmena", ""), s)
                return "Izmenjeno.\n" + _tekst_kalendara(s)
            if ime == "analiziraj_kompetencije":
                from .intervju import _tekst_kompetencija
                s.pop("analizirano")
                return _tekst_kompetencija(s)
            if ime == "izmeni_kompetencije":
                from .intervju import _tekst_kompetencija, parsiraj_kompetencije
                parsiraj_kompetencije(arg.get("izmena", ""), s)
                return "Izmenjeno.\n" + _tekst_kompetencija(s)
            if ime == "napravi_plan":
                return self._napravi()
            if ime == "proveri_plan":
                from .provera import izvestaj
                if not self.plan:
                    return "Plan još nije napravljen."
                return izvestaj(self.iv.provera(self.plan["casovi"]))
            if ime == "zavrsi":
                return "ok"
        except (KeyError, ValueError) as e:
            return f"GREŠKA: {e}. Proveri da li su prethodni koraci urađeni ili pitaj nastavnika."
        return f"Nepoznat alat {ime}."

    def _postavi(self, podaci: dict) -> str:
        poruke = []
        for k, v in podaci.items():
            if k not in POLJA:
                poruke.append(f"{k}: nepoznato polje")
                continue
            try:
                self.iv.s[k] = POLJA[k](str(v), self.iv.s)
                self.iv.zavrseno.add(k)
                self.iv._posle(k)
                poruke.append(f"{k} = {self.iv.s[k]}")
            except ValueError as e:
                poruke.append(f"{k}: {e}")
        return "; ".join(poruke)

    def _program(self, varijanta: int | None) -> str:
        s = self.iv.s
        if not self.glasnik:
            return "Glasnik nije poslat. Zamoli nastavnika da pošalje DOCX glasnika dugmetom ispod razgovora."
        if varijanta and s.get("kandidati"):
            self.iv._postavi_varijantu(s["kandidati"][varijanta - 1])
        else:
            greska = self.iv.postavi_glasnik(*self.glasnik)
            if greska:
                return greska
        if "program" not in s.podaci:
            from .intervju import _tekst_varijanti
            return _tekst_varijanti(s)
        return self._opis_programa()

    def _opis_programa(self) -> str:
        from .intervju import _tekst_pismenih, _tekst_programa
        s = self.iv.s
        tekst = _tekst_programa(s)
        if s["program"].pismeni_broj or s["program"].inicijalni_casova:
            tekst += "\n\n" + _tekst_pismenih(s)
        return tekst

    def _napravi(self) -> str:
        from .raspodela import globalni_plan
        from .sadrzaj import podrazumevano_operativno
        if "raspored" not in self.iv.s.podaci or "kalendar" not in self.iv.s.podaci:
            return "GREŠKA: nedostaju raspored ili školska godina."
        teme, casovi, nije_stalo = self.iv.napravi()
        casovi = podrazumevano_operativno(casovi, teme)
        self.plan = {"teme": teme, "casovi": casovi, "nije_stalo": nije_stalo}
        gp = globalni_plan(casovi, teme)
        redovi = "\n".join(f"- {r['tema']}: {r['ukupno']} č. " +
                           ", ".join(f"{m:02d}:{n}" for (g, m), n in r["po_mesecu"].items() if n)
                           for r in gp["redovi"])
        return f"Plan napravljen: {gp['ukupno']} časova.\n{redovi}\n{self.iv.napomena_rezerve()}"
