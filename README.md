# Napravi plan

Besplatna aplikacija koja nastavniku osnovne ili srednje škole za nekoliko minuta pravi
**godišnji (globalni)** i **mesečne (operativne)** planove rada — na osnovu službenog glasnika,
školskog kalendara i rasporeda časova, po **ZUOV obrascima**.

Nastavnik samo razgovara sa aplikacijom: kaže predmet, razred, smer i raspored, pošalje glasnik,
potvrdi predloge — i preuzme gotove Word i Excel dokumente.

## Šta dobijate

- **Godišnji plan** po ZUOV obrascu: teme po mesecima (IX–VI), ukupno časova, međupredmetne
  kompetencije po temi i raspodela časova po tipu (obrada, utvrđivanje, provera).
- **Mesečni plan** za svaki mesec po ZUOV obrascu: oblast/tema, ishodi, redni broj i naziv nastavne
  jedinice, tip časa, međupredmetno povezivanje i rubrika za evaluaciju.
- **Excel** sa svim časovima i datumima.
- Plan na **ćirilici ili latinici**, sa ispravno zapisanim formulama (x², log₂ x, √x, ≤).

## Kako radi

1. **Pravi glasnik, pronađen i proveren.** Nastavnik ne mora da zna koji pravilnik važi: aplikacija u
   zvaničnom ZUOV katalogu važećih propisa pronađe pravilnike za školu, smer i predmet i ponudi ih.
   Nastavnik izabere broj, a aplikacija preuzme glasnik i **proveri** da zaista sadrži program za taj
   predmet, razred i fond časova pre nego što ga upotrebi. Može se poslati i sopstveni DOCX.
2. **Glasnik ima prednost.** Program (teme, ishodi, broj časova, inicijalni test, pismeni zadaci) čita
   se direktno iz glasnika — za osnovne škole, gimnazije i stručne škole. Plan ima tačno onoliko časova
   koliko propisuje glasnik; višak iz kalendara ostaje kao rezerva.
3. **Brojeve računa program, ne AI.** Kalendar (praznici, pravoslavni Uskrs, raspusti), raspodela tema
   po mesecima, pismeni zadaci na blok času i po dva u polugodištu — sve je izračunato tačno.
4. **Kompetencije i povezivanje sa obrazloženjem.** Za svaku temu aplikacija predlaže međupredmetne
   kompetencije i predmete za povezivanje — iz uputstva u glasniku, iz ishoda i logički (uključujući
   stručne predmete profila) — i navodi zašto. Nastavnik potvrđuje ili menja.
5. **Provera pre preuzimanja.** Gotov plan prolazi 15 automatskih provera: zbir časova, nijedan čas na
   praznik ili raspust, redosled tema, pismeni i ispravke, kompetencije, svaki mesec ima časove.

Dva načina rada:

- **Razgovor sa asistentom** — pišete slobodno („matematika, 2. razred, 3 časa, utorak i četvrtak
  blok“), a besplatan AI model razume poruku i izmene. Potreban je besplatan API ključ.
- **Korak po korak** — radi bez AI i bez ključa; aplikacija postavlja pitanja redom.

## Pokretanje

Potreban je Python 3.11 ili noviji.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
streamlit run app.py
```

Za probu bez glasnika, u načinu „korak po korak“ na pitanje o programu napišite `primer`.

U VS Code-u: otvorite folder, izaberite interpreter `.venv`, pa **F5 → Pokreni aplikaciju (Streamlit)**.
Testovi: `python -m pytest`, provera koda: `python -m ruff check .`.

### Besplatan AI ključ (opciono)

Kopirajte `.env.example` u `.env` i upišite ključ (ili ga stavite u `.streamlit/secrets.toml`).

| `LLM_PROVIDER` | Ključ | Napomena |
|---|---|---|
| `groq` | [console.groq.com/keys](https://console.groq.com/keys) | najbrži, preporuka |
| `gemini` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | veliki kontekst |
| `openrouter` | [openrouter.ai/keys](https://openrouter.ai/keys) | modeli sa oznakom `:free` |
| `ollama` | — | lokalno, bez interneta |

## Objava na internetu

Besplatno na Streamlit Community Cloud, i sa telefona — uputstvo: [docs/OBJAVA.md](docs/OBJAVA.md).

## Struktura

```
app.py                        Streamlit aplikacija
planer/
  izvori.py                   pronalaženje važećeg glasnika (ZUOV katalog) i provera
  glasnik_parser.py           čitanje glasnika — DOCX i HTML (programi, teme, ishodi, časovi)
  ekstrakcija.py              čitanje PDF glasnika (uz AI)
  kalendar.py                 praznici, nastavni dani, datumi časova
  podrazumevani_kalendar.py   zvanični ili približan školski kalendar
  raspodela.py                raspodela časova, pismeni zadaci, godišnji i mesečni plan
  kompetencije.py             međupredmetne kompetencije i povezivanje
  provera.py                  automatske provere plana
  intervju.py                 pitanja i tumačenje odgovora
  agent.py                    asistent (AI razume poruke, program vodi korake)
  llm.py                      klijent za Groq / Gemini / OpenRouter / Ollama
  sadrzaj.py                  nazivi jedinica, ishodi i metode
  izvoz.py                    Word po ZUOV obrascima, Excel
  pismo.py, formule.py        ćirilica ↔ latinica, zapis formula
  modeli.py                   modeli podataka
data/                         primer programa, školski kalendari (JSON)
ui/                           izgled aplikacije
tests/                        testovi
docs/                         uputstvo za objavu
```

Zvanični kalendar dodaje se kao JSON u `data/kalendari/` — vidi [data/kalendari/README.md](data/kalendari/README.md).
