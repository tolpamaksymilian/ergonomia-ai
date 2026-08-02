import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <section className="mx-auto flex min-h-screen max-w-7xl flex-col justify-center px-6 py-20">
        <div className="max-w-4xl">
          <p className="mb-6 text-sm font-semibold uppercase tracking-[0.3em] text-emerald-400">
            Ergonomia wspierana przez AI
          </p>

          <h1 className="text-5xl font-bold leading-tight sm:text-6xl lg:text-7xl">
            Analiza ergonomii pracy na podstawie nagrań wideo
          </h1>

          <p className="mt-8 max-w-3xl text-lg leading-8 text-slate-300">
            Ergonomia AI analizuje pozycję pracownika, kąty ciała,
            czas utrzymywania obciążających pozycji oraz poziom ryzyka.
            System będzie wspierał ocenę REBA, RULA i własne metody
            konfigurowane w panelu administratora.
          </p>

          <div className="mt-10 flex flex-wrap gap-4">
            <Link
              href="/test-bazy"
              className="rounded-xl bg-emerald-500 px-6 py-3 font-semibold text-slate-950 transition hover:bg-emerald-400"
            >
              Sprawdź status systemu
            </Link>

            <Link
              href="/o-projekcie"
              className="rounded-xl border border-slate-700 px-6 py-3 font-semibold transition hover:border-slate-500 hover:bg-slate-900"
            >
              Dowiedz się więcej
            </Link>
          </div>
        </div>

        <div className="mt-20 grid gap-6 md:grid-cols-3">
          <FeatureCard
            title="Analiza postawy"
            description="Pomiar karku, tułowia, ramion, łokci, dłoni, bioder, kolan i nóg."
          />

          <FeatureCard
            title="Reguły administratora"
            description="Edytowalne kąty, czasy, progi, punktacja, poziomy ryzyka i rekomendacje."
          />

          <FeatureCard
            title="Raporty i film"
            description="Wykresy, krytyczne momenty, film ze szkieletem oraz raport PDF."
          />
        </div>
      </section>
    </main>
  );
}

type FeatureCardProps = {
  title: string;
  description: string;
};

function FeatureCard({ title, description }: FeatureCardProps) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-3 leading-7 text-slate-400">{description}</p>
    </article>
  );
}