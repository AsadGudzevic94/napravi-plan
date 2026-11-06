# Zvanični školski kalendari

Ovde stavite JSON kalendar prepisan iz Pravilnika o kalendaru obrazovno-vaspitnog rada.
Ime fajla: `srbija_2026-27.json` (važi za sve), ili `srbija_2026-27_osnovna.json`,
ili `srbija_2026-27_osnovna_8.json` (samo za 8. razred). Ako fajla nema, koristi se
približan kalendar koji nastavnik potvrđuje u razgovoru.

```json
{
  "naziv": "Školska 2026/27 – Pravilnik ...",
  "drzava": "srbija",
  "pocetak": "2026-09-01",
  "kraj_prvog_polugodista": "2026-12-30",
  "kraj": "2027-06-18",
  "raspusti": [{"naziv": "Zimski raspust", "od": "2026-12-31", "do": "2027-01-15"}],
  "dodatni_neradni": [{"datum": "2027-01-27", "naziv": "Sveti Sava (nenastavni dan)"}],
  "zamene": [{"datum": "2026-10-17", "po_rasporedu_dana": 4}]
}
```
`po_rasporedu_dana`: 0 = ponedeljak … 4 = petak (radna subota po rasporedu tog dana).
