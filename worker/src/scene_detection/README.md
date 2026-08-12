# Scene Detection Worker

Lekki, odseparowany etap dla analiz `PHOTO_SCENE`. Pobiera wyłącznie prywatny obraz z bucketa `analysis-scenes`, dekoduje go, uruchamia istniejący YOLOX-X COCO w trybie wieloklasowym na CPU i zapisuje `scene-detection.json` oraz zmniejszony preview. Nie uruchamia Pose, Metrics, Risk, RULA, REBA ani OWAS.

Klasy COCO są mapowane zachowawczo. Przykładowo `dining table` jest sugerowane jako `TABLE`, przy czym oryginalne `source_class` pozostaje w wyniku. Nieznane klasy są pomijane, a brak detekcji jest poprawnym wynikiem umożliwiającym ręczną edycję.

Ograniczenia: obraz jest 2D, detektor nie rozpoznaje wszystkich elementów przemysłowych, adapter RTMLib nie zwraca confidence, a każdy kandydat wymaga potwierdzenia użytkownika.

Worker startuje automatycznie przez Pipeline Manager. Lokalnie można wykonać jeden cykl:

```powershell
worker\.venv\Scripts\python.exe worker\src\scene_detection_worker.py --once
```
