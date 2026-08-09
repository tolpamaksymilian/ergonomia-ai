import type { KeyMoment } from "./schemas";

export function rankAndDeduplicateKeyMoments(
  candidates: readonly KeyMoment[],
  options: { minimumGapSeconds?: number; limit?: number } = {},
): KeyMoment[] {
  const minimumGapSeconds = options.minimumGapSeconds ?? 0.75;
  const limit = options.limit ?? 8;
  const valid = candidates
    .filter((item) => Number.isFinite(item.time) && item.time >= 0 && Number.isFinite(item.rank))
    .sort((a, b) => b.rank - a.rank || (b.quality ?? -1) - (a.quality ?? -1) || a.time - b.time || a.id.localeCompare(b.id));
  const selected: KeyMoment[] = [];
  for (const candidate of valid) {
    const duplicate = selected.find((item) => Math.abs(item.time - candidate.time) < minimumGapSeconds);
    if (!duplicate) selected.push({ ...candidate });
    if (selected.length >= limit) break;
  }
  return selected.sort((a, b) => a.time - b.time || b.rank - a.rank);
}
