export type AnalysisContext = {
  schema_version: "1.0";
  process_name: string | null;
  activity_description: string | null;
  department: string | null;
  area: string | null;
  line_machine: string | null;
  notes: string | null;
  author_name: string | null;
};

export type Workstation = {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  department: string | null;
  area: string | null;
  is_active: boolean;
};

export type AnalysisCategoryGroup = string;
export type AnalysisCategory = {
  id: string;
  name: string;
  group_name: AnalysisCategoryGroup;
  description: string | null;
  is_active: boolean;
};

export type AnalysisMetadata = {
  title: string;
  description: string | null;
  analysis_date: string | null;
  workstation: Workstation | null;
  categories: AnalysisCategory[];
  context: AnalysisContext;
};

export type MissingContextQuestion = {
  id: keyof Omit<AnalysisContext, "schema_version"> | "workstation";
  label: string;
  section: "workstation" | "methods" | "additional";
  neededFor: string[];
};

export type AnalysisCompleteness = {
  completed: number;
  total: number;
  ratio: number;
  percentage: number;
  missing: MissingContextQuestion[];
};

const EMPTY_CONTEXT: AnalysisContext = {
  schema_version: "1.0",
  process_name: null,
  activity_description: null,
  department: null,
  area: null,
  line_machine: null,
  notes: null,
  author_name: null,
};

export function normalizeAnalysisContext(value: unknown): AnalysisContext {
  if (!isRecord(value)) return { ...EMPTY_CONTEXT };
  return {
    schema_version: "1.0",
    process_name: optionalText(value.process_name, 120),
    activity_description: optionalText(value.activity_description, 2000),
    department: optionalText(value.department, 120),
    area: optionalText(value.area, 120),
    line_machine: optionalText(value.line_machine, 120),
    notes: optionalText(value.notes, 4000),
    author_name: optionalText(value.author_name, 120),
  };
}

export function calculateAnalysisCompleteness(metadata: Pick<AnalysisMetadata, "workstation" | "context">): AnalysisCompleteness {
  const questions: MissingContextQuestion[] = [
    { id: "workstation", label: "Wybierz stanowisko pracy", section: "workstation", neededFor: ["organizacja historii", "raport"] },
    { id: "process_name", label: "Jaki proces lub czynność jest analizowana?", section: "workstation", neededFor: ["raport"] },
    { id: "activity_description", label: "Opisz analizowaną czynność", section: "additional", neededFor: ["interpretacja specjalisty"] },
    { id: "department", label: "Podaj dział", section: "workstation", neededFor: ["raport"] },
    { id: "area", label: "Podaj obszar lub lokalizację", section: "workstation", neededFor: ["raport"] },
    { id: "author_name", label: "Podaj autora analizy", section: "additional", neededFor: ["identyfikowalność"] },
  ];
  const missing = questions.filter((question) => question.id === "workstation" ? !metadata.workstation : !metadata.context[question.id]);
  const completed = questions.length - missing.length;
  return { completed, total: questions.length, ratio: completed / questions.length, percentage: Math.round((completed / questions.length) * 100), missing };
}

function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function optionalText(value: unknown, max: number): string | null { return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null; }
