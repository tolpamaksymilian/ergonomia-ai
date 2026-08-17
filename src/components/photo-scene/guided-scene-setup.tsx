"use client";

import {
  AlertTriangle,
  ArrowRight,
  Check,
  CircleDot,
  Cuboid,
  Eye,
  EyeOff,
  LoaderCircle,
  Pencil,
  Plus,
  Ruler,
  ScanSearch,
  Sparkles,
  Trash2,
  UserRound,
} from "lucide-react";

import { GuidedCalibrationForm, type GuidedReferenceInput } from "@/components/photo-scene/guided-calibration";
import {
  GUIDED_SCENE_SETUP_VERSION,
  GUIDED_SCENE_STEPS,
  measurementAssociationSuggestions,
  type GuidedSceneStepId,
  type GuidedSetupStatus,
} from "@/lib/photo-scene/guided-setup";
import type {
  CalibrationReference,
  NormalizedPoint,
  ReferenceDimensionType,
  SceneObject,
  SceneObjectType,
  SceneRegionType,
  SceneState,
} from "@/types/photo-scene";

type MeasurementDraft = { start: NormalizedPoint; end: NormalizedPoint; objectId: string | null };

export type GuidedSceneSetupProps = {
  state: SceneState;
  step: GuidedSceneStepId;
  status: GuidedSetupStatus;
  processingStage: string | null;
  detectionCount: number;
  measurementDraft: MeasurementDraft | null;
  measurementType: ReferenceDimensionType;
  buildBusy: boolean;
  buildError: string | null;
  reconstructionError: string | null;
  onStepChange: (step: GuidedSceneStepId) => void;
  onStartRegion: (type: SceneRegionType) => void;
  onStartMeasurement: (type: ReferenceDimensionType, referenceId?: string) => void;
  onSaveMeasurement: (input: GuidedReferenceInput) => void;
  onCancelMeasurement: () => void;
  onDeleteReference: (referenceId: string) => void;
  onToggleReference: (referenceId: string) => void;
  onAddObject: (type: SceneObjectType) => void;
  onAddObjectSurface: (objectId: string, type: SceneRegionType) => void;
  onAssociateMeasurement: (referenceId: string, objectId: string) => void;
  onBuild: () => Promise<void>;
  onReview: () => void;
  onOpenHuman: () => void;
  onOpenErgonomics: () => void;
  onAdvanced: () => void;
  humanEditor?: React.ReactNode;
  ergonomicsPanel?: React.ReactNode;
};

const HEIGHT_TYPES: Array<{ type: ReferenceDimensionType; label: string }> = [
  { type: "WORK_SURFACE_HEIGHT", label: "Wysokość blatu" },
  { type: "SHELF_HEIGHT", label: "Wysokość półki" },
  { type: "HEIGHT", label: "Monitor / panel / maszyna" },
  { type: "REACH_HEIGHT", label: "Punkt nad podłogą" },
  { type: "HEIGHT", label: "Inna wysokość" },
];

const OBJECT_TYPES: Array<{ type: SceneObjectType; label: string }> = [
  { type: "TABLE", label: "Blat / stół" }, { type: "MONITOR", label: "Monitor" },
  { type: "RACK", label: "Regał" }, { type: "SHELF", label: "Półka" },
  { type: "MACHINE", label: "Maszyna" }, { type: "CONTROL_PANEL", label: "Panel" },
  { type: "CONTAINER", label: "Pojemnik" }, { type: "CHAIR", label: "Krzesło" },
  { type: "HANDLE", label: "Uchwyt" }, { type: "TOOL", label: "Narzędzie" },
  { type: "OBSTACLE", label: "Przeszkoda" }, { type: "OTHER", label: "Inny obiekt" },
];

export function GuidedSceneSetup(props: GuidedSceneSetupProps) {
  const stepIndex = GUIDED_SCENE_STEPS.findIndex((step) => step.id === props.step);
  return <div className="flex max-h-[78vh] flex-col">
    <header className="border-b border-border px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div><p className="text-[10px] font-bold uppercase tracking-[0.16em] text-primary">Guided Setup · {GUIDED_SCENE_SETUP_VERSION}</p><h2 className="mt-1 text-base font-bold">Krok {stepIndex + 1} z 9 · {GUIDED_SCENE_STEPS[stepIndex].label}</h2></div>
        <button type="button" onClick={props.onAdvanced} className="text-xs font-semibold text-primary hover:underline">Edytor zaawansowany</button>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-[width]" style={{ width: `${((stepIndex + 1) / GUIDED_SCENE_STEPS.length) * 100}%` }} /></div>
    </header>
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      {props.measurementDraft ? <GuidedCalibrationForm
        key={`${props.measurementDraft.start.x}:${props.measurementDraft.start.y}:${props.measurementType}`}
        start={props.measurementDraft.start}
        end={props.measurementDraft.end}
        objectName={props.state.objects.find((object) => object.id === props.measurementDraft?.objectId)?.name ?? null}
        verticalDirection={props.state.calibration.verticalDirection}
        initialType={props.measurementType}
        onSave={props.onSaveMeasurement}
        onCancel={props.onCancelMeasurement}
      /> : <StepContent {...props} />}
    </div>
  </div>;
}

function StepContent(props: GuidedSceneSetupProps) {
  switch (props.step) {
    case "PHOTO": return <PhotoSetupStep {...props} />;
    case "FLOOR": return <FloorSetupStep {...props} />;
    case "HEIGHTS": return <HeightSetupStep {...props} />;
    case "DIMENSIONS": return <DimensionSetupStep {...props} />;
    case "OBJECTS": return <ObjectSetupStep {...props} />;
    case "BUILD": return <SceneBuildStep {...props} />;
    case "VERIFY": return <SceneVerificationStep {...props} />;
    case "HUMAN": return <HumanSetupStep {...props} />;
    case "ERGONOMICS": return <ErgonomicsSetupStep {...props} />;
  }
}

export function PhotoSetupStep(props: GuidedSceneSetupProps) {
  return <StepCard icon={CircleDot} title="Zdjęcie jest gotowe" description="Sprawdź, czy widoczna jest podłoga, główne elementy stanowiska i obszar, w którym będzie ustawiony operator.">
    <StatusRow label="Obraz źródłowy" value="wczytany i zapisany prywatnie" complete />
    <NextButton onClick={() => props.onStepChange("FLOOR")}>Dalej — oznacz podłogę</NextButton>
  </StepCard>;
}

export function FloorSetupStep(props: GuidedSceneSetupProps) {
  return <div className="space-y-4">
    <StepCard icon={CircleDot} title="Gdzie może poruszać się pracownik?" description="Zaznacz widoczny obszar podłogi, po którym pracownik może się poruszać. Klikaj kolejne punkty po obrysie; Enter lub podwójne kliknięcie kończy polygon.">
      <details className="rounded-lg border border-border p-3 text-xs"><summary className="cursor-pointer font-semibold">Jak to zaznaczyć?</summary><pre className="mt-2 text-cyan-700 dark:text-cyan-300">1 ●──────● 2{"\n"}  ╲      ╱{"\n"}4 ●────● 3</pre><p className="mt-2 text-muted-foreground">Minimum 3 punkty, najlepiej 4 lub więcej. Linie nie powinny się przecinać.</p></details>
      <div className="grid gap-2 sm:grid-cols-2">
        <button type="button" onClick={() => props.onStartRegion("FLOOR_REGION")} className="ui-button-primary justify-center"><Plus className="size-4" />{props.status.hasFloor ? "Narysuj podłogę ponownie" : "Zaznacz podłogę"}</button>
        <button type="button" disabled={!props.status.hasFloor} onClick={() => props.onStartRegion("MOVEMENT_ZONE")} className="ui-button-secondary justify-center disabled:opacity-40"><Plus className="size-4" />{props.status.hasMovementZone ? "Zmień pole pracy" : "Zaznacz pole pracy"}</button>
      </div>
      <p className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">Podłoga opisuje widoczną płaszczyznę sceny. Pole pracy jest mniejszym obszarem, w którym wolno ustawić i przesuwać operatora. Po pierwszym obrysie pole pracy domyślnie kopiuje podłogę.</p>
      <StatusRow label="Podłoga" value={props.status.hasFloor ? "gotowa" : "wymagana"} complete={props.status.hasFloor} />
      <StatusRow label="Pole pracy" value={props.status.hasMovementZone ? "gotowe" : "wymagane"} complete={props.status.hasMovementZone} />
      <NextButton disabled={!props.status.hasFloor || !props.status.hasMovementZone} onClick={() => props.onStepChange("HEIGHTS")}>Dalej — dodaj znane wysokości</NextButton>
    </StepCard>
  </div>;
}

export function HeightSetupStep(props: GuidedSceneSetupProps) {
  const validations = props.status.heightValidations;
  return <div className="space-y-4">
    <StepCard icon={Ruler} title="Dodaj znane wysokości" description="Wskaż minimum dwie rzeczywiste wysokości widoczne na zdjęciu. Najpierw kliknij punkt na podłodze, potem górny punkt.">
      <div className="grid grid-cols-2 gap-2">{HEIGHT_TYPES.map((item, index) => <button type="button" key={`${item.type}-${index}`} onClick={() => props.onStartMeasurement(item.type)} className="ui-button-secondary justify-center text-xs"><Plus className="size-3.5" />{item.label}</button>)}</div>
      <details className="rounded-lg border border-border p-3 text-xs"><summary className="cursor-pointer font-semibold">Jak to zaznaczyć?</summary><pre className="mt-2 text-cyan-700 dark:text-cyan-300">górny punkt ●{"\n"}            │ 80 cm{"\n"}podłoga     ●────</pre></details>
      <div className="space-y-2">{validations.map(({ reference, valid, reasons }, index) => <ReferenceRow key={reference.id} reference={reference} index={index + 1} valid={valid} reasons={reasons} onEdit={() => props.onStartMeasurement(reference.dimensionType, reference.id)} onDelete={() => props.onDeleteReference(reference.id)} onToggle={() => props.onToggleReference(reference.id)} />)}</div>
      {!validations.length && <Empty text="Nie dodano jeszcze żadnej pionowej wysokości." />}
      <div className={`rounded-xl border p-3 text-sm ${props.status.heightCount >= 2 ? "border-emerald-500/30 bg-emerald-500/10" : "border-amber-500/30 bg-amber-500/10"}`}><strong>{props.status.heightCount} / 2 poprawne wysokości</strong><p className="mt-1 text-xs text-muted-foreground">{props.status.heightCount < 2 ? `Dodaj jeszcze co najmniej ${2 - props.status.heightCount}.` : "Minimum osiągnięte. Więcej wysokości może poprawić stabilność rekonstrukcji."}</p></div>
      {props.status.spatialHeightAdvice && <Notice text={props.status.spatialHeightAdvice} />}
      <NextButton disabled={props.status.heightCount < 2} onClick={() => props.onStepChange("DIMENSIONS")}>Dalej — szerokości i głębokości</NextButton>
    </StepCard>
  </div>;
}

export function DimensionSetupStep(props: GuidedSceneSetupProps) {
  const dimensions = props.state.calibration.references.filter((reference) => reference.axis !== "VERTICAL");
  return <StepCard icon={Ruler} title="Dodaj znane szerokości i głębokości" description="Ten etap jest opcjonalny. Jeśli znasz te wartości, pomogą dokładniej odtworzyć perspektywę i bryły.">
    <div className="grid grid-cols-2 gap-2">
      <DimensionButton label="Szerokość" onClick={() => props.onStartMeasurement("WIDTH")} />
      <DimensionButton label="Głębokość" onClick={() => props.onStartMeasurement("DEPTH")} />
      <DimensionButton label="Odległość po podłodze" onClick={() => props.onStartMeasurement("DISTANCE")} />
      <DimensionButton label="Inny wymiar" onClick={() => props.onStartMeasurement("CUSTOM")} />
    </div>
    <details className="rounded-lg border border-border p-3 text-xs"><summary className="cursor-pointer font-semibold">Jak to zaznaczyć?</summary><div className="mt-2 grid grid-cols-2 gap-2 text-muted-foreground"><span><strong className="text-foreground">Szerokość</strong><br />A ●────● B</span><span><strong className="text-foreground">Głębokość</strong><br />przód ●──● tył</span></div></details>
    <div className="space-y-2">{dimensions.map((reference, index) => <ReferenceRow key={reference.id} reference={reference} index={index + 1} valid={reference.active} reasons={[]} onEdit={() => props.onStartMeasurement(reference.dimensionType, reference.id)} onDelete={() => props.onDeleteReference(reference.id)} onToggle={() => props.onToggleReference(reference.id)} />)}</div>
    {!dimensions.length && <Empty text="Nie dodano dodatkowych wymiarów. Możesz bezpiecznie pominąć ten etap." />}
    <NextButton onClick={() => props.onStepChange("OBJECTS")}>{dimensions.length ? "Dalej — zaznacz obiekty" : "Pomiń dodatkowe wymiary"}</NextButton>
  </StepCard>;
}

export function ObjectSetupStep(props: GuidedSceneSetupProps) {
  return <StepCard icon={Cuboid} title="Co jest czym?" description="Wybierz typ, a następnie obrysuj obiekt lub powierzchnię polygonem. Dane ręczne mają pierwszeństwo przed detektorem.">
    <div className="grid grid-cols-2 gap-2">{OBJECT_TYPES.map((item) => <button type="button" key={item.type} onClick={() => props.onAddObject(item.type)} className="ui-button-secondary justify-center text-xs"><Plus className="size-3.5" />{item.label}</button>)}</div>
    <details className="rounded-lg border border-border p-3 text-xs"><summary className="cursor-pointer font-semibold">Jak to zaznaczyć?</summary><p className="mt-2 text-muted-foreground">Stół: obrys blatu. Monitor: obrys ekranu. Regał: główny obrys, potem opcjonalne półki. Maszyna: główny region, potem blat lub panel sterowania.</p></details>
    <div className="space-y-2">{props.state.objects.filter((object) => object.status !== "USER_REJECTED").map((object) => <GuidedObjectCard key={object.id} object={object} state={props.state} onSurface={props.onAddObjectSurface} onAssociate={props.onAssociateMeasurement} />)}</div>
    {!props.status.objectCount && <Empty text="Nie oznaczono obiektów. Worker może nadal wystartować po podłodze i dwóch wysokościach, ale ręczne obrysy zwykle poprawiają wynik." />}
    <NextButton disabled={!props.status.canBuild} onClick={() => props.onStepChange("BUILD")}>Dalej — rozpoznaj i zbuduj scenę</NextButton>
  </StepCard>;
}

export function SceneBuildStep(props: GuidedSceneSetupProps) {
  const detectionRunning = ["ready-for-scene-detection", "scene-detection-processing"].includes(props.processingStage ?? "");
  const reconstructionRunning = ["QUEUED", "SOLVING"].includes(props.state.reconstructionState.status);
  const running = props.buildBusy || detectionRunning || reconstructionRunning;
  return <StepCard icon={ScanSearch} title="Rozpoznaj i zbuduj scenę" description="Worker otrzyma oryginalne zdjęcie oraz wszystkie ręczne obrysy, wymiary i relacje. Najpierw wyszuka dodatkowe elementy, potem dopasuje geometrię sceny.">
    <div className="grid grid-cols-2 gap-2 text-xs">
      <StatusRow label="Podłoga i ruch" value={props.status.hasFloor && props.status.hasMovementZone ? "gotowe" : "brak"} complete={props.status.hasFloor && props.status.hasMovementZone} />
      <StatusRow label="Wysokości" value={`${props.status.heightCount} poprawne`} complete={props.status.heightCount >= 2} />
      <StatusRow label="Dodatkowe wymiary" value={String(props.status.dimensionCount)} complete={props.status.dimensionCount > 0} optional />
      <StatusRow label="Obiekty ręczne" value={String(props.status.objectCount)} complete={props.status.objectCount > 0} optional />
    </div>
    {running && <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3 text-sm"><LoaderCircle className="mr-2 inline size-4 animate-spin" />{detectionRunning ? "Rozpoznawanie obrazu z kontekstem użytkownika…" : "Rekonstrukcja geometrii sceny…"}</div>}
    {props.buildError && <ErrorNotice text={props.buildError} />}
    {props.reconstructionError && <ErrorNotice text={props.reconstructionError} />}
    <button type="button" disabled={!props.status.canBuild || running} onClick={() => void props.onBuild()} className="ui-button-primary w-full justify-center py-3 text-sm disabled:cursor-not-allowed disabled:opacity-45"><ScanSearch className="size-5" />{running ? "Budowanie sceny…" : "Rozpoznaj i zbuduj scenę"}</button>
    {!props.status.canBuild && <p className="text-xs text-amber-700 dark:text-amber-300">Najpierw dodaj podłogę, pole pracy i minimum dwie poprawne wysokości.</p>}
    {props.status.reconstructionReady && <NextButton onClick={() => props.onStepChange("VERIFY")}>Dalej — sprawdź geometrię</NextButton>}
  </StepCard>;
}

export function SceneVerificationStep(props: GuidedSceneSetupProps) {
  const reconstruction = props.state.reconstructionState;
  return <StepCard icon={Check} title="Sprawdź wynik geometrii" description="Porównaj obrysy i wymiary ze zdjęciem. Wynik częściowy jest jawny — brakujące dane nie są wymyślane.">
    <div className="grid grid-cols-2 gap-2"><StatusRow label="Status" value={reconstruction.status} complete={["SOLVED", "PARTIAL"].includes(reconstruction.status)} /><StatusRow label="Wykryte dodatkowo" value={String(props.detectionCount)} complete optional /></div>
    {!!reconstruction.conflicts.length && <section className="rounded-xl border border-red-500/30 bg-red-500/10 p-3"><strong className="text-sm">Konflikty ({reconstruction.conflicts.length})</strong>{reconstruction.conflicts.map((conflict) => <p key={conflict.id} className="mt-2 text-xs">{conflict.message}</p>)}</section>}
    {!!reconstruction.autoRepairs.length && <section className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3"><strong className="text-sm">Sugerowane Auto Repair ({reconstruction.autoRepairs.length})</strong>{reconstruction.autoRepairs.slice(0, 4).map((repair) => <p key={repair.id} className="mt-2 text-xs">{repair.reason}</p>)}</section>}
    {reconstruction.nextBestMeasurements[0] && <section className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3"><p className="text-[10px] font-bold uppercase text-cyan-700 dark:text-cyan-300">Najważniejszy kolejny pomiar</p><strong className="mt-1 block text-sm">{reconstruction.nextBestMeasurements[0].reason}</strong><button type="button" onClick={() => props.onStartMeasurement(typeForKind(reconstruction.nextBestMeasurements[0].measurementKind))} className="mt-3 text-xs font-bold text-primary">Dodaj ten pomiar →</button></section>}
    <div className="grid grid-cols-2 gap-2"><button type="button" onClick={() => props.onStepChange("HEIGHTS")} className="ui-button-secondary justify-center"><Pencil className="size-4" />Popraw dane</button><button type="button" disabled={!props.status.reconstructionReady} onClick={props.onReview} className="ui-button-primary justify-center disabled:opacity-45"><Check className="size-4" />Wszystko wygląda poprawnie</button></div>
  </StepCard>;
}

function HumanSetupStep(props: GuidedSceneSetupProps) {
  return <StepCard icon={UserRound} title="Dodaj i ustaw operatora" description="Operator jest dostępny dopiero po potwierdzeniu geometrii. Jego stopy są ograniczane do pola pracy, a skala korzysta z lokalnego modelu pionowego.">
    <StatusRow label="Weryfikacja geometrii" value={props.status.reconstructionReviewed ? "potwierdzona" : "wymagana"} complete={props.status.reconstructionReviewed} />
    <StatusRow label="Operatorzy" value={String(props.status.humanCount)} complete={props.status.humanCount > 0} />
    <button type="button" disabled={!props.status.reconstructionReviewed} onClick={props.onOpenHuman} className="ui-button-primary w-full justify-center disabled:opacity-45"><UserRound className="size-4" />Otwórz ustawienia operatora</button>
    {props.humanEditor}
    {props.status.humanCount > 0 && <NextButton onClick={() => props.onStepChange("ERGONOMICS")}>Dalej — ergonomia</NextButton>}
  </StepCard>;
}

function ErgonomicsSetupStep(props: GuidedSceneSetupProps) {
  const humanReady = props.status.humanCount > 0;
  const geometryReady = props.state.reconstructionState.readiness.HUMAN_PLACEMENT.status === "READY";
  return <StepCard icon={Sparkles} title="Ergonomia" description="Ocena korzysta z istniejącego Scene Ergonomics Engine. Nie uruchomi się dla starej lub niewystarczającej geometrii.">
    <StatusRow label="Geometria operatora" value={props.state.reconstructionState.readiness.HUMAN_PLACEMENT.status} complete={geometryReady} />
    <StatusRow label="Operator" value={humanReady ? "dodany" : "brak"} complete={humanReady} />
    <button type="button" disabled={!humanReady || !geometryReady || !props.status.reconstructionReviewed} onClick={props.onOpenErgonomics} className="ui-button-primary w-full justify-center disabled:opacity-45"><Sparkles className="size-4" />Przejdź do ergonomii sceny</button>
    {humanReady && geometryReady && props.status.reconstructionReviewed ? props.ergonomicsPanel : null}
  </StepCard>;
}

function GuidedObjectCard({ object, state, onSurface, onAssociate }: { object: SceneObject; state: SceneState; onSurface: (objectId: string, type: SceneRegionType) => void; onAssociate: (referenceId: string, objectId: string) => void }) {
  const suggestions = measurementAssociationSuggestions(state, object);
  return <article className="rounded-xl border border-border p-3">
    <div className="flex items-center justify-between gap-3"><div><strong className="text-sm">{object.name}</strong><small className="block text-muted-foreground">{object.type} · {object.source === "USER" ? "oznaczenie ręczne" : "kandydat Workera"}</small></div><span className="rounded-full bg-primary/10 px-2 py-1 text-[10px] font-bold text-primary">{object.regionIds.length} obrysów</span></div>
    {(object.type === "RACK" || object.type === "MACHINE") && <div className="mt-2 flex gap-2">{object.type === "RACK" && <button type="button" onClick={() => onSurface(object.id, "SHELF_REGION")} className="text-xs font-semibold text-primary">+ Dodaj półkę</button>}{object.type === "MACHINE" && <><button type="button" onClick={() => onSurface(object.id, "WORK_SURFACE")} className="text-xs font-semibold text-primary">+ Powierzchnia pracy</button><button type="button" onClick={() => onSurface(object.id, "CONTROL_PANEL_REGION")} className="text-xs font-semibold text-primary">+ Panel</button></>}</div>}
    {suggestions.map((suggestion) => <div key={suggestion.referenceId} className="mt-3 rounded-lg bg-cyan-500/10 p-2 text-xs"><p>Wygląda na to, że „{suggestion.referenceName}” ({suggestion.valueCm} cm) dotyczy tego obiektu.</p><div className="mt-2 flex gap-3"><button type="button" onClick={() => onAssociate(suggestion.referenceId, object.id)} className="font-bold text-primary">Przypisz</button><span className="text-muted-foreground">Nie — pozostaw jako referencję sceny</span></div></div>)}
  </article>;
}

function ReferenceRow({ reference, index, valid, reasons, onEdit, onDelete, onToggle }: { reference: CalibrationReference; index: number; valid: boolean; reasons: string[]; onEdit: () => void; onDelete: () => void; onToggle: () => void }) {
  return <article className={`rounded-xl border p-3 ${valid ? "border-border" : "border-amber-500/40 bg-amber-500/5"}`}>
    <div className="flex items-start gap-2"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-[10px] font-bold">{index}</span><div className="min-w-0 flex-1"><strong className="block truncate text-sm">{reference.name}</strong><small className="text-muted-foreground">{reference.valueCm} cm · {reference.objectId ? "przypisany do obiektu" : "referencja sceny"}</small></div><button type="button" title={reference.visible ? "Ukryj" : "Pokaż"} onClick={onToggle}>{reference.visible ? <Eye className="size-4" /> : <EyeOff className="size-4" />}</button><button type="button" title="Zmień punkty" onClick={onEdit}><Pencil className="size-4" /></button><button type="button" title="Usuń" onClick={onDelete} className="text-red-600"><Trash2 className="size-4" /></button></div>
    {reasons.map((reason) => <p key={reason} className="mt-2 text-xs text-amber-700 dark:text-amber-300">{reason}</p>)}
  </article>;
}

function StepCard({ icon: Icon, title, description, children }: { icon: typeof Ruler; title: string; description: string; children: React.ReactNode }) {
  return <section className="space-y-4"><div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Icon className="size-5" /></span><div><h3 className="font-bold">{title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p></div></div>{children}</section>;
}

function StatusRow({ label, value, complete, optional = false }: { label: string; value: string; complete: boolean; optional?: boolean }) {
  return <div className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-border bg-card p-3 text-xs"><span>{label}{optional && <small className="ml-1 text-muted-foreground">(opcjonalne)</small>}</span><strong className={complete ? "text-emerald-600" : optional ? "text-muted-foreground" : "text-amber-600"}>{value}</strong></div>;
}

function NextButton({ children, disabled = false, onClick }: { children: React.ReactNode; disabled?: boolean; onClick: () => void }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="ui-button-primary w-full justify-center disabled:cursor-not-allowed disabled:opacity-40">{children}<ArrowRight className="size-4" /></button>;
}

function DimensionButton({ label, onClick }: { label: string; onClick: () => void }) { return <button type="button" onClick={onClick} className="ui-button-secondary justify-center text-xs"><Plus className="size-3.5" />{label}</button>; }
function Empty({ text }: { text: string }) { return <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">{text}</div>; }
function Notice({ text }: { text: string }) { return <div className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs"><AlertTriangle className="size-4 shrink-0" />{text}</div>; }
function ErrorNotice({ text }: { text: string }) { return <div role="alert" className="flex gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs"><AlertTriangle className="size-4 shrink-0" />{text}</div>; }

function typeForKind(kind: SceneState["reconstructionState"]["nextBestMeasurements"][number]["measurementKind"]): ReferenceDimensionType {
  if (["VERTICAL_HEIGHT", "OBJECT_HEIGHT", "SCREEN_HEIGHT"].includes(kind)) return "HEIGHT";
  if (kind === "WORK_SURFACE_HEIGHT") return "WORK_SURFACE_HEIGHT";
  if (kind === "SHELF_HEIGHT") return "SHELF_HEIGHT";
  if (["HORIZONTAL_WIDTH", "OBJECT_WIDTH"].includes(kind)) return "WIDTH";
  if (["DEPTH", "OBJECT_DEPTH"].includes(kind)) return "DEPTH";
  if (kind === "FLOOR_DISTANCE") return "DISTANCE";
  return "CUSTOM";
}
