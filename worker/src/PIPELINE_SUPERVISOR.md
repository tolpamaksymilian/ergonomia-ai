# Pipeline Supervisor v1.0 beta

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

Stan jest atomowo zapisywany do `.runtime/worker-health.json`. Plik nie zawiera
sekretów, tokenów, signed URL ani treści dokumentów analizy. Lock
`.runtime/pipeline-supervisor.lock` zapobiega uruchomieniu dwóch lokalnych
managerów. Stary lock jest usuwany dopiero po sprawdzeniu PID.

Po nieoczekiwanym zakończeniu Pipeline Managera Supervisor stosuje opóźnienia
2, 5, 10, 20 i maksymalnie 30 sekund. Piąty crash w dziesięć minut przełącza
stan na `crash_loop`.

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
