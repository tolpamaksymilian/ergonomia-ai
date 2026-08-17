# Scene Detection Worker

Lekki, odseparowany etap dla analiz `PHOTO_SCENE`. Pobiera prywatny obraz z bucketa `analysis-scenes` oraz zapisany kontekst Guided Setup, dekoduje obraz, uruchamia istniejący YOLOX-X COCO w trybie wieloklasowym na CPU i zapisuje `scene-detection.json` oraz zmniejszony preview. Nie uruchamia Pose, Metrics, Risk, RULA, REBA ani OWAS.

Od v0.3 Worker startuje dopiero po poleceniu „Rozpoznaj i zbuduj scenę”. Otrzymuje ręczne regiony podłogi i ruchu, wszystkie wysokości oraz dodatkowe wymiary, ręczne obiekty/powierzchnie, Constraint Graph i rewizję sceny. Kandydat nakładający się na ręczny obiekt jest pomijany; Worker może znaleźć dodatkowe obiekty, ale nie zastępuje semantyki ani geometrii `USER_PROVIDED`.

Klasy COCO są mapowane zachowawczo. Przykładowo `dining table` jest sugerowane jako `TABLE`, przy czym oryginalne `source_class` pozostaje w wyniku. Nieznane klasy są pomijane, a brak detekcji jest poprawnym wynikiem umożliwiającym ręczną edycję.

Ograniczenia: obraz jest 2D, detektor nie rozpoznaje wszystkich elementów przemysłowych, adapter RTMLib nie zwraca confidence, a każdy kandydat wymaga potwierdzenia użytkownika.

Worker jest utrzymywany przez Pipeline Manager, ale nowe zdjęcie nie trafia do jego kolejki automatycznie. Lokalnie można wykonać jeden cykl kolejki:

```powershell
worker\.venv\Scripts\python.exe worker\src\scene_detection_worker.py --once
```

Self-test nie pobiera zadania z kolejki i nie zapisuje danych produkcyjnych. Sprawdza konfigurację,
inicjalizację rzeczywistego YOLOX-X/ONNX Runtime na CPU, kodowanie i dekodowanie obrazu, inference
oraz przebieg geometrii:

```powershell
worker\.venv\Scripts\python.exe worker\src\scene_detection_worker.py --self-test
```

`SUCCESS_NO_OBJECTS` jest poprawnym wynikiem: geometria nadal jest analizowana, a użytkownik może
dodać obiekty ręcznie. Stabilne kody błędów rozróżniają claim, ścieżkę, download, decode,
inicjalizację detektora, inference, geometrię, upload i finalizację RPC. Worker wykonuje najwyżej
jedno automatyczne ponowienie błędu przejściowego.

Obrazy do 2000 px mają jeden przebieg detektora. Większe obrazy zachowują pełny przebieg oraz do
dziewięciu nakładających się kafli 1600 px; duplikaty są usuwane przez istniejący IoU. Ogranicza to
utratę małych obiektów bez nieograniczonego wzrostu czasu CPU.
