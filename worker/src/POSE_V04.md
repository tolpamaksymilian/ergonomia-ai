# Pose Pipeline V4.0 beta

Worker `0.4.0-beta.1` zachowuje modele YOLOX-X, RTMW WholeBody i MediaPipe
Hands, ale dodaje nad ich wynikami konserwatywną warstwę biomechaniczną.
Wersja dokumentu pozy to `4.0`, a wersja pipeline'u to
`pose-v4.0-beta.1`.

## Architektura danych

Pipeline rozdziela trzy warstwy:

- **RAW** — niezmieniony wynik modeli, przechowywany diagnostycznie;
- **ANALYSIS** — punkty zaakceptowane przez walidację lokalną, łańcuchową,
  globalną i czasową; tylko ta warstwa zasila metryki;
- **RENDER** — widok jakościowo bramkowany, z krótkim fade ostatniej poprawnej
  geometrii. Render nigdy nie zmienia danych analitycznych.

Predykcja krótkoterminowa wyznacza expected position i pomaga odrzucić
teleportujący punkt. Ma jawne źródło `predicted`, nigdy nie jest publikowana
jako prawidłowy pomiar. Interpolacja offline jest możliwa tylko dla krótkiej,
geometrycznie dozwolonej luki; zasłonięcie i wyjście z kadru jej zabraniają.

## Pose Graph i tracking

`pose_v4.graph.BiomechanicalPoseGraph` przechowuje stan jointów, kości,
anchorów tułowia i kończyn. Walidacja ma trzy poziomy: lokalny (V3), łańcuch
kinematyczny i cały model. Confidence modelu jest tylko jednym z sygnałów.
Expected position, prędkość, przyspieszenie, zależności rodzic–dziecko,
długość i kierunek kości mogą odrzucić pozornie pewny, lecz nierealny punkt.

Główna osoba nadal jest wybierana i śledzona przez istniejący tracker z
pamięcią bbox, tożsamości i potwierdzanym `REACQUIRING`. Nie istnieje fallback
uruchamiający estymację pozy na pełnej klatce. Druga, większa albo bardziej
centralna osoba nie zastępuje automatycznie aktywnego tracku.

Każda kończyna ma niezależny stan: `VISIBLE`, `PARTIAL`, `OCCLUDED`,
`OUT_OF_FRAME`, `PREDICTED_SHORT`, `LOST` lub `REACQUIRING`. Expected position
poza obrazem oznacza `OUT_OF_FRAME`; pozycja wewnątrz bbox/tułowia przy
zniknięciu punktu stanowi sygnał zasłonięcia. Są to heurystyki 2D, nie
segmentacja ani pomiar głębokości.

Skala ciała jest medianą bbox i wiarygodnych anchorów konkretnej osoby, z
ograniczeniem zmiany pomiędzy klatkami. Profil proporcji przechowuje medianę,
MAD, liczbę próbek i techniczny wskaźnik stabilności. Profil aktualizują tylko
dobre klatki stanu `TRACKED`.

## Hand Graph

Adaptacyjne ROI wynikają z nadgarstka, przedramienia, poprzedniego palm center,
prędkości i palm scale. Detekcje obu dłoni są przypisywane globalnie w problemie
2×2. Koszt uwzględnia wrist, przewidywane centrum, skalę, orientację,
handedness jako miękką wskazówkę i karę zmiany strony.

Palm frame wymaga stabilnej geometrii wrist oraz MCP. Zawiera center, width,
height, orientation, kierunki baz palców i — wyłącznie gdy MediaPipe dostarczy
wiarygodne world landmarks — względny sygnał normalnej. Każdy palec jest
walidowany osobno; zły tip nie unieważnia poprawnego MCP/PIP. Brakujące palce
przy obiekcie albo tułowiu otrzymują stan `OCCLUDED`/`UNKNOWN`, a nie sztucznie
odtworzone współrzędne. Odrzucone punkty RTMW nie zastępują dedykowanej dłoni.

Grip V2 rozróżnia `OPEN`, `RELAXED`, `PARTIALLY_CLOSED`, kandydat chwytu
siłowego, kandydat pinch, `CLOSED` i `UNKNOWN`. Cechy obejmują zgięcia MCP/PIP/
DIP, aperturę dłoni, relacje kciuka i stabilność. Są to cechy geometryczne, nie
siła chwytu.

## Holding V2

Holding jest wnioskowaniem zdarzeń z ważonych evidence: geometrii chwytu,
bliskości i krótkiego tracku obiektu, wspólnego ruchu, ciągłości, wzorca
zasłonięcia i kary jakości. Wynik evidence nie jest prawdopodobieństwem.
Wyższy próg wejścia, niższy próg utrzymania i osobny próg wyjścia ograniczają
migotanie. Krótka luka `UNKNOWN` i zgodne epizody są łączone. Otwarcie dłoni,
wzrost apertury, utrata bliskości i rozbieżny ruch składają się na release.

Znany obiekt korzysta ze stabilnego `track_id`. Dla obiektu spoza COCO możliwy
jest jawny stan `LIKELY_HOLDING_UNKNOWN_OBJECT`, ale wymaga mocnej i trwałej
geometrii. Bimanual holding wymaga tego samego tracku albo trwałego wspólnego
ruchu i geometrii; sama bliskość dłoni nie wystarcza. Czas jest liczony z
timestampów, z FPS jedynie jako fallback. Zapisywane są epizody, holding
statyczny po minimalnym czasie oraz cykle grasp/release i pinch.

## Overlay

Paleta jest centralna. Kolory neutral/mild/elevated/strong wynikają z jawnych,
nienormatywnych pasm odchylenia geometrycznego i nie są wynikiem RULA, REBA ani
klasyfikacją ryzyka. Niska jakość daje szary fallback. Dwuklatkowa histereza
koloru ogranicza migotanie. Kąty pochodzą z tego samego API Metrics Engine co
wynik analityczny.

Render ma osobne progi jakości i stan widoczności kości. Może krótko wygasić
ostatnią poprawną geometrię, lecz nie rysuje nowej błędnej linii. Ostatnia
warstwa bezpieczeństwa odrzuca NaN/Infinity, punkty poza obrazem, wektory
zerowe i segmenty dłuższe niż limit względem kości, skali ciała lub przekątnej.
Tryb normalny jest oszczędny; debug dodaje bbox, powody odrzuceń i obiekty.

## Quality V2 i diagnostyka

Jakość klatki agreguje body quality, coverage, widoczność kończyn, dłonie,
lokalny i globalny blur proxy, ekspozycję, stabilność trackingu i zasłonięcia.
Lokalne ROI dłoni zapobiegają ukrywaniu ich problemów przez ostrą resztę obrazu.
`pose-diagnostics.json` przechowuje tracking, body, hands, holding, quality,
runtime, render safety i najgorsze klatki. Warningi obejmują m.in. track loss,
occlusion, swap risk, finger rejection, body coverage, motion blur i niski
holding evidence.

## Ograniczenia

- Analiza jest głównie 2D; relative depth, jeżeli dostępne, pozostaje miękkim
  sygnałem i nigdy nie jest nazywane metrami.
- Occlusion jest heurystyką, nie segmentacją obrazu.
- Klasy nieznanych obiektów mogą pozostać nierozpoznane.
- Pipeline nie estymuje siły, masy, momentów ani obciążenia mięśni.
- Kolory overlayu nie są oceną normatywną ani decyzją BHP.
- Rzeczywista trafność wymaga testów na nagraniach i ground truth.

## Lokalna walidacja

```powershell
worker\.venv\Scripts\python.exe worker\tools\analyze_local_video.py --input "D:\film.mp4" --output "D:\ergonomia-v04-test" --debug-overlay --angles --objects --ergonomics
worker\.venv\Scripts\python.exe worker\tools\compare_pose_runs.py baseline\pose-diagnostics.json candidate\pose-diagnostics.json
```

Pełne testy:

```powershell
worker\.venv\Scripts\python.exe -m pytest worker\tests
worker\.venv\Scripts\python.exe -m compileall worker\src worker\tools
```
