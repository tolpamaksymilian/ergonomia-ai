# Photo Scene Builder v0.5 beta — Digital Human production candidate

Model człowieka ma cztery rozdzielone warstwy: fizyczny profil w centymetrach, kanoniczną pozę,
osadzenie w scenie i projekcję 2D/pseudo-2.5D. Renderer SVG nie wyznacza wymiarów fizycznych;
otrzymuje gotowe punkty projekcji. Przeniesienie postaci w inne miejsce ponownie projektuje profil
z lokalnym `px/cm`, zamiast skalować aktualne piksele.

Wymiary pochodzące z profilu są oznaczone `DERIVED_DISPLAY_APPROXIMATION`. Wartość podana przez
użytkownika ma `USER_PROVIDED` i ma pierwszeństwo. Te przybliżenia służą wyłącznie do budowy
technicznego manekina — nie są wynikiem pomiaru ani oceną ergonomiczną.

## Publiczne API

- `getCanonicalHuman()` — model fizyczny i pochodzenie wymiarów,
- `getProjectedHuman()` — projekcja dla punktu kontaktu, skali i yaw,
- `getSceneObjectGeometry()` — geometria obiektu bez interpretacji ergonomicznej,
- `getHumanObjectRelations()` — jawne powiązania postaci z obiektem i celami dłoni,
- `getSceneCalibrationQuality()` — jakość kalibracji oddzielona od kompletności projektu.

## Podłoże i perspektywa

Status podłoża ma poziomy `GROUND_NONE`, `GROUND_BASIC`, `GROUND_LOCAL` i `GROUND_PROJECTIVE`.
Wersja v0.5 nie wykonuje pełnej homografii: istniejące referencje opisują lokalne pole pionowej
skali, ale zdjęcie bez wystarczających, niezależnych danych nie uzasadnia rekonstrukcji płaszczyzny
3D. Brak skali daje jawny stan `UNVERIFIED` i wymaga referencji blisko stóp.

## Diagnostyka

W development parametr `?debugHuman=1` pokazuje wzrost fizyczny, wysokość projekcji w pikselach,
lokalną skalę, root, yaw, stan podłoża i IK. Starszy, zdeformowany model można przebudować jawnie
przyciskiem „Napraw model postaci”; profil, punkt kontaktu, kierunek i powiązanie z obiektem zostają
zachowane.

Model pozostaje analizą 2D/pseudo-2.5D. Nie odtwarza niewidocznej głębokości, nie wykonuje oceny
ergonomicznej PHOTO_SCENE i nie zastępuje pomiaru stanowiska.
