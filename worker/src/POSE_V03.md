# Ergonomia AI Worker V0.3

Wersja workerowa: `0.3.0-beta.1`. Wersja kontraktu Pose: `pose-v3.1` / JSON `3.1`.

## Tracking osoby

Tracker ma jawne stany `TRACKED`, `PARTIAL`, `OCCLUDED`, `LOST` i
`REACQUIRING`. Tożsamość kandydata jest oceniana z użyciem IoU, przesunięcia
środka, zmiany skali bbox oraz sygnatury proporcji barków, bioder i tułowia.
Po `LOST` nowy kandydat musi przejść kilka kolejnych potwierdzeń. W stanie
`LOST` lub `REACQUIRING` punkty nie są rysowane ani interpolowane. RTMW nadal
otrzymuje wyłącznie bbox z YOLOX — nie ma fallbacku pełnej klatki.

## Walidacja ciała i wyjście z kadru

Każdy z 23 głównych punktów ciała ma `raw_confidence`, techniczny `quality`,
`valid` i kontrolowany kod odrzucenia. Kontrolowane są granice obrazu, strefa
przy krawędzi, prędkość, przyspieszenie oraz długość i zmiana kierunku kości.
Widoczne części ciała mogą pozostać poprawne w stanie `PARTIAL`; brakujące
punkty i zależne kości są ukrywane.

Profil proporcji powstaje wyłącznie ze stabilnych klatek `TRACKED`. Długości
kości są normalizowane do wysokości bbox, agregowane medianą i chronione przez
MAD przed outlierami. Overlay rysuje kość tylko przy poprawnych endpointach,
poprawnej długości i współrzędnych wewnątrz obrazu.

## Wygładzanie

Po zebraniu trajektorii działa filtr medianowy oraz dwukierunkowe EMA. Luki są
interpolowane tylko pomiędzy dwoma poprawnymi punktami, maksymalnie przez dwie
klatki, przy ograniczonym przemieszczeniu. `LOST` i `REACQUIRING` są twardymi
granicami segmentu.

## Dłonie

MediaPipe pozostaje osobnym źródłem 21 landmarków na dłoń. Przypisanie stron
łączy nadgarstek i łokieć RTMW, odległość śródręcza, handedness jako miękki
sygnał oraz historię środka dłoni. Walidacja obejmuje skalę dłoni, profil kości,
prędkość, orientację, głębokość i każdy segment palca. Pojedynczy odrzucony
fingertip nie ukrywa poprawnej dłoni. Powrót po `HAND_LOST` przechodzi przez
`HAND_REACQUIRING`.

Wygładzanie dłoni jest offline i warstwowe: korzeń dłoni jest filtrowany lżej,
a końcówki palców mocniej. Linie są rysowane wyłącznie dla zaakceptowanych
punktów i segmentów.

## Grip i hand-object interaction

Deterministyczne stany chwytu to `OPEN`, `PARTIALLY_CLOSED`, `CLOSED`, `PINCH`
i `UNKNOWN`. Cechy obejmują zamknięcie dłoni, odległości kciuka, zgięcie palców,
orientacje i stabilność.

Holding V1 korzysta z geometrii chwytu, jakości, stabilności oraz — jeśli jest
dostępna — bliskości klasy COCO wykrytej przez tę samą instancję YOLOX. Brak
klasy COCO nie oznacza braku przedmiotu. Stany to `NOT_HOLDING`,
`POSSIBLE_HOLDING`, `LIKELY_HOLDING` i `UNKNOWN`. Epizod wymaga minimalnego
czasu potwierdzenia; krótkie luki `UNKNOWN` i krótkie przerwy przed
potwierdzonym release mogą zostać scalone. Czas wynika z timestampów klatek,
bez kumulacyjnego zaokrąglania. Bimanual holding wymaga zgodnej detekcji obiektu
po obu stronach albo — gdy obiekt nie ma klasy COCO — jednoczesnego
potwierdzonego chwytu i bliskości dłoni. Drugi wariant pozostaje oznaczony jako
kandydat nieznanego obiektu.

Silnik nie estymuje masy, siły chwytu, momentu ani obciążenia zewnętrznego.
`external_load_known` pozostaje `false`.

## Jakość i output

Każda klatka otrzymuje stan `GOOD`, `ACCEPTABLE`, `POOR` albo `INVALID` z
jawnymi komponentami: ciało, dłonie, ostrość, ekspozycja i tracking. Mały
`pose-diagnostics.json` zawiera podsumowanie trackingu, jakości, dłoni, holding,
odrzucenia i czasy etapów. Pełne dane pozostają w `pose-keypoints.json`.

Ergonomics Metrics Engine akceptuje schematy Pose `3.0` i `3.1`. Wersja 3.1
przekazuje jawny dependency graph, odrzuca izolowane skoki metryk i wylicza
techniczne cechy czasu poprawnych danych oraz powtarzalności. Nie dodaje progów
ryzyka.

## Lokalna walidacja

Z katalogu głównego repozytorium:

```powershell
worker\.venv\Scripts\python.exe worker\tools\analyze_local_video.py `
  --input "D:\film.mp4" `
  --output "D:\wynik" `
  --debug-overlay `
  --ergonomics
```

Opcja `--no-hands` wyłącza MediaPipe i holding. Narzędzie nie łączy się z
Supabase i nie kopiuje filmu wejściowego. Korzysta z tego samego kodu Pose co
worker kolejki.

## Ograniczenia

- Analiza jest oparta głównie o obraz 2D i zależy od kadru, oświetlenia i
  zasłonięć.
- Geometryczny tracking nie jest pełnym modelem ReID; po długim `LOST`
  reacquisition jest konserwatywnie potwierdzany, ale scena wieloosobowa nadal
  może być niejednoznaczna.
- YOLOX/COCO nie zna wielu obiektów przemysłowych; takie obiekty pozostają
  nieklasyfikowane.
- Holding jest technicznym wynikiem probabilistycznym, nie pomiarem siły ani
  masy i nie zastępuje oceny specjalisty.
