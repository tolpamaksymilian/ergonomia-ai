# Photo Scene Builder v0.6 beta — Scene World Model

## Przyczyna regresji skali

W wersji v0.5 wszystkie aktywne referencje poza `DEPTH` mogły zasilać jeden model
`valueCm / pixelDistance`. Typy `WIDTH`, `DISTANCE`, `CUSTOM` oraz wymiary obiektów nie
były odizolowane od skali pionowej. Przesunięcie człowieka zmieniało wynik regresji albo
zestaw najbliższych referencji, przez co poziomy wymiar 50 cm mógł zmienić projekcję
wzrostu człowieka. Cichy clamp 10–92% wysokości obrazu maskował błąd zamiast go ujawnić.

## Measurement Semantics V2

Każdy zapisany pomiar ma teraz jawne:

- `measurementKind` — co jest mierzone,
- `axis` — kierunek geometryczny,
- `plane` — płaszczyznę,
- `purpose` — przeznaczenie,
- `useForCalibration` — świadomą decyzję użytkownika,
- `semanticStatus` — potwierdzenie albo wymagany przegląd,
- `worldAnchors` — znane punkty obrazu i wysokości świata.

Tylko potwierdzony pomiar pionowy na `VERTICAL_PLANE`, przeznaczony do kalibracji
i posiadający spójne dolne oraz górne world anchor może zasilać Vertical Scale Field.

## Scene World Model

Centralne API znajduje się w `scene-world-model.ts`:

- `createSceneWorldModel`,
- `getVerticalScaleAt`,
- `getGroundProjectionAt`,
- `getMeasurementPlane`,
- `getHumanProjectionAt`,
- `validateMeasurementForCalibration`,
- `getCalibrationCoverageAt`.

Human Projection nie iteruje po `scene.measurements`. Otrzymuje wyłącznie wynik modelu
kalibracji dla punktu kontaktu stóp.

## Podłoga i perspektywa

Tryb podstawowy zapisuje dwa punkty orientacyjne. Tryb dokładniejszy zapisuje cztery
punkty widocznego fragmentu podłogi. Cztery punkty bez rzeczywistego wymiaru podłoża
nie tworzą world homography — stan pozostaje `ORIENTATION_ONLY`. `PROJECTIVE` może być
użyte dopiero, gdy istnieje również rzeczywista odległość na podłodze.

## Starsze sceny

Dokumenty 1.0–1.2 są normalizowane do 1.3. Stare pomiary otrzymują
`SEMANTICS_REVIEW_REQUIRED` i `useForCalibration=false`. Użytkownik musi potwierdzić ich
znaczenie, zanim zaczną wpływać na Calibration V3.

## Ograniczenia

- Jest to model projekcyjny pojedynczego zdjęcia, a nie rekonstrukcja 3D.
- Brak pełnej kalibracji kamery i pełnej homografii bez danych użytkownika.
- Worker może sugerować linie i płaszczyzny, ale nigdy wartości centymetrowe.
- Moduł nie wykonuje PHOTO RULA, REBA, OWAS ani punktacji ryzyka.

## Testy

```powershell
npm.cmd run test:photo-scene
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
git diff --check
```
