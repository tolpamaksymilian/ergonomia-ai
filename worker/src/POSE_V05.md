# Pose Pipeline V5.1

Pose V5.1 (`pose-v5.1-beta.1`, schema `5.1`) zachowuje YOLOX-X, RTMW WholeBody i MediaPipe Hand Landmarker jako bazowe providery. Nie przedstawia jakości jako prawdopodobieństwa ani dokładności względem ground truth.

## Przepływ

Pass 1 wykonuje standardową detekcję, tracking, graf biomechaniczny, analizę dłoni, obiektów, chwytu i jakości. Warstwa robust evidence fusion łączy konserwatywnie jakość modelu, ciągłość czasową, geometrię łańcucha, tracking, widoczność i jakość obrazu. Wynik jointa to `ACCEPTED`, `WEAK`, `REJECTED`, `OCCLUDED`, `PREDICTED` albo `UNKNOWN`; odrzucony outlier nie przesuwa anchorów temporalnych.

Prędkość, przyspieszenie i jerk są liczone z rzeczywistego `dt` i normalizowane względem skali ciała. Lekka estymacja sparse optical flow poza bbox osoby daje sygnał globalnego przesunięcia i drgania kamery. Scene cut resetuje pamięć trackera, grafu oraz przypisania dłoni. Surowe współrzędne nie są stabilizowane ani nadpisywane ruchem kamery.

Po Pass 1 detektor scala trudne klatki w segmenty z marginesem czasowym. Pass 2 uruchamia baseline wyłącznie dla segmentów refinable, maksymalnie dla `POSE_V5_MAX_REFINEMENT_RATIO` filmu. Długi segment jest przycinany do budżetu. Kandydat zastępuje Pass 1 tylko po przejściu bramki biomechanicznej i osiągnięciu co najmniej `POSE_V5_MIN_QUALITY_GAIN`; następnie cały graf jest odtwarzany w oryginalnym kontekście. Awaria Pass 2 zachowuje Pass 1. Gdy większość filmu jest trudna, diagnostyka zgłasza `video_quality_limited`, zamiast automatycznie analizować wszystko ponownie.

## Dłonie i Holding V3

Walidacja palców obejmuje pełne łańcuchy MCP–PIP–DIP–TIP, sąsiedni kontekst czasowy i profil kształtu dłoni aktualizowany tylko przy wysokiej jakości. Assignment uwzględnia nadgarstek, łokieć, kierunek przedramienia, orientację dłoni, trajektorię, skalę, handedness i histerezę tożsamości. Brak palca pozostaje `OCCLUDED` lub `UNKNOWN`.

Holding V3 wymaga zbieżnych dowodów chwytu, kontaktu/obiektu i wspólnego ruchu. Zamknięta pięść bez obiektu nie oznacza trzymania. Krótka utrata obiektu nie rozcina epizodu, natomiast potwierdzone otwarcie dłoni kończy go. Masa, siła i obciążenie zewnętrzne nie są estymowane.

## Konfiguracja

- `POSE_V5_REFINEMENT_ENABLED=true`
- `POSE_V5_MAX_REFINEMENT_RATIO=0.25`
- `POSE_V5_SEGMENT_PADDING_SECONDS=0.35`
- `POSE_V5_MIN_QUALITY_GAIN=0.04`
- `POSE_V5_CAMERA_MOTION_ENABLED=true`

## Ograniczenia

Analiza pozostaje oparta głównie na obrazie 2D. Zasłonięcia, motion blur, wyjście z kadru i brak widoku dłoni mogą dać `UNKNOWN`, `OCCLUDED` lub `INVALID`. Predykcja służy jako krótki sygnał diagnostyczny i nie jest pomiarem. V5 nie estymuje siły ani masy i wymaga walidacji na reprezentatywnych nagraniach z danymi referencyjnymi przed formułowaniem twierdzeń o dokładności.
