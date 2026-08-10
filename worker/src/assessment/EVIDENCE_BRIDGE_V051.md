# Evidence bridge Pose V5.1 → Assessment

Assessment łączy klatki Pose i Metrics po `source_frame_index`; indeks pozycyjny pozostaje wyłącznie zgodnościowym fallbackiem dla starszych dokumentów. Czasem autorytatywnym jest `source_timestamp_seconds`.

## Automatyczne dowody

- `CAN_DERIVE`: zgięcie szyi i tułowia, elewacja ramienia, kąt łokcia oraz zgięcie nadgarstka — z poprawnych metryk geometrycznych.
- `CAN_DERIVE`: zgięcie kolana REBA — z wiarygodnych punktów biodro–kolano–kostka Pose. Rodzaj podparcia i rozkład ciężaru nadal pozostają nieznane.
- `CONDITIONAL`: odwiedzenie ramienia, przekroczenie linii środkowej, uniesienie barku oraz boczne zgięcie szyi/tułowia. Obecny kontrakt 2D nie dostarcza jeszcze wystarczającej, jawnie zwalidowanej geometrii dla każdego ustawienia kamery, więc składniki pozostają `UNKNOWN`.
- `CANNOT_DERIVE`: podparcie ramienia, pleców i stóp, jakość uchwytu, masa, siła oraz obciążenie zewnętrzne. Te dane wymagają pomiaru lub potwierdzenia człowieka.
- `CANNOT_DERIVE` w V5.1: dokładny skręt osiowy szyi, tułowia i przedramienia z pojedynczego obrazu 2D bez wiarygodnego dowodu głębi.

Brak dowodu nie jest zamieniany na zero ani korzystną kategorię. Silniki RULA i REBA zachowują wtedy wynik częściowy oraz jawny zakres możliwych wyników. Tablice punktowe metod nie zostały zmienione w Pose V5.1.
