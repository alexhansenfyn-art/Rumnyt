#!/usr/bin/env python3
"""
Rumnyt — hent rigtige rumfartsnyheder og genfortæl dem på letlæst dansk.

Kør lokalt:
    pip install -r requirements.txt
    python byg_nyheder.py --test-feeds     # tjek at kilderne svarer
    python byg_nyheder.py --antal 3        # genfortæl 3 artikler (billig test)
    python byg_nyheder.py                  # normalt kør

API-nøglen læses fra miljøvariablen DEEPSEEK_API_KEY eller fra en .env-fil
i samme mappe. .env er i .gitignore og må ALDRIG committes.

Vigtigt princip: modellen opdigter ikke artikler. Hver artikel stammer fra
et rigtigt RSS-punkt, og link, kilde og dato tages altid fra feedet — aldrig
fra modellen. Modellen må kun genfortælle den tekst, den får.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests

ROT = Path(__file__).parent
UD = ROT / "data" / "artikler.json"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"

MAX_ARTIKLER = 100      # hvor mange der maks. gemmes i alt
MAX_NYE_PR_KOERSEL = 12  # koster penge — hold den lav under test
MAX_ALDER_DAGE = 5

KILDER = [
    ("NASA",            "https://www.nasa.gov/news-release/feed/"),
    ("ESA",             "https://www.esa.int/rssfeed/Our_Activities/Space_Science"),
    ("SpaceNews",       "https://spacenews.com/feed/"),
    ("NASASpaceflight", "https://www.nasaspaceflight.com/feed/"),
    ("Ars Technica",    "https://feeds.arstechnica.com/arstechnica/space"),
    ("Phys.org Rum",    "https://phys.org/rss-feed/space-news/"),
    ("Sky & Telescope", "https://skyandtelescope.org/feed/"),
]

KATEGORIER = ["Opsendelser", "Satellitter", "Missioner", "Astronomi", "Rumvejr", "Forskning", "Politik & penge"]

SYSTEM = """Du er redaktør på Rumnyt, et dansk nyhedssite om rumfart for almindelige mennesker.

Du får én rigtig nyhedsartikel. Din opgave er at genfortælle den på kort, letlæst dansk.

ABSOLUTTE REGLER:
- Opfind ALDRIG fakta, tal, datoer, navne eller citater. Brug kun det, der står i kildeteksten.
- Er kildeteksten for kort til et felt, så lad feltet være tomt eller listen tom. Det er helt i orden.
- Skriv i dine egne ord. Oversæt ikke ordret, og kopier ikke hele sætninger fra kilden.
- Skriv til en voksen uden teknisk baggrund. Ingen jargon. Korte sætninger. Ingen fyld.
- Skriv på dansk. Brug danske tal- og datoformater.

Svar KUN med et JSON-objekt med præcis disse nøgler:

{
  "rubrik": "max 60 tegn, konkret, ingen clickbait",
  "resume_da": "1-2 sætninger, max 200 tegn",
  "kategori": "én af: %s",
  "sektioner": [{"overskrift": "3-5 ord", "tekst": "2-4 sætninger. Marker de vigtigste tal med **stjerner**"}],
  "noegletal": [{"tal": "fx '350 km'", "label": "hvad tallet betyder, max 5 ord"}],
  "detaljer": ["korte faktapunkter fra kilden"],
  "betydning": "1-2 sætninger: hvorfor er det relevant for en almindelig dansker?",
  "pointer": ["3-4 meget korte punkter"],
  "prio": 1-10, hvor vigtig historien er for almindelige mennesker
}

2-4 sektioner. 0-3 nøgletal — kun tal der faktisk står i kilden.""" % ", ".join(KATEGORIER)


# ---------------------------------------------------------------- hjælpere

def laes_env():
    """Læs DEEPSEEK_API_KEY fra miljø eller .env."""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"].strip()
    envfil = ROT / ".env"
    if envfil.exists():
        for linje in envfil.read_text(encoding="utf-8").splitlines():
            linje = linje.strip()
            if linje.startswith("DEEPSEEK_API_KEY"):
                return linje.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def ren_tekst(html, maks=6000):
    """Strip HTML-tags og klip til en fornuftig længde."""
    tekst = re.sub(r"<script.*?</script>", " ", html or "", flags=re.S | re.I)
    tekst = re.sub(r"<style.*?</style>", " ", tekst, flags=re.S | re.I)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    tekst = re.sub(r"&nbsp;?", " ", tekst)
    tekst = re.sub(r"\s+", " ", tekst).strip()
    return tekst[:maks]


def entry_dato(e):
    for felt in ("published_parsed", "updated_parsed"):
        v = getattr(e, felt, None)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc)
    return None


def hent_feeds(verbose=True):
    """Returner liste af rå nyhedspunkter fra alle kilder."""
    graense = datetime.now(timezone.utc) - timedelta(days=MAX_ALDER_DAGE)
    punkter, status = [], []

    for navn, url in KILDER:
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Rumnyt/1.0 (+https://rumnyt.dk)"})
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            nye = 0
            for e in feed.entries:
                d = entry_dato(e)
                if not d or d < graense:
                    continue
                brodtekst = ""
                if getattr(e, "content", None):
                    brodtekst = e.content[0].get("value", "")
                brodtekst = brodtekst or getattr(e, "summary", "") or ""
                punkter.append({
                    "titel": (getattr(e, "title", "") or "").strip(),
                    "link": (getattr(e, "link", "") or "").strip(),
                    "dato": d.isoformat(),
                    "kilde": navn,
                    "resume": ren_tekst(getattr(e, "summary", ""), 400),
                    "_tekst": ren_tekst(brodtekst),
                })
                nye += 1
            status.append((navn, "ok", f"{nye} nye af {len(feed.entries)}"))
        except Exception as exc:
            status.append((navn, "FEJL", str(exc)[:90]))

    if verbose:
        print("\nKilder:")
        for navn, tilstand, note in status:
            mark = "  ok " if tilstand == "ok" else "  !! "
            print(f"{mark}{navn:<18} {note}")
        print()

    # kun punkter med link og nok tekst til at genfortælle
    punkter = [p for p in punkter if p["link"] and len(p["_tekst"]) > 250]
    punkter.sort(key=lambda p: p["dato"], reverse=True)
    return punkter


def genfortael(punkt, noegle):
    """Kald DeepSeek. Returnerer dict eller None ved fejl."""
    bruger = (
        f"KILDE: {punkt['kilde']}\n"
        f"OVERSKRIFT: {punkt['titel']}\n\n"
        f"ARTIKELTEKST:\n{punkt['_tekst']}"
    )
    krop = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": bruger},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 2000,
    }
    for forsoeg in range(3):
        try:
            r = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {noegle}", "Content-Type": "application/json"},
                json=krop, timeout=120,
            )
            if r.status_code == 429:
                time.sleep(5 * (forsoeg + 1))
                continue
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as exc:
            if forsoeg == 2:
                print(f"    fejl: {str(exc)[:120]}")
                return None
            time.sleep(3)
    return None


def saml(punkt, svar):
    """Byg den endelige artikel. Fakta-felter kommer fra feedet, ikke fra modellen."""
    rubrik = (svar.get("rubrik") or "").strip()
    if not rubrik:
        return None
    kat = svar.get("kategori")
    return {
        "titel":     punkt["titel"],
        "link":      punkt["link"],
        "dato":      punkt["dato"],
        "kilde":     punkt["kilde"],
        "resume":    punkt["resume"],
        "kategori":  kat if kat in KATEGORIER else "Missioner",
        "rubrik":    rubrik[:80],
        "resume_da": (svar.get("resume_da") or "").strip(),
        "sektioner": svar.get("sektioner") or [],
        "noegletal": (svar.get("noegletal") or [])[:3],
        "detaljer":  (svar.get("detaljer") or [])[:6],
        "betydning": (svar.get("betydning") or "").strip(),
        "pointer":   (svar.get("pointer") or [])[:4],
        "prio":      max(1, min(10, int(svar.get("prio") or 5))),
    }


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-feeds", action="store_true", help="hent kun feeds, kald ikke API'et")
    ap.add_argument("--antal", type=int, default=MAX_NYE_PR_KOERSEL, help="maks. nye artikler at genfortælle")
    ap.add_argument("--dry-run", action="store_true", help="skriv ikke til artikler.json")
    args = ap.parse_args()

    punkter = hent_feeds()
    print(f"{len(punkter)} brugbare nyhedspunkter fra de sidste {MAX_ALDER_DAGE} dage.")

    if args.test_feeds:
        for p in punkter[:15]:
            print(f"  [{p['kilde']}] {p['titel'][:80]}")
        return

    noegle = laes_env()
    if not noegle:
        sys.exit("Ingen API-nøgle fundet. Sæt DEEPSEEK_API_KEY som miljøvariabel "
                 "eller læg den i en .env-fil ved siden af dette script.")

    gamle = {"artikler": []}
    if UD.exists():
        try:
            gamle = json.loads(UD.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    kendte = {a.get("link") for a in gamle.get("artikler", [])}

    nye_punkter = [p for p in punkter if p["link"] not in kendte][: args.antal]
    print(f"Genfortæller {len(nye_punkter)} nye artikler med {MODEL} …\n")

    nye = []
    for i, p in enumerate(nye_punkter, 1):
        print(f"  {i}/{len(nye_punkter)} [{p['kilde']}] {p['titel'][:60]}")
        svar = genfortael(p, noegle)
        if not svar:
            continue
        art = saml(p, svar)
        if art:
            nye.append(art)
            print(f"        → {art['rubrik']}")

    alle = nye + gamle.get("artikler", [])
    alle.sort(key=lambda a: a.get("dato", ""), reverse=True)
    alle = alle[:MAX_ARTIKLER]

    ud = {
        "opdateret": datetime.now(timezone.utc).isoformat(),
        "antal": len(alle),
        "artikler": alle,
    }

    if args.dry_run:
        print(f"\n[dry-run] Ville skrive {len(alle)} artikler ({len(nye)} nye).")
        return

    UD.parent.mkdir(parents=True, exist_ok=True)
    UD.write_text(json.dumps(ud, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSkrev {len(alle)} artikler til {UD.relative_to(ROT)} ({len(nye)} nye).")


if __name__ == "__main__":
    main()
