# Pipeline Supervisor v1.1 beta

`pipeline_supervisor.py` jest lokalnym procesem nadrzędnym dla istniejącego
`pipeline_manager.py`. Nie przejmuje kolejki i nie duplikuje logiki workerów.

## Start

Z katalogu repozytorium:

```powershell
npm.cmd run dev
```

Polecenie wybiera `worker\.venv\Scripts\python.exe`, uruchamia Supervisor i
Next.js oraz kończy oba procesy po `Ctrl+C`. Sam frontend uruchamia
`npm.cmd run dev:web`.

Skrypt JavaScript nie uruchamia `npm.cmd` jako procesu potomnego. Next.js jest
wywoływany bez shella przez aktualny `process.execPath` oraz lokalny plik
`node_modules/next/dist/bin/next`. Dzięki temu start działa również z Node 26
na Windows i nie wymaga wyłączania zabezpieczeń `child_process`. Port 3000 jest
sprawdzany przed startem; zajęty port powoduje czytelny błąd zamiast cichego
przejścia Next.js na port 3001.

## Gotowość i heartbeat

Preflight kontroluje nazwy wymaganych zmiennych (bez odczytu ich wartości do
logów), prywatne buckety i RPC przez istniejący check gotowości, FFmpeg,
FFprobe, PyTorch/CUDA, model dłoni i możliwość zapisu do `.runtime`.
Jeżeli kontrola wykryje błąd, Supervisor utrzymuje heartbeat `degraded`,
pozostawia Next.js dostępny z diagnostyką i ponawia preflight co 30 sekund.

Stan jest atomowo zapisywany do `.runtime/worker-health.json` przez jednego
właściciela: `pipeline_supervisor.py`. Zapis używa unikalnego pliku tymczasowego
na tym samym systemie plików, `flush`, `fsync` oraz ograniczonych ponowień z
jitterem dla przejściowych blokad Windows. Nieudany zapis diagnostyki nie
zatrzymuje supervisora ani aktywnego workera: stan wykonania pozostaje online,
a persistence przechodzi w `degraded` i jest ponawiane przy następnym heartbeat.
Ostatni poprawny JSON pozostaje nienaruszony.

Plik health nie zawiera sekretów, tokenów, signed URL ani treści dokumentów
analizy. Frontend wykonuje krótkie retry odczytu i przez ograniczony grace period
korzysta z ostatniego poprawnego dokumentu zamiast zgłaszać natychmiastowe
`offline`.

Lock `.runtime/pipeline-supervisor.lock` zawiera PID, UUID instancji, czas startu
i bezwzględny katalog repozytorium. Jest tworzony atomowo i zapobiega uruchomieniu
dwóch lokalnych managerów. Stary lock jest usuwany dopiero po weryfikacji procesu;
poprawne zamknięcie usuwa wyłącznie lock należący do tej samej instancji.

Po nieoczekiwanym zakończeniu Pipeline Managera Supervisor stosuje opóźnienia
2, 5, 10, 20 i maksymalnie 30 sekund. Piąty crash w dziesięć minut przełącza
stan na `crash_loop`.

`dev-supervisor.mjs` jest właścicielem procesu Python Supervisor, natomiast
Python Supervisor jest właścicielem Pipeline Managera i jego workerów. Warstwa
Node ponownie wykorzystuje zgodną, aktywną instancję, czeka na jej pełne
zakończenie przed restartem i stosuje ograniczony backoff 0,5 / 1,5 / 4 s.
Supervisor prosi Pipeline Manager o łagodne zatrzymanie przez plik runtime;
dzięki temu na Windows Manager wykonuje własny cleanup workerów przed
ewentualnym wymuszonym zakończeniem.

## Pliki runtime

- `.runtime/worker-health.json` — atomowy, diagnostyczny heartbeat; nie jest
  częścią krytycznej ścieżki obliczeń,
- `.runtime/pipeline-supervisor.lock` — tożsamość jedynej instancji supervisora,
- `.runtime/pipeline-supervisor.stop` — łagodne żądanie zatrzymania supervisora,
- `.runtime/pipeline-manager.stop` — łagodne żądanie cleanupu workerów Managera,
- `worker-health.json.*.tmp` — pliki przejściowe; stare egzemplarze są bezpiecznie
  sprzątane przy starcie.

Konfigurację interwału heartbeat, ponawiania preflight, limitu crashy, okna
crash-loop i czasu łagodnego zamknięcia opisuje `worker/.env.example`.

Sterowanie procesem z aplikacji jest dostępne wyłącznie lokalnie, poza Vercel i
produkcją, po jawnym ustawieniu `ALLOW_LOCAL_WORKER_CONTROL=true`.

## Opcjonalny autostart Windows

Autostart przy logowaniu nie jest wymagany przez `npm.cmd run dev`. Można go
opcjonalnie zarejestrować i usunąć poleceniami:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\install-worker-autostart.ps1
powershell.exe -ExecutionPolicy Bypass -File scripts\uninstall-worker-autostart.ps1
```
