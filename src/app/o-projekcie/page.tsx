import Link from "next/link";

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-20 text-white">
      <div className="mx-auto max-w-5xl">
        <Link
          href="/"
          className="text-sm font-semibold text-emerald-400 hover:text-emerald-300"
        >
          ← Powrót do strony głównej
        </Link>

        <p className="mt-12 text-sm font-semibold uppercase tracking-[0.3em] text-emerald-400">
          O projekcie
        </p>

        <h1 className="mt-5 text-4xl font-bold leading-tight sm:text-6xl">
          System wspierający analizę ergonomii pracy
        </h1>

        <p className="mt-8 max-w-4xl text-lg leading-8 text-slate-300">
          Ergonomia AI będzie analizować nagrania stanowisk pracy,
          wykrywać pozycję pracownika, obliczać kąty części ciała oraz
          rozpoznawać czas utrzymywania obciążających pozycji.
        </p>

        <div className="mt-14 grid gap-6 md:grid-cols-2">
          <Section
            title="Analiza obrazu"
            description="System będzie wykrywać sylwetkę, dłonie, kończyny, tułów oraz wybrane przedmioty znajdujące się na stanowisku pracy."
          />

          <Section
            title="Edytowalne reguły"
            description="Administrator będzie mógł ustalać zakresy kątów, wymagany czas pozycji, punktację, poziomy ryzyka i rekomendacje."
          />

          <Section
            title="Metody oceny"
            description="System będzie wspierał REBA, RULA oraz własne metody oceny przygotowane dla konkretnych stanowisk."
          />

          <Section
            title="Wyniki"
            description="Użytkownik otrzyma wykresy, krytyczne momenty filmu, ocenę ryzyka, film z oznaczeniami oraz raport PDF."
          />
        </div>

        <div className="mt-14 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
          <h2 className="text-xl font-semibold text-amber-200">
            Ważna informacja
          </h2>

          <p className="mt-3 leading-7 text-amber-100/80">
            System będzie narzędziem wspierającym specjalistę i nie będzie
            zastępował profesjonalnej oceny ergonomicznej stanowiska pracy.
          </p>
        </div>
      </div>
    </main>
  );
}

type SectionProps = {
  title: string;
  description: string;
};

function Section({ title, description }: SectionProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-7">
      <h2 className="text-2xl font-semibold">{title}</h2>
      <p className="mt-4 leading-7 text-slate-400">{description}</p>
    </section>
  );
}