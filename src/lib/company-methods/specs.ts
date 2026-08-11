import chemicalSpec from "../../../method-specs/chemical-inhalation.json" with { type: "json" };
import hazardSpec from "../../../method-specs/hazards.json" with { type: "json" };
import manifestSpec from "../../../method-specs/manifest.json" with { type: "json" };
import measurableSpec from "../../../method-specs/measurable-factors.json" with { type: "json" };
import owasSpec from "../../../method-specs/owas.json" with { type: "json" };
import riskScoreSpec from "../../../method-specs/risk-score.json" with { type: "json" };

export const companyMethodSpecs = {
  manifest: manifestSpec,
  hazards: hazardSpec,
  riskScore: riskScoreSpec,
  measurable: measurableSpec,
  owas: owasSpec,
  chemical: chemicalSpec,
} as const;

export const hazardSuggestions = hazardSpec.hazards.map((item) => ({
  id: item.id,
  label: item.display_label,
  source: item.source,
  effects: item.effects,
}));
