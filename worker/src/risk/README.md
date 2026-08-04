# Risk Engine V1

Risk Engine V1 jest niezależną, działającą lokalnie warstwą interpretacji danych. Odczytuje `ergonomics-metrics.json` oraz **jawnie wskazany** profil progów i zapisuje `risk-assessment.json`. Nie łączy się z Supabase, nie korzysta z GPU i nie zmienia statusu analizy.

Silnik wykonuje techniczny screening. Nie jest diagnozą, certyfikacją ani automatyczną decyzją BHP. Nie implementuje RULA, REBA ani innej metody normatywnej. Profil używany produkcyjnie musi zostać przygotowany i zatwierdzony przez kompetentnego ergonomistę lub specjalistę BHP.

## Metryka a klasyfikacja

Ergonomics Metrics Engine dostarcza pomiar geometryczny, jego ważność i techniczny wskaźnik jakości. Risk Engine nie zmienia pomiaru. Dla każdej ważnej wartości wybiera pasmo z profilu, zapisuje poziom, score, wagę oraz wynik ważony. Brak lub odrzucona wartość zawsze daje `insufficient_data`, nigdy `low`.

Dozwolone poziomy klasyfikacji to:

- `low`
- `moderate`
- `high`
- `critical`
- `insufficient_data`
- `disabled` (tylko dla metryki wyłączonej profilem)

Nazwy opisują poziomy technicznej klasyfikacji profilu, a nie bezpieczeństwo lub zgodność stanowiska.

## Profil progów

CLI zawsze wymaga osobnego pliku profilu. W kodzie nie ma profilu domyślnego ani ukrytych progów. Plik `worker/tests/fixtures/risk-profile-test.json` jest wyłącznie syntetycznym fixture testowym, nie jest ergonomicznie zwalidowany i nie wolno używać go produkcyjnie.

Główne pola profilu:

```json
{
  "schema_version": "1.0",
  "profile_id": "jawny-identyfikator",
  "profile_name": "Nazwa profilu",
  "profile_version": "1.0.0",
  "status": "development",
  "normative_method": null,
  "description": "Opis przeznaczenia",
  "disclaimer": "Ograniczenia profilu",
  "metrics": {},
  "zones": {},
  "summary_rule": {
    "minimum_sequence_seconds": 0.5,
    "minimum_exposure_ratio": 0.05,
    "percentile_for_summary": 95
  },
  "overall": {
    "minimum_data_coverage": 0.65,
    "aggregation": "weighted_average_with_peak_guard",
    "peak_guard": {
      "enabled": true,
      "minimum_level": "high",
      "minimum_exposure_ratio": 0.1
    },
    "score_bands": []
  },
  "key_frames": {
    "minimum_time_separation_seconds": 1.0
  }
}
```

Każda metryka deklaruje `enabled`, `direction`, `weight`, `minimum_valid_ratio` i pełne, nienakładające się `bands`. Kierunki to `higher_is_worse`, `lower_is_worse` oraz `outside_range_is_worse`; ostatni wymaga dodatkowo jawnego `preferred_range`. Zakres dolny jest domknięty, górny otwarty, z wyjątkiem ostatniego pasma. Skrajne pasma muszą używać `null`, dzięki czemu profil pokrywa każdą skończoną wartość.

`overall.score_bands` jawnie mapuje znormalizowany wynik 0–1 na poziom ogólny. Dzięki temu także progi agregacji ogólnej nie są zaszyte w kodzie.

Profil odwołujący się do aktywnej metryki, która nie występuje w całym dokumencie wejściowym, jest odrzucany jako niekompatybilny. Brak tej metryki tylko w części klatek pozostaje zwykłym `insufficient_data`. Dodatkowe metryki wejściowe, których profil nie używa, są ignorowane.

## Czas ekspozycji

Silnik preferuje skończone, ściśle rosnące timestampy kolejnych klatek. Czas klatki odpowiada różnicy do następnego timestampu; dla ostatniej klatki używana jest mediana wcześniejszych różnic. Jeżeli timestampy są niepełne lub niepoprawne, silnik może użyć jawnego FPS z dokumentu (`fps`, `source.fps` albo `configuration.source_fps`) i zapisuje `fps_fallback` oraz przyczynę fallbacku. Gdy nie ma ani poprawnych timestampów, ani FPS, czas jest oznaczony jako niedostępny, a podsumowania nie są sztucznie klasyfikowane jako `low`.

Dla każdej metryki zapisywane są czasy poszczególnych poziomów, udziały w całym **ważnym** czasie oraz najdłuższe ciągłe sekwencje. Klatki nieważne nie są czasem poziomu `low`.

## Agregacja

Końcowy poziom metryki jest najwyższym poziomem podwyższonym, który spełnia co najmniej jeden jawny warunek profilu: minimalny udział czasu albo minimalny czas ciągłej sekwencji. Percentyl jest zapisywany w statystykach i przyczynach decyzji. Pojedyncze krótkie maksimum nie determinuje automatycznie całej analizy. Pokrycie niższe od `minimum_valid_ratio` daje `insufficient_data`.

Strefy pochodzą wyłącznie z mapowania `zones` profilu. Strefa zawiera liczbę metryk aktywnych i wystarczających, pokrycie, najwyższy poziom, sumę wyników ważonych oraz wynik znormalizowany. Jeżeli więcej niż połowa aktywnych metryk strefy ma niewystarczające dane, strefa otrzymuje `insufficient_data`.

Ogólny wynik używa jedynej strategii V1: `weighted_average_with_peak_guard`. Jest to iloraz sumy końcowych wyników ważonych i ich jawnego maksimum, ograniczony do 0–1. Profil mapuje ten wynik przez `score_bands`. Jeżeli całkowite pokrycie jest zbyt niskie, wynik ogólny to `insufficient_data`. Peak guard może podnieść poziom ogólny do jawnie skonfigurowanego minimum, gdy utrwalona ekspozycja metryki na tym lub wyższym poziomie przekroczy próg profilu. Każda taka decyzja jest zapisana w `decision_reasons`.

## Kluczowe klatki

Silnik nie generuje obrazów. Wybiera wyłącznie metadane kandydatów z poziomem `high` lub `critical`, preferując wyższą wagę wyniku i jakość. Obowiązuje limit 3 klatek na metrykę, 10 dla analizy, deduplikacja indeksu klatki oraz minimalny odstęp czasu z profilu.

## Uruchomienie

Z katalogu głównego repozytorium:

```powershell
worker\.venv\Scripts\python.exe -m worker.src.risk.cli `
  input_ergonomics_metrics.json `
  input_risk_profile.json `
  output_risk_assessment.json
```

Publiczne API Pythona:

```python
from worker.src.risk import process_risk_document, process_risk_file
```

## Testy

```powershell
worker\.venv\Scripts\python.exe -m pytest `
  worker\tests\ergonomics `
  worker\tests\risk `
  -q
```

## Ograniczenia

- wejście powstaje głównie z analizy obrazu 2D;
- zasłonięte części ciała mogą nie dostarczać danych;
- wynik zależy od jakości pomiarów wejściowych i zatwierdzonego profilu;
- `quality` nie jest prawdopodobieństwem ani dokładnością modelu;
- fixture testowy nie posiada wartości normatywnej;
- brak RULA, REBA, raportu PDF oraz automatycznej integracji z kolejką;
- ostateczna interpretacja wymaga przeglądu specjalisty.
