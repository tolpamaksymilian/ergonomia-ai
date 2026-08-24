import type { DeviationBand, MetricPoint, TimelineSegment } from "./schemas";

type RawSegment = Omit<TimelineSegment, "id">;

export function mergeTimelineSegments(
  segments: readonly RawSegment[],
  maximumGapSeconds = 0.12,
): TimelineSegment[] {
  const sorted = segments
    .filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end) && item.start >= 0 && item.end >= item.start)
    .map((item) => ({ ...item }))
    .sort((a, b) => a.layer.localeCompare(b.layer) || a.track.localeCompare(b.track) || a.label.localeCompare(b.label) || a.start - b.start || a.end - b.end);
  const merged: RawSegment[] = [];
  for (const segment of sorted) {
    const previous = merged.at(-1);
    if (
      previous &&
      previous.layer === segment.layer &&
      previous.track === segment.track &&
      previous.band === segment.band &&
      previous.provenance === segment.provenance &&
      previous.usability === segment.usability &&
      previous.label === segment.label &&
      segment.start <= previous.end + maximumGapSeconds
    ) {
      previous.end = Math.max(previous.end, segment.end);
      previous.quality = minimumNullable(previous.quality, segment.quality);
      continue;
    }
    merged.push(segment);
  }
  return merged
    .sort((a, b) => a.start - b.start || a.layer.localeCompare(b.layer) || a.track.localeCompare(b.track))
    .map((item, index) => ({ ...item, id: `${item.layer}-${item.track}-${index}` }));
}

export function metricPointsToSegments(
  points: readonly MetricPoint[],
  track: string,
  label: string,
): TimelineSegment[] {
  const timelinePoints = points.length > 360 ? downsampleMetricPoints(points, 360) : points;
  const durations = estimatePointDurations(timelinePoints);
  return mergeTimelineSegments(
    timelinePoints.map((point, index) => ({
      layer: "posture" as const,
      track,
      label,
      start: point.time,
      end: point.time + durations[index],
      band: point.valid ? point.band : ("unknown" as DeviationBand),
      quality: point.quality,
      provenance: point.provenance,
      usability: point.usability,
      description: point.valid
        ? undefined
        : point.usability === "usable_for_timeline_only"
          ? "Ciągłość techniczna bez wartości użytej do obliczeń."
          : undefined,
    })),
  );
}

export function downsampleMetricPoints(
  points: readonly MetricPoint[],
  maximumPoints = 520,
): MetricPoint[] {
  if (maximumPoints < 8 || points.length <= maximumPoints) return points.map((point) => ({ ...point }));
  const output = new Map<number, MetricPoint>();
  const first = points[0];
  const last = points.at(-1);
  if (first) output.set(0, first);
  if (last) output.set(points.length - 1, last);
  const buckets = Math.max(1, Math.floor((maximumPoints - 2) / 4));
  const bucketSize = points.length / buckets;
  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const start = Math.floor(bucket * bucketSize);
    const end = Math.min(points.length, Math.ceil((bucket + 1) * bucketSize));
    const valid: Array<{ point: MetricPoint; index: number }> = [];
    for (let index = start; index < end; index += 1) {
      const point = points[index];
      if (!point) continue;
      if (point.valid && point.value !== null) valid.push({ point, index });
      if (!point.valid && (index === start || points[index - 1]?.valid || points[index + 1]?.valid)) output.set(index, point);
    }
    if (valid.length) {
      const byValue = [...valid].sort((a, b) => (a.point.value ?? 0) - (b.point.value ?? 0));
      const byQuality = [...valid].sort((a, b) => (a.point.quality ?? 1) - (b.point.quality ?? 1));
      for (const selected of [valid[0], byValue[0], byValue.at(-1), byQuality[0], valid.at(-1)]) {
        if (selected) output.set(selected.index, selected.point);
      }
    }
  }
  return [...output.entries()]
    .sort(([left], [right]) => left - right)
    .slice(0, maximumPoints)
    .map(([, point]) => ({ ...point }));
}

function estimatePointDurations(points: readonly MetricPoint[]): number[] {
  const positive = points.slice(1).map((point, index) => point.time - (points[index]?.time ?? point.time)).filter((value) => value > 0 && Number.isFinite(value));
  const fallback = positive.length ? positive[Math.floor(positive.length / 2)] ?? 0 : 0;
  return points.map((point, index) => {
    const next = points[index + 1];
    const delta = next ? next.time - point.time : fallback;
    return delta > 0 && Number.isFinite(delta) ? delta : fallback;
  });
}

function minimumNullable(first: number | null | undefined, second: number | null | undefined): number | null {
  const values = [first, second].filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return values.length ? Math.min(...values) : null;
}
