"""Jedan klijent za sve besplatne LLM-ove (OpenAI-kompatibilan /chat/completions).

Podešavanje kroz promenljive okruženja (ili .env):
    LLM_PROVIDER = groq | gemini | openrouter | ollama
    LLM_MODEL    = (opciono) naziv modela, inače podrazumevani za providera
    GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import requests

PROVIDERI = {
    "groq": {
        "url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "kljuc": "GROQ_API_KEY",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "kljuc": "GEMINI_API_KEY",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "kljuc": "OPENROUTER_API_KEY",
    },
    "ollama": {
        "url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
        "kljuc": None,
    },
}


def _ucitaj_env(putanja: str = ".env") -> None:
    if not os.path.exists(putanja):
        return
    for red in open(putanja, encoding="utf-8"):
        red = red.strip()
        if red and not red.startswith("#") and "=" in red:
            k, v = red.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLMGreska(RuntimeError):
    pass


@dataclass
class LLM:
    provider: str
    model: str
    url: str
    kljuc: str | None
    timeout: int = 120

    @classmethod
    def iz_okruzenja(cls) -> "LLM | None":
        """Vrati klijent ili None ako LLM nije podešen (aplikacija tada radi bez LLM-a)."""
        _ucitaj_env()
        provider = os.environ.get("LLM_PROVIDER", "").lower().strip()
        if not provider:
            for p, cfg in PROVIDERI.items():  # auto: prvi provider čiji ključ postoji
                if cfg["kljuc"] and os.environ.get(cfg["kljuc"]):
                    provider = p
                    break
        if provider not in PROVIDERI:
            return None
        cfg = PROVIDERI[provider]
        kljuc = os.environ.get(cfg["kljuc"]) if cfg["kljuc"] else None
        if cfg["kljuc"] and not kljuc:
            return None
        return cls(provider=provider, model=os.environ.get("LLM_MODEL") or cfg["model"],
                   url=os.environ.get("LLM_BASE_URL") or cfg["url"], kljuc=kljuc)

    def chat(self, poruke: list[dict], json_odgovor: bool = False, temperatura: float = 0.2,
             max_tokena: int = 4096) -> str:
        telo = {"model": self.model, "messages": poruke, "temperature": temperatura,
                "max_tokens": max_tokena}
        if json_odgovor and self.provider != "ollama":
            telo["response_format"] = {"type": "json_object"}
        zaglavlja = {"Content-Type": "application/json"}
        if self.kljuc:
            zaglavlja["Authorization"] = f"Bearer {self.kljuc}"
        for pokusaj in range(4):
            r = requests.post(f"{self.url}/chat/completions", json=telo, headers=zaglavlja,
                              timeout=self.timeout)
            if r.status_code == 429 or r.status_code >= 500:  # limit besplatnog plana → sačekaj
                time.sleep(2 ** (pokusaj + 1))
                continue
            if r.status_code != 200:
                raise LLMGreska(f"{self.provider} {r.status_code}: {r.text[:500]}")
            return r.json()["choices"][0]["message"]["content"] or ""
        raise LLMGreska(f"{self.provider}: previše zahteva (limit besplatnog plana), probajte kasnije.")

    def chat_alati(self, poruke: list[dict], alati: list[dict], temperatura: float = 0.1,
                   max_tokena: int = 2048) -> dict:
        """Jedan korak agenta: model vraća poruku sa tekstom i/ili pozivima alata (OpenAI format)."""
        telo = {"model": self.model, "messages": poruke, "tools": alati, "tool_choice": "auto",
                "temperature": temperatura, "max_tokens": max_tokena}
        zaglavlja = {"Content-Type": "application/json"}
        if self.kljuc:
            zaglavlja["Authorization"] = f"Bearer {self.kljuc}"
        for pokusaj in range(4):
            r = requests.post(f"{self.url}/chat/completions", json=telo, headers=zaglavlja, timeout=self.timeout)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** (pokusaj + 1))
                continue
            if r.status_code != 200:
                raise LLMGreska(f"{self.provider} {r.status_code}: {r.text[:500]}")
            return r.json()["choices"][0]["message"]
        raise LLMGreska(f"{self.provider}: previše zahteva (limit besplatnog plana), probajte kasnije.")

    def chat_json(self, sistem: str, korisnik: str, **kw) -> dict:
        tekst = self.chat([{"role": "system", "content": sistem},
                           {"role": "user", "content": korisnik}], json_odgovor=True, **kw)
        return izvuci_json(tekst)


def izvuci_json(tekst: str) -> dict:
    tekst = tekst.strip()
    tekst = re.sub(r"^```(?:json)?\s*|\s*```$", "", tekst)
    try:
        return json.loads(tekst)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", tekst, re.S)
        if m:
            return json.loads(m.group(0))
        raise LLMGreska(f"LLM nije vratio JSON: {tekst[:300]}")
