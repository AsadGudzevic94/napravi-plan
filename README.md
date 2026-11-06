# 📘 Napravi plan

Besplatna aplikacija koja nastavniku osnovne i srednje škole pravi **globalni (godišnji)**
i **operativni (mesečni)** plan rada na osnovu **službenog glasnika** (plan i program nastave
i učenja), školskog kalendara i rasporeda časova — kroz kratak razgovor.

Cilj, arhitektura i plan razvoja: **[docs/PLAN.md](docs/PLAN.md)**

## Kako radi
1. Aplikacija pita: tip škole, razred, predmet, smer.
2. Učitate glasnik: **DOCX** (npr. Pravilnik sa paragraf.rs) se čita **bez LLM-a** — predmet, varijanta po
   nedeljnom fondu i trajanju profila, teme, sadržaji, ishodi, oriјentacioni broj časova, inicijalni test i
   pismeni zadaci. PDF čita LLM. Može i ručni unos ili „primer“.
3. Potvrdite/izmenite teme, nedeljni fond, dane kada držite čas i školski kalendar.
4. **Kod** (ne LLM) tačno izračuna sve datume časova (praznici, raspusti, pravoslavni Uskrs)
   i rasporedi teme po mesecima. **Glasnik ima prednost**: plan ima tačno onoliko časova koliko propisuje
   glasnik; višak časova iz kalendara ostaje slobodan (rezerva, navedeni datumi). Samo ako kalendar ima
   manje časova, aplikacija pita kako da skrati.
5. LLM napiše nazive nastavnih jedinica, ishode po času, metode i oblike rada.
6. Preuzmete **.docx** po **zvaničnim ZUOV obrascima** ([zuov.gov.rs/obrasci](https://zuov.gov.rs/obrasci/)):
   *Godišnji plan* (Red. br. | Tema/oblast | Mesec IX–VI | Ukupno + tabela Međupredmetne kompetencije) i
   *Operativni plan* (Oblast/Tema | Ishodi | Redni broj časa i naziv nastavne jedinice | Tip časa |
   Međupredmetno povezivanje | Evaluacija isplaniranog), ili **.xlsx** sa svim časovima i datumima.

## Dva načina rada
- **Vođeni razgovor** (radi i bez LLM-a): aplikacija postavlja pitanja redom.
- **Agent (LLM)**: besplatan model (Groq/Gemini/OpenRouter/Ollama) vodi posao **postupno**, kao asistent:
  sam bira sledeći korak, pita nastavnika samo ono što ne zna, pokazuje rezultat svakog koraka na potvrdu
  i posle pravljenja plana pokreće **automatske provere** (zbir = glasnik, nema časova na praznik, pismeni na
  blok času, ispravke u istom polugodištu, kompetencije po temama…). Brojeve i datume uvek računa kod
  preko alata (`planer/agent.py`), pa model ne može da pogreši u računu.

**Međupredmetne kompetencije i povezivanje** (`planer/kompetencije.py`): za svaku temu se traže pasusi
uputstva iz glasnika (citat), ishodi iz glasnika i logička pravila (gde se sadržaj primenjuje, uključujući
stručne predmete profila); svaki predlog ima izvor i obrazloženje i nastavnik ga potvrđuje.

## Pokretanje
```bash
pip install -r requirements.txt
cp .env.example .env        # upišite BESPLATAN ključ (Groq ili Gemini)
streamlit run app.py
```
Radi i bez ključa (generički nazivi jedinica, bez čitanja PDF-a) — dobro za probu: napišite `primer`.

### Besplatni LLM-ovi
| `LLM_PROVIDER` | Ključ | Zašto |
|---|---|---|
| `groq` | [console.groq.com](https://console.groq.com/keys) | najbrži |
| `gemini` | [aistudio.google.com](https://aistudio.google.com/apikey) | najveći kontekst (ceo glasnik) |
| `openrouter` | [openrouter.ai](https://openrouter.ai/keys) | `:free` modeli |
| `ollama` | — | lokalno, offline |

## Struktura
```
planer/
  modeli.py                 Program, Tema, Čas, Kalendar
  kalendar.py               praznici RS, Uskrs, nastavni dani, slotovi časova
  podrazumevani_kalendar.py približan kalendar ako nema zvaničnog JSON-a
  raspodela.py              usklađivanje fonda, provere, globalni/operativni plan
  llm.py                    jedan klijent za Groq/Gemini/OpenRouter/Ollama
  glasnik_parser.py         DOCX Pravilnika → programi (bez LLM-a)
  ekstrakcija.py            PDF glasnika → odeljak predmeta → JSON program (LLM)
  pismo.py                  ćirilica ↔ latinica
  kompetencije.py           MK i predmeti za povezivanje (glasnik + logika, sa obrazloženjem)
  provera.py                automatske provere gotovog plana
  agent.py                  agent: LLM vodi korake, alati računaju
  formule.py                x2 → x², log2 → log₂, sqrt → √, <= → ≤
  sadrzaj.py                LLM: nazivi jedinica, ishodi, metode, oblici rada
  intervju.py               razgovor sa nastavnikom (lista pitanja + tumačenje)
  izvoz.py                  DOCX i XLSX
app.py                      Streamlit chat aplikacija
data/                       primer programa, zvanični kalendari (JSON)
tests/                      pytest
```

## Testovi
```bash
python -m pytest -q
```
