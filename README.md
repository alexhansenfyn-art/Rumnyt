# Rumnyt

Søstersite til [ainyheder.com](https://ainyheder.com) — dagens rumfartsnyheder på kort, letlæst dansk.

## Filer

- `index.html` — forside. Al CSS og JS er inline. Henter `data/artikler.json`.
- `om.html` — om-side.
- `data/artikler.json` — indholdet. Samme skema som ainyheder.com (rubrik, resume_da, sektioner, noegletal, detaljer, betydning, pointer, prio).

## Kør lokalt

Forsiden bruger `fetch()`, så den skal serveres over HTTP — dobbeltklik på filen virker ikke:

```
python3 -m http.server 8000
```

Åbn derefter http://localhost:8000

## Status

Indholdet er demo-data. Næste skridt er at koble den samme indsamlings- og
genfortællingspipeline på, som kører AI-nyheder, med rumfartskilder
(NASA, ESA, SpaceNews, NASASpaceflight, NOAA Space Weather m.fl.).
