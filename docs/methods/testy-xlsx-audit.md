# Audyt źródłowy `testy.xlsx`

## Zakres i identyfikacja źródła

- Plik źródłowy: `testy.xlsx` (dostarczony poza repozytorium; nie jest kopiowany do Git).
- SHA-256: `78fa02ed3be7d46c1aaab772c556a7e7e56867f7566c825ed84f3eef02be5eca`.
- Arkusze: 6 (`Lista zagrożeń`, `form_ Risk_Score`, `form czynniki mierzalne`, `form_chemia`, `OWAS`, `EJMS`).
- Komórki, formuły, komentarze, nazwy zdefiniowane, relacje rysunków i media odczytano bezpośrednio ze struktur Open XML pakietu XLSX. Widoki wszystkich arkuszy wyrenderowano niezależnie.
- Media: 159 unikalnych plików PNG. Arkusz OWAS ma 96 osadzeń, EJMS 71 osadzeń; 8 osadzeń ponownie używa istniejących plików, dlatego liczba relacji wynosi 167, a unikalnych obrazów 159.
- Wszystkie obrazy obejrzano na 10 arkuszach kontaktowych. Obrazy 1–96 pokazują warianty pozycji OWAS, a 97–159 głównie kąty, postawy, chwyt, siły oraz geometrię przenoszenia EJMS. Obrazy są materiałem QA, nie samodzielnym źródłem progów.

Statusy: `VERIFIED`, `AMBIGUOUS`, `BROKEN`, `EXTERNAL_REFERENCE_REQUIRED`. Dodatkowe oznaczenia wykonawcze (`NORMALIZED_INTERPRETATION`, `SOURCE_FORMULA_MISSING`, `SOURCE_AMBIGUOUS`) nie naprawiają źródła i pozostają widoczne w specyfikacjach.

## Rejestr reguł

| Metoda | Opis | Arkusz | Komórka / zakres | Typ | Interpretacja | Status |
|---|---|---|---|---|---|---|
| Katalog zagrożeń | Źródło, zagrożenie i możliwe skutki | Lista zagrożeń | A3:D44 | CELL | 41 pozycji; puste źródła/skutki pozostają `null` | VERIFIED |
| Risk Score | Skala ekspozycji 0,5/1/2/3/6/10 | form_ Risk_Score | J5:Q8 | CELL + FORMULA | Wartości potwierdza formuła Q6:Q8 | VERIFIED |
| Risk Score | Skala skutków 1/3/7/15/40/100 | form_ Risk_Score | T5:Z9 | CELL + FORMULA | Wartości potwierdza formuła Z6:Z7; kolejne komórki mają zapisane wyniki bez formuł | VERIFIED |
| Risk Score | Skala prawdopodobieństwa 0,1/0,2/0,5/1/3/6/10 | form_ Risk_Score | AA5:AH8 | CELL + FORMULA | Wartości potwierdza formuła AH6 | VERIFIED |
| Risk Score | Wartość ryzyka | form_ Risk_Score | AI6:AI17 | CELL | Brak formuły. Implementowane mnożenie E×S×P jest jawnie oznaczone `NORMALIZED_INTERPRETATION`, nie jako formuła skoroszytu | BROKEN |
| Risk Score | Kategorie do 20/70/200/400 i powyżej 400 | form_ Risk_Score | AJ6:AJ17 | FORMULA | Progi są czytelne, lecz 11 formuł zawiera `#REF!`, a AJ7 odwołuje się do AI17 | BROKEN |
| Risk Score | Akcja dla kategorii | form_ Risk_Score | AK6:AK17 | FORMULA | Kontrola / poprawa / natychmiastowa poprawa / wstrzymanie pracy | VERIFIED |
| Risk Score | D do 400, ND powyżej 400 | form_ Risk_Score | AL6:AL20 | FORMULA + CELL | Akceptowalność dotyczy jawnych progów wyniku | VERIFIED |
| Czynniki mierzalne | P > Pmax → duże, niedopuszczalne | form czynniki mierzalne | E6:I14 | FORMULA | Granica ścisła | VERIFIED |
| Czynniki mierzalne | 0,5Pmax ≤ P ≤ Pmax → średnie, dopuszczalne | form czynniki mierzalne | E6:I14 | FORMULA | Obie granice włączone | VERIFIED |
| Czynniki mierzalne | P < 0,5Pmax → małe, dopuszczalne | form czynniki mierzalne | E6:I14 | FORMULA | Granica ścisła | VERIFIED |
| Ważność dokumentu | Data aktualizacji + 60 miesięcy | form czynniki mierzalne | J2:J3 | FORMULA | `EDATE(J2,60)` | VERIFIED |
| Chemia | Nazwa zgodna z kartą charakterystyki i producent | form_chemia | A4 | COMMENT | Wartość manualna | VERIFIED |
| Chemia | Poziom A–E z H-statements | form_chemia | B4 | COMMENT | Odwołanie do IN.06.13, której brak w pliku | EXTERNAL_REFERENCE_REQUIRED |
| Chemia | Temperatura wrzenia z karty charakterystyki | form_chemia | C4 | COMMENT | Wartość manualna / pomiarowa | VERIFIED |
| Chemia | Lotność z wykresu temperatur | form_chemia | E4 | COMMENT | Odwołanie do wykresu IN.06.13, którego brak | EXTERNAL_REFERENCE_REQUIRED |
| OWAS | Kody pleców 1–4 | OWAS | E81:F84 | LOOKUP | Wyprostowane / zgięte / skręcone / zgięte i skręcone | VERIFIED |
| OWAS | Kody ramion 1–3 | OWAS | H81:I83 | LOOKUP | Oba poniżej / jedno powyżej / oba powyżej barków | VERIFIED |
| OWAS | Kody nóg 1–7 | OWAS | K81:L87 | LOOKUP | Siedzenie, warianty stania, klęczenie, chodzenie | VERIFIED |
| OWAS | Obciążenie 1–3 | OWAS | N81:O83 | LOOKUP | <10 kg, 10–20 kg, >20 kg; masa wyłącznie manualna/pomiarowa | VERIFIED |
| OWAS | Kategoria kodu czterocyfrowego | OWAS | AB79:AC330 | LOOKUP | Runtime używa dopasowania ścisłego; skoroszyt używa przybliżonego VLOOKUP | AMBIGUOUS |
| OWAS | Opisy kategorii 1–4 | OWAS | S60:S72 | CELL | Opisy działań zachowane semantycznie | VERIFIED |
| OWAS | Ocena czasu i wymuszenia | OWAS | BA63:BB72 | LOOKUP | Wymuszenie nie jest wyznaczane z filmu; wymaga `USER_PROVIDED` | VERIFIED |
| EJMS I | 8 obszarów: szyja, ramię, tułów, przedramię/łokieć, nadgarstek, palce/dłonie, nogi, statyczność | EJMS | A18:V38 | CELL | Reguły HIGH i LOW są jawne; poziom pośredni jest znormalizowany jako MOD | VERIFIED |
| EJMS I | Macierz postawa/siła × częstotliwość/czas | EJMS | C25:I29, C40:I44 | LOOKUP | 0/5/10, 5/10/15, 10/15/20 | VERIFIED |
| EJMS II | Masa | EJMS | H51:L51 | CELL + IMAGE | 1/5/10/20/30 punktów; kg wymaga użytkownika/pomiaru | VERIFIED |
| EJMS II | HD, SLH, pionowe przemieszczenie | EJMS | H52:L54 | CELL + IMAGE | Centymetry wymagają kalibracji albo użytkownika | VERIFIED |
| EJMS II | Częstotliwość | EJMS | H55:L55 | CELL | Może być wyprowadzona z wiarygodnych zdarzeń wideo | VERIFIED |
| EJMS II | Skręt | EJMS | H56:K56 | CELL + IMAGE | 1–15/16–35/36–65/66–135°; tylko przy wiarygodnej geometrii | VERIFIED |
| EJMS II | Chwyt | EJMS | A57:J57 | CELL + IMAGE | GOOD/SATISFACTORY/BAD wymaga danych użytkownika; Holding V3 nie przesądza jakości chwytu | VERIFIED |
| EJMS II | Dystans | EJMS | H58:K58 | CELL | Metry wymagają użytkownika/pomiaru | VERIFIED |
| EJMS | Globalny ranking | EJMS | A9:C11 | CELL | `>85` wysokie, `45–84` umiarkowane, `>=44` niskie jest sprzeczne; globalna etykieta jest wyłączona | BROKEN |
| EJMS | Komunikat przeglądu | EJMS | S11 | FORMULA | `R23>=Y1416` wskazuje pustą komórkę poza używanym zakresem | BROKEN |

## Komentarze

Znaleziono dokładnie cztery komentarze, wszystkie w `form_chemia`: A4, B4, C4 i E4. Ich treść wskazuje odpowiednio kartę charakterystyki/producenta, zwroty H i IN.06.13, temperaturę wrzenia z karty charakterystyki oraz wykres lotności IN.06.13. Brak IN.06.13 uniemożliwia automatyczny scoring chemiczny.

## Ukryte dane, lookupy i zależności

- `Lista zagrożeń`: kolumny A i D są ukryte, mimo że zawierają źródła oraz skutki. Dane zostały zachowane.
- `OWAS`: ukryte są wiersze 59–338 i 370–1029. Zawierają opisy kategorii, słowniki kodów, lookup 252 wierszy oraz dane pomocnicze formularzy.
- `EJMS`: ukryte kolumny Z:AA zawierają liczby wykorzystywane przez formułę S11.
- Nazwy zdefiniowane `Plecy`, `Ramiona`, `Nogi`, `Obciążenia_zewnętrzne`, `Pozycja_ciała_przy_pracy`, `czynnosci` i `reductionscore` odwołują się do nieobecnych zewnętrznych arkuszy/pliku. Globalna nazwa `FQ` ma `#REF!`; lokalna `FQ` poprawnie wskazuje EJMS!A74:A76.
- OWAS AW354 i analogiczne komórki używają `VLOOKUP(..., TRUE)`. Takie przybliżone wyszukiwanie może zamaskować brak kodu. Specyfikacja wykonawcza wymaga dopasowania exact.

## Anomalie źródła

1. OWAS 3133 występuje dwukrotnie i prowadzi do kategorii 3 oraz 2 — `SOURCE_AMBIGUOUS`.
2. OWAS nie zawiera 2133, 4173 i 4373 — `SOURCE_MISSING`.
3. OWAS zawiera niepoprawne 7173 i 7373 — `SOURCE_INVALID`.
4. OWAS stosuje przybliżony VLOOKUP dla kodu — runtime nie powiela tego zachowania.
5. Risk Score nie definiuje formuły wartości ryzyka w AI6:AI17 — `SOURCE_FORMULA_MISSING`.
6. Risk Score AJ6 i AJ8:AJ17 mają `#REF!`; AJ7 błędnie używa AI17 — `BROKEN`.
7. EJMS globalny ranking ma nakładające się/sprzeczne granice — `SOURCE_THRESHOLD_CONFLICT`.
8. EJMS S11 odwołuje się do Y1416 — `BROKEN_SOURCE_REFERENCE`.
9. Chemia wymaga brakującej IN.06.13 — `EXTERNAL_REFERENCE_REQUIRED`.
10. Skoroszyt zawiera uszkodzone nazwy zdefiniowane i odwołania do nieobecnych zewnętrznych arkuszy — dodatkowa anomalia wykryta w audycie.
11. W wielu wierszach formularzy formuły występują tylko w pierwszych przykładach, a dalsze komórki mają jedynie cache wyniku; nie są traktowane jako niezależne źródło reguł.
12. OWAS BA63:BB66 nakłada reguły dla niewymuszonej kategorii 1 w zakresie 50–70% i może zwrócić jednocześnie `MAŁE` oraz `ŚREDNIE` — `SOURCE_AMBIGUOUS`; runtime zachowuje oba dopasowania.

## Decyzje implementacyjne

- JSON w `method-specs/` jest jedynym źródłem progów dla Python i TypeScript.
- `UNKNOWN` nigdy nie jest konwertowane na 0 ani LOW.
- Klasyfikacja filmu może dostarczać tylko cechy względne i kątowe. kg, N, cm i m wymagają `USER_PROVIDED`/`MEASUREMENT` lub wiarygodnej kalibracji.
- Risk Score używa mnożenia czynników tylko jako jawnej `NORMALIZED_INTERPRETATION`.
- Chemia pozostaje `PARTIAL_MANUAL`; automatyczny scoring jest wyłączony.
- EJMS globalny ranking pozostaje wyłączony do zatwierdzenia spójnych granic.
- OWAS o nieznanej masie zwraca możliwe kategorie dla kodów load 1/2/3 i status `PARTIAL`; kod niejednoznaczny nie jest arbitralnie rozstrzygany.
