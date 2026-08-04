export type AuthorProfile = {
  name: string;
  role: string;
  summary: string;
  education: string;
  interests: readonly string[];
  projectMotivation: readonly string[];
};

export const authorProfile = {
  name: "Maksymilian Tołpa",
  role: "Autor projektu Ergonomia AI",
  summary:
    "Student informatyki, który łączy rozwój aplikacji, automatyzację i doświadczenie ze środowiska produkcyjnego.",
  education: "Informatyka — WSIiZ w Rzeszowie",
  interests: [
    "Sztuczna inteligencja",
    "Automatyzacja procesów",
    "Ergonomia i bezpieczeństwo pracy",
    "Aplikacje internetowe",
    "Analiza danych",
  ],
  projectMotivation: [
    "Projekt powstał z połączenia zainteresowania technologią, doświadczeń ze środowiska produkcyjnego i potrzeby prostszego analizowania ergonomii pracy.",
    "Jego celem jest porządkowanie danych z nagrań tak, aby specjalista mógł szybciej przejść do właściwej oceny.",
  ],
} as const satisfies AuthorProfile;
