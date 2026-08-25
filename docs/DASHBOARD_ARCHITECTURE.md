# Dashboard Workspace Redesign

Wersja aplikacji: `0.27.0-beta.1`.

## Architektura informacji

Panel korzysta ze wspólnego, responsywnego shellu z lewą nawigacją i topbarem. Trasy użytkownika pozostają pod `/panel`, a widoki superadministratora pod `/admin`.

### Użytkownik

- `/panel` — podsumowanie analiz, raportów i ostatniej aktywności,
- `/panel/analizy` — historia, wyszukiwanie i filtry analiz,
- `/panel/analizy/nowa` — wybór istniejącego trybu analizy,
- `/panel/raporty` — gotowe raporty,
- `/panel/stanowiska` — stanowiska pracy używane w analizach,
- `/panel/profil` — dane konta, firma, rola i stanowisko,
- `/panel/ustawienia` — preferencje i słowniki.

Administrator firmy otrzymuje dodatkowo `/panel/firma`. Widzi i modyfikuje wyłącznie członków, stanowiska i zaproszenia swojej firmy. Dostęp jest wymuszany zarówno w kodzie serwerowym, jak i przez RLS.

### Superadministrator

- `/admin` — przekrojowy dashboard,
- `/admin/firmy` i `/admin/firmy/[id]` — organizacje i ich zespoły,
- `/admin/uzytkownicy` — filtrowana lista kont,
- `/admin/zaproszenia` — onboarding przez e-mail,
- `/admin/stanowiska` — stanowiska organizacyjne,
- `/admin/rozwoj` — wersje i roadmapa.

## Model organizacyjny

Migracja `20260825190000_add_company_dashboard_management.sql` dodaje:

- `companies` — firmy,
- `company_positions` — funkcje pracowników w konkretnej firmie,
- `company_invitations` — audytowalne zaproszenia e-mail,
- pola organizacyjne w `profiles`, w tym firmę, rolę, stanowisko, status konta, e-mail i ostatnią aktywność.

Rola aplikacyjna `admin` nadal oznacza superadministratora. Rola firmowa ma wartości `admin`, `member` i `reviewer`. Nie należy utożsamiać `company_positions` ze stołem `workstations`: pierwsze opisują funkcje ludzi, drugie miejsca/procesy analizowane ergonomicznie.

## Zapraszanie użytkownika

1. Administrator podaje e-mail, firmę, rolę i opcjonalne stanowisko.
2. Server Action zapisuje rekord `company_invitations`.
3. Serwerowy klient Supabase Auth wysyła zaproszenie.
4. Trigger tworzący profil przypisuje oczekujące zaproszenie po znormalizowanym adresie e-mail.
5. Callback po uwierzytelnieniu wywołuje `accept_my_company_invitation()` i aktywuje konto.

Wysyłka wymaga `SUPABASE_SECRET_KEY` wyłącznie w środowisku serwerowym Next.js. Zmienna nie może mieć prefiksu `NEXT_PUBLIC_`, nie może być importowana przez Client Component ani zapisywana w repozytorium. Należy też skonfigurować SMTP i dozwolony redirect `/auth/callback` w projekcie Supabase.

## Design system i responsywność

Klasy dashboardu są zawężone do `.dashboard-shell`, dzięki czemu fioletowo-indygowy język wizualny nie zmienia publicznej strony ani edytorów. Sidebar ma tryb zwinięty na desktopie i drawer na urządzeniach mobilnych. Tabele zachowują czytelność przez lokalny scroll poziomy; cała strona go nie wymusza. Nawigacja oraz topbar są ukrywane podczas drukowania raportu.

Wspólne elementy znajdują się w `src/components/dashboard`, definicje nawigacji w `src/config/dashboard-navigation.ts`, a czyste helpery prezentacji w `src/lib/dashboard/presentation.ts`.

## Wdrożenie i testy

```powershell
npx.cmd supabase db push
npm.cmd run test:dashboard
npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build
npm.cmd run check:release
```

Po migracji należy ręcznie sprawdzić zaproszenie na testowy adres, logowanie z linku oraz separację dwóch firm. Nie należy testować przez konto produkcyjne bez przygotowanego planu cofnięcia zaproszenia.
