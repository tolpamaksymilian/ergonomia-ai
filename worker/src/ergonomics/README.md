# Ergonomics Metrics Engine V1

Moduł odczytuje plik `pose-keypoints.json` w schemacie Pose Pipeline V3.0 lub V3.1 i tworzy
`ergonomics-metrics.json` z surowymi pomiarami geometrycznymi dla każdej klatki
aktywnego fragmentu. Nie wykonuje punktacji RULA/REBA, progów ostrzegawczych,
zapisu do Supabase ani interpolacji metryk.

## Wejście i wyjście

Obsługiwane wejście ma `schema_version: "3.0"` albo `"3.1"`. Punkty ciała są odczytywane z
`frames[].smoothed_keypoints` oraz `frames[].scores` w formacie COCO WholeBody
133. Próg jakości pochodzi z `configuration.keypoint_threshold`; przy jego braku
stosowana jest wartość V3.0 `0.78`.

Punkty dłoni pochodzą wyłącznie z zatwierdzonego wyniku V3.0:
`frames[].left_hand/right_hand.landmarks_2d`. Dłoń jest używana tylko, gdy
`visible` ma wartość `true`. Silnik nie wraca do punktów dłoni RTMW zapisanych w
`raw_keypoints`. Klatka dłoni oznaczona przez V3.0 jako `interpolated` jest już
zatwierdzonym wynikiem źródłowego pipeline'u; silnik nie tworzy żadnej dodatkowej
interpolacji.

Wyjście zawiera metryki klatkowe z polami `value`, `valid`, `quality`,
`source_points` i `rejection_reason`, a także podsumowania liczone wyłącznie z
poprawnych wartości. `quality` jest minimum jakości wszystkich wymaganych
punktów (oraz jakości dłoni, gdy dotyczy), ograniczonym do 0–1. Jest to techniczny
wskaźnik jakości danych, nie skalibrowane prawdopodobieństwo.

Dla Pose 3.1 wynik zawiera także jawny graf zależności punktów i kości,
odrzucanie izolowanych skoków o limitach właściwych dla danej metryki,
`movement_features`, techniczny czas ciągłej dostępności poprawnych danych oraz
`holding_metric_exposure`. Ostatnie pole mówi wyłącznie, przez jaki czas podczas
potwierdzonego chwytu odpowiednia metryka postawy była poprawna. Nie stosuje
progów ryzyka i nie klasyfikuje pozycji jako dobrej ani złej.

## Definicje i konwencje

Analiza używa geometrii 2D w pikselach filmu źródłowego; oś X rośnie w prawo, a
oś Y w dół.

- `trunk_inclination_deg`: nieukierunkowane odchylenie osi środek bioder–środek
  barków od pionu, 0–90°.
- `neck_flexion_deg`: kąt pomiędzy osią tułowia i odcinkiem środek barków–nos,
  0° dla współliniowej głowy i tułowia.
- `*_upper_arm_elevation_deg`: kąt ramienia bark–łokieć względem skierowanej w dół
  osi tułowia, 0° dla ramienia opuszczonego wzdłuż tułowia.
- `*_elbow_flexion_deg`: `180° - kąt bark–łokieć–nadgarstek`; wyprost to 0°,
  zgięcie pod kątem prostym to 90°.
- `*_forearm_inclination_deg`: nieukierunkowane odchylenie przedramienia od
  pionu, 0–90°.
- `*_wrist_flexion_deg`: kąt między wektorem łokieć–nadgarstek ciała a osią
  `wrist–middle_mcp` zatwierdzonej dłoni.
- `*_hand_closure_ratio`: `1 - średnia(długość bezpośrednia MCP–tip / długość
  łańcucha MCP–PIP–DIP–tip)` dla czterech palców; 0 oznacza palce proste, a
  wartości bliższe 1 większe zamknięcie.
- `*_pinch_distance_ratio`: odległość `thumb_tip–index_tip` podzielona przez
  medianę odległości definiujących rozmiar dłoni (`wrist–middle_mcp`,
  `index_mcp–pinky_mcp`, `wrist–index_mcp`, `wrist–pinky_mcp`).

Współrzędne `null`, NaN/Infinity, punkt `[0, 0]`, punkty poniżej progu jakości,
zerowe wektory i niewiarygodne dłonie dają metrykę `valid: false`. Braki nie są
uzupełniane z poprzedniej ani następnej klatki.

## Uruchomienie

Z katalogu głównego repozytorium:

```powershell
worker\.venv\Scripts\python.exe -m worker.src.ergonomics.cli `
  worker\data\pose-keypoints.json `
  worker\outputs\ergonomics-metrics.json
```

Instalacja zależności testowych i uruchomienie testów:

```powershell
worker\.venv\Scripts\python.exe -m pip install -r worker\requirements-dev.txt
worker\.venv\Scripts\python.exe -m pytest worker\tests\ergonomics -q
```

Moduł korzysta wyłącznie ze standardowej biblioteki Pythona i NumPy. Testy nie
ładują modeli, OpenCV, Supabase, MediaPipe, GPU ani zasobów sieciowych.
