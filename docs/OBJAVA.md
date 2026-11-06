# Objava na Streamlit Community Cloud (besplatno, može sa telefona)

Aplikacija dobija stalnu adresu, npr. `https://napravi-plan.streamlit.app`.

## Koraci
1. Otvorite **https://share.streamlit.io** i izaberite **Continue with GitHub**
   (prijavite se GitHub nalogom *AsadGudzevic94*).
2. Dozvolite Streamlit-u pristup repozitorijumu **napravi-plan** kada pita.
3. Pritisnite **Create app** → **Deploy a public app from GitHub** i popunite:
   - **Repository:** `AsadGudzevic94/napravi-plan`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** npr. `napravi-plan` (ako je zauzeto, dodajte nešto: `napravi-plan-srbija`)
4. Otvorite **Advanced settings**:
   - **Python version:** 3.12
   - **Secrets:** nalepite (sa vašim ključem sa https://console.groq.com/keys):
     ```toml
     LLM_PROVIDER = "groq"
     GROQ_API_KEY = "gsk_..."
     ```
5. **Deploy**. Prvo pokretanje traje 2–3 minuta.

## Dobro je znati
- Ključ upisan u Secrets vidi samo aplikacija — ne nalazi se u kodu ni na GitHubu.
- Javnu aplikaciju može da koristi svako ko ima adresu, i troši vaš besplatni Groq limit.
  Ako želite da je koriste samo određeni ljudi: u aplikaciji **Share** → **Only specific people**
  i upišite njihove e-mail adrese (besplatni nalog dozvoljava jednu privatnu aplikaciju).
- Bez ključa aplikacija i dalje radi, u načinu „Korak po korak (bez AI)“.
- Svaki novi commit na izabranu granu automatski osvežava aplikaciju.
- Aplikacija „zaspi“ posle nekoliko dana bez korišćenja; probudi se klikom na dugme na stranici.
