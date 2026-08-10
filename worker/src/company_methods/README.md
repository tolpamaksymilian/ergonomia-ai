# Company Methods Engine V1

`company-methods-v1.1-beta.1` jest lekkim, deterministycznym modułem CPU, który uzupełnia Risk Engine, RULA i REBA o metody zakładowe odtworzone z audytowanego skoroszytu `testy.xlsx`.

## Źródło reguł

Python i TypeScript czytają te same wersjonowane pliki w `method-specs/`. Skoroszyt nie jest bazą danych runtime. Pełny rejestr źródeł, komentarzy, lookupów i błędów znajduje się w `docs/methods/testy-xlsx-audit.md`.

## Metody

- OWAS: pozycja pleców, ramion i nóg może być wyprowadzona z danych wideo, jeśli dowody są wystarczające. Masa zawsze pochodzi od użytkownika albo z pomiaru. Lookup jest ścisły; 3133 pozostaje niejednoznaczne.
- EJMS: sekcja I używa postawy i zmian w czasie; dane o sile są manualne. Sekcja II może wykorzystywać częstotliwość i skręt, lecz kg/cm/m i jakość chwytu wymagają danych użytkownika lub kalibracji.
- Risk Score: skale i progi są źródłowe. Wzór E×S×P jest jawnie oznaczony `NORMALIZED_INTERPRETATION`, ponieważ komórki wartości ryzyka nie zawierają formuły.
- Czynniki mierzalne: dokładne granice P/Pmax oraz ważność +60 miesięcy.
- Chemia: część manualna. Automatyczny scoring jest wyłączony do czasu dostarczenia IN.06.13.

## Evidence

Każda wartość ma źródło: `VIDEO_DERIVED`, `USER_PROVIDED`, `MEASUREMENT`, `WORKBOOK_RULE` lub `UNKNOWN`. `UNKNOWN` nie jest zamieniane na zero ani poziom niski.

## Integracja

Report Worker tworzy i zapisuje prywatnie:

- `{user_id}/{analysis_id}/results/company-method-assessment.json`
- opcjonalne dane użytkownika: `{user_id}/{analysis_id}/results/company-method-inputs.json`

Uzupełnienie danych w Analysis Review Workspace przelicza część deterministyczną bez uruchamiania Pose/GPU. Report V2.1 prezentuje metody zakładowe oddzielnie.

## Testy

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests\company_methods -q
npm.cmd run test:analysis-review
```

Powtarzalny audyt XLSX (ZIP/XML, bez uruchamiania formuł):

```powershell
worker\.venv\Scripts\python.exe worker\tools\audit_company_workbook.py C:\ścieżka\do\testy.xlsx
```

Wyniki są screeningiem wspierającym i wymagają interpretacji przez kompetentnego specjalistę.
