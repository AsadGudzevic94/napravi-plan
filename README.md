# 📘 Napravi plan

Besplatna aplikacija koja nastavniku osnovne i srednje škole pravi **globalni (godišnji)**
i **operativni (mesečni)** plan rada na osnovu **službenog glasnika** (plan i program nastave
i učenja), školskog kalendara i rasporeda časova — kroz kratak razgovor.

Cilj, arhitektura i plan razvoja: **[docs/PLAN.md](docs/PLAN.md)**

## Kako radi
1. Aplikacija pita: tip škole, razred, predmet, smer.
2. Učitate PDF glasnika → LLM izvuče teme, ishode i broj časova (ili upišete teme ručno / „primer“).
3. Potvrdite/izmenite teme, nedeljni fond, dane kada držite čas i školski kalendar.
4. **Kod** (ne LLM) tačno izračuna sve datume časova (praznici, raspusti, pravoslavni Uskrs)
   i rasporedi teme po mesecima; ako fond ne odgovara kalendaru, vi birate strategiju.
5. LLM napiše nazive nastavnih jedinica, ishode po času, metode i oblike rada.
6. Preuzmete **.docx** (globalni i operativni) ili **.xlsx** (sve).

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
  ekstrakcija.py            PDF glasnika → odeljak predmeta → JSON program
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
