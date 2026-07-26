# Rumnyt

Søstersite til [ainyheder.com](https://ainyheder.com) — rumfartsnyheder på kort, letlæst dansk.

Live: https://alexhansenfyn-art.github.io/Rumnyt/

## Filer

- `index.html` — forside. Al CSS og JS er inline. Henter `data/artikler.json`.
- `om.html` — om-side.
- `byg_nyheder.py` — henter RSS fra rigtige rumfartskilder og genfortæller dem med DeepSeek.
- `data/artikler.json` — indholdet. Skrives af scriptet.

## Kør pipelinen lokalt

```bash
pip install -r requirements.txt

# 1. Læg nøglen i .env (aldrig i koden — .env er gitignored)
cp .env.eksempel .env        # og indsæt din nøgle

# 2. Tjek at kilderne svarer — koster ingenting
python byg_nyheder.py --test-feeds

# 3. Lille testkørsel — genfortæller 3 artikler
python byg_nyheder.py --antal 3

# 4. Normal kørsel
python byg_nyheder.py
```

Herefter: `git add data/artikler.json && git commit && git push` — GitHub Pages
opdaterer sig selv inden for et minut eller to.

## Sådan undgås opdigtet indhold

Modellen skriver ikke artikler ud af ingenting. Hvert emne stammer fra et rigtigt
RSS-punkt, og `link`, `kilde`, `dato` og originaltitel tages altid fra feedet —
aldrig fra modellen. Modellen får kildeteksten og må kun genfortælle den, og er
instrueret i at lade felter stå tomme frem for at gætte.

Det fjerner ikke risikoen for fejl i selve genfortællingen. Stikprøvekontrol mod
kildelinket er stadig nødvendig, før noget bør betragtes som pålideligt.

## Kør lokalt i browseren

Forsiden bruger `fetch()`, så den skal serveres over HTTP:

```bash
python -m http.server 8000
```

## Næste skridt

- `uge.html` (linket i menuen findes endnu ikke)
- GitHub Actions-workflow, så pipelinen kører automatisk med nøglen i Actions Secrets
