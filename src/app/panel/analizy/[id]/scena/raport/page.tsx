import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Printer } from "lucide-react";

import { requireUser } from "@/lib/auth/access";
import { SCENE_ASSESSMENT_SCHEMA, type SceneAssessmentResult } from "@/lib/scene-ergonomics/types";

export const dynamic = "force-dynamic";

export default async function SceneDesignReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase } = await requireUser();
  const [{ data: analysis, error: analysisError }, { data: scene, error: sceneError }] = await Promise.all([
    supabase.from("analyses").select("id,title,analysis_type").eq("id", id).maybeSingle(),
    supabase.from("photo_scenes").select("scene_assessment_path,scene_assessed_at").eq("analysis_id", id).maybeSingle(),
  ]);

  if (analysisError || sceneError) throw new Error("Nie udało się pobrać raportu projektu.");
  if (!analysis || analysis.analysis_type !== "PHOTO_SCENE" || !scene?.scene_assessment_path) notFound();

  const { data: artifact, error: artifactError } = await supabase.storage
    .from("analysis-scenes")
    .download(scene.scene_assessment_path);
  if (artifactError || !artifact) throw new Error("Nie udało się pobrać prywatnego artefaktu oceny.");

  const assessment = await parseAssessment(artifact);

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-6 text-slate-950 print:bg-white print:p-0">
      <div className="mx-auto max-w-5xl space-y-5">
        <header className="flex flex-wrap items-center justify-between gap-3 print:hidden">
          <Link href={`/panel/analizy/${id}/scena`} className="ui-button-secondary">
            <ArrowLeft className="size-4" /> Wróć do sceny
          </Link>
          <span className="ui-button-secondary" title="Użyj polecenia drukowania przeglądarki (Ctrl+P)">
            <Printer className="size-4" /> Ctrl+P / Drukuj
          </span>
        </header>

        <article className="space-y-5 rounded-3xl bg-white p-6 shadow-sm print:rounded-none print:p-0 print:shadow-none sm:p-10">
          <header className="border-b border-slate-200 pb-6">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">Scene Design Report</p>
            <h1 className="mt-2 text-3xl font-black">{analysis.title}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              Projektowa analiza wspomagająca oparta na cyfrowym modelu człowieka i stanowiska. Wynik nie zastępuje oceny kompetentnego specjalisty.
            </p>
            <dl className="mt-5 grid gap-3 text-xs sm:grid-cols-3">
              <Meta label="Silnik" value={assessment.engineVersion} />
              <Meta label="Rewizja sceny" value={assessment.sceneRevision} />
              <Meta label="Data oceny" value={formatDate(scene.scene_assessed_at ?? assessment.calculatedAt)} />
            </dl>
          </header>

          <Section title="Najważniejsze findings">
            {assessment.findings.length ? assessment.findings.map((finding) => (
              <div key={finding.id} className="rounded-xl border border-slate-200 p-3">
                <strong className="text-xs uppercase text-cyan-800">{finding.priority} · {finding.type}</strong>
                <p className="mt-1 text-sm">{finding.description}</p>
                <p className="mt-1 text-xs text-slate-500">Reguła: {finding.rule} · jakość danych {Math.round(finding.quality * 100)}%</p>
              </div>
            )) : <Empty text="Brak findings dla dostępnych danych." />}
          </Section>

          {Object.entries(assessment.humans).map(([humanId, human]) => (
            <section key={humanId} className="space-y-4 border-t border-slate-200 pt-5">
              <h2 className="text-xl font-black">Operator {humanId}</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Section title="Postawa 3D">
                  {Object.entries(human.posture.jointAngles).slice(0, 16).map(([name, value]) => (
                    <Row key={name} label={name.replaceAll("_", " ")} value={value.valid ? `${formatNumber(value.value)} ${value.unit ?? ""}` : "UNKNOWN"} />
                  ))}
                </Section>
                <Section title="RULA / REBA">
                  <Row label="RULA lewa" value={methodValue(human.rula.left)} />
                  <Row label="RULA prawa" value={methodValue(human.rula.right)} />
                  <Row label="REBA lewa" value={methodValue(human.reba.left)} />
                  <Row label="REBA prawa" value={methodValue(human.reba.right)} />
                </Section>
                <Section title="Wysokość robocza">
                  {human.workHeight ? <>
                    <Row label="Powierzchnia" value={`${formatNumber(human.workHeight.surfaceHeightCm.value)} cm`} />
                    <Row label="Łokieć" value={`${formatNumber(human.workHeight.elbowHeightCm.value)} cm`} />
                    <Row label="Różnica" value={`${formatNumber(human.workHeight.differenceFromElbowCm.value)} cm`} />
                    <Row label="Charakter pracy" value={human.workHeight.taskType} />
                  </> : <Empty text="Brak kompletnej powierzchni roboczej." />}
                </Section>
                <Section title="Dosiężność i clearance">
                  <Row label="Punkty robocze" value={String(human.reach.length)} />
                  <Row label="Poza zasięgiem" value={String(human.reach.filter((item) => item.zone === "OUTSIDE_ZONE").length)} />
                  <Row label="Kontakty" value={String(human.clearance.filter((item) => item.level === "CONTACT").length)} />
                  <Row label="Penetracje" value={String(human.clearance.filter((item) => item.level === "PENETRATION").length)} />
                </Section>
              </div>
            </section>
          ))}

          <div className="grid gap-4 md:grid-cols-2">
            <Section title="Rekomendacje">
              {assessment.recommendations.length ? assessment.recommendations.map((item) => <p key={item.id} className="rounded-xl bg-slate-50 p-3 text-sm">{item.text}<span className="mt-1 block text-xs text-slate-500">{item.reason}</span></p>) : <Empty text="Brak rekomendacji dla dostępnych danych." />}
            </Section>
            <Section title="Brakujące dane">
              {assessment.missingData.length ? assessment.missingData.map((item) => <p key={item.id} className="rounded-xl bg-amber-50 p-3 text-sm"><strong>{item.label}</strong><span className="mt-1 block text-xs text-slate-600">{item.reason}</span></p>) : <Empty text="Nie zidentyfikowano brakujących danych." />}
            </Section>
          </div>

          {assessment.task && <Section title="Sekwencja zadania">
            <Row label="Liczba próbek" value={String(assessment.task.samples.length)} />
            <Row label="Najgorszy moment" value={assessment.task.worstSample ? `${assessment.task.worstSample.stepId} · ${Math.round(assessment.task.worstSample.progress * 100)}%` : "UNKNOWN"} />
            <Row label="Pierwsza kolizja" value={assessment.task.firstCollision ? `${assessment.task.firstCollision.stepId} · ${Math.round(assessment.task.firstCollision.progress * 100)}%` : "brak"} />
            <Row label="Ekspozycja" value={assessment.task.exposure.known ? `${formatNumber(assessment.task.exposure.totalDurationSeconds)} s` : "UNKNOWN"} />
          </Section>}

          <Section title="Ograniczenia i śledzenie wyniku">
            <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">{assessment.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
              <Meta label="Schema sceny" value={assessment.sceneSchemaVersion} />
              <Meta label="Schema oceny" value={assessment.schemaVersion} />
              <Meta label="Jakość" value={`${assessment.quality.overall} · ${Math.round(assessment.quality.coverage * 100)}% pokrycia`} />
            </dl>
          </Section>
        </article>
      </div>
    </main>
  );
}

async function parseAssessment(blob: Blob): Promise<SceneAssessmentResult> {
  let value: unknown;
  try { value = JSON.parse(await blob.text()); } catch { throw new Error("Artefakt oceny ma nieprawidłowy JSON."); }
  if (!value || typeof value !== "object" || (value as { schemaVersion?: unknown }).schemaVersion !== SCENE_ASSESSMENT_SCHEMA) {
    throw new Error("Artefakt oceny ma nieobsługiwany format.");
  }
  return value as SceneAssessmentResult;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="space-y-2 rounded-2xl border border-slate-200 p-4 print:break-inside-avoid"><h2 className="text-lg font-black">{title}</h2>{children}</section>;
}
function Row({ label, value }: { label: string; value: string }) { return <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-1 text-xs last:border-0"><span className="text-slate-500">{label}</span><strong className="text-right">{value}</strong></div>; }
function Meta({ label, value }: { label: string; value: string }) { return <div><dt className="uppercase tracking-wide text-slate-500">{label}</dt><dd className="mt-1 break-all font-semibold">{value}</dd></div>; }
function Empty({ text }: { text: string }) { return <p className="text-sm text-slate-500">{text}</p>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("pl-PL", { dateStyle: "long", timeStyle: "short" }).format(new Date(value)); }
function formatNumber(value: number | null) { return value === null ? "UNKNOWN" : String(Math.round(value * 10) / 10); }
function methodValue(method: SceneAssessmentResult["humans"][string]["rula"]["left"]) { return method.score !== null ? `${method.score} · ${method.status}` : method.scoreRange ? `${method.scoreRange.min}–${method.scoreRange.max} · ${method.status}` : method.status; }
