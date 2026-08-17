"use client";

import { Check, LockKeyhole } from "lucide-react";

import { GUIDED_SCENE_STEPS, type GuidedSceneStepId, type GuidedSetupStatus } from "@/lib/photo-scene/guided-setup";

export function SceneSetupStepper({
  current,
  status,
  onSelect,
}: {
  current: GuidedSceneStepId;
  status: GuidedSetupStatus;
  onSelect: (step: GuidedSceneStepId) => void;
}) {
  const currentIndex = GUIDED_SCENE_STEPS.findIndex((step) => step.id === current);
  return <nav aria-label="Konfiguracja sceny krok po kroku" className="ui-surface overflow-x-auto p-2">
    <ol className="grid min-w-[1080px] grid-cols-9 gap-2">
      {GUIDED_SCENE_STEPS.map((step, index) => {
        const done = stepDone(step.id, status);
        const available = stepAvailable(step.id, status) || index <= currentIndex;
        return <li key={step.id}>
          <button
            type="button"
            disabled={!available}
            onClick={() => onSelect(step.id)}
            aria-current={current === step.id ? "step" : undefined}
            className={`flex min-h-14 w-full items-center gap-2 rounded-xl px-2 text-left text-[11px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${current === step.id ? "bg-orange-500 text-white" : done ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-muted text-muted-foreground"}`}
          >
            <span className="grid size-6 shrink-0 place-items-center rounded-full border border-current text-[10px]">
              {done ? <Check className="size-3.5" /> : available ? index + 1 : <LockKeyhole className="size-3" />}
            </span>
            <span className="min-w-0 leading-4">{step.label}<small className="block font-normal opacity-75">{step.required ? "wymagane" : "opcjonalne"}</small></span>
          </button>
        </li>;
      })}
    </ol>
  </nav>;
}

export function stepAvailable(step: GuidedSceneStepId, status: GuidedSetupStatus) {
  if (step === "PHOTO" || step === "FLOOR") return status.hasImage;
  if (step === "HEIGHTS") return status.hasFloor && status.hasMovementZone;
  if (["DIMENSIONS", "OBJECTS", "BUILD"].includes(step)) return status.heightCount >= 2;
  if (step === "VERIFY") return status.reconstructionReady;
  if (step === "HUMAN") return status.reconstructionReviewed;
  if (step === "ERGONOMICS") return status.reconstructionReviewed && status.humanCount > 0;
  return false;
}

function stepDone(step: GuidedSceneStepId, status: GuidedSetupStatus) {
  switch (step) {
    case "PHOTO": return status.hasImage;
    case "FLOOR": return status.hasFloor && status.hasMovementZone;
    case "HEIGHTS": return status.heightCount >= 2;
    case "DIMENSIONS": return status.dimensionCount > 0;
    case "OBJECTS": return status.objectCount > 0;
    case "BUILD": return status.reconstructionReady;
    case "VERIFY": return status.reconstructionReviewed;
    case "HUMAN": return status.humanCount > 0;
    case "ERGONOMICS": return false;
  }
}
