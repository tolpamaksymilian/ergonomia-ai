export type AuthorProfile = {
  name: string;
  role: string;
  summary: string;
  about: string;
  education: string;
  focusAreas: readonly {
    title: string;
    description: string;
  }[];
  experience: readonly {
    title: string;
    description: string;
  }[];
  projectMotivation: readonly string[];
  developmentDirections: readonly string[];
};

export const authorProfile = {
  name: "Maksymilian Tołpa",
  role: "Autor projektu Ergonomia AI",
  summary:
    "Student informatyki rozwijający aplikacje internetowe, automatyzacje i rozwiązania wykorzystujące sztuczną inteligencję.",
  about:
    "Łączę wiedzę techniczną z doświadczeniem zdobytym w środowisku produkcyjnym oraz przy projektach IT i HR. Tworzę rozwiązania, które upraszczają pracę, porządkują dane i pomagają podejmować lepsze decyzje.",
  education: "Informatyka — WSIiZ w Rzeszowie",
  focusAreas: [
    { title: "Aplikacje internetowe", description: "Projektuję czytelne serwisy i narzędzia działające w przeglądarce." },
    { title: "Automatyzacja procesów", description: "Łączę powtarzalne etapy w prostsze, kontrolowane przepływy pracy." },
    { title: "Analiza danych", description: "Porządkuję dane tak, aby łatwiej było je zrozumieć i wykorzystać." },
    { title: "Sztuczna inteligencja", description: "Sprawdzam, gdzie modele AI mogą realnie wspierać codzienną pracę." },
  ],
  experience: [
    { title: "Informatyka", description: "Studia rozwijają mój warsztat programistyczny i podejście do projektowania systemów." },
    { title: "Produkcja, IT i HR", description: "Doświadczenia z różnych środowisk pomagają mi patrzeć na technologię z perspektywy użytkownika." },
    { title: "Strony i komunikacja", description: "Tworzę materiały cyfrowe, które łączą funkcjonalność z jasnym przekazem." },
  ],
  projectMotivation: [
    "Projekt powstał z połączenia zainteresowania technologią, doświadczeń ze środowiska produkcyjnego i potrzeby prostszego analizowania ergonomii pracy.",
    "Celem jest stworzenie narzędzia, które zamienia film w uporządkowane dane i ułatwia dalszą ocenę stanowiska.",
  ],
  developmentDirections: [
    "Rozwój analizy wideo",
    "Walidacja wyników",
    "Czytelniejsze raportowanie",
    "Projektowanie stanowisk przed ich budową",
  ],
} as const satisfies AuthorProfile;
