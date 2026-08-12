import type { GeometryMeasurement, NormalizedPoint } from "../../types/photo-scene";

export type MeasurementLabelLayout = { id: string; anchor: NormalizedPoint; position: NormalizedPoint; leader: boolean; compact: boolean };

export function layoutMeasurementLabels(measurements: GeometryMeasurement[], zoom: number): MeasurementLabelLayout[] {
  const placed: MeasurementLabelLayout[] = [];
  const visible = measurements.filter((measurement) => measurement.visible && measurement.active);
  for (const measurement of visible) {
    const anchor = { x: (measurement.start.x + measurement.end.x) / 2, y: (measurement.start.y + measurement.end.y) / 2 };
    const candidates = [anchor, { x: anchor.x, y: anchor.y - .035 }, { x: anchor.x + .055, y: anchor.y }, { x: anchor.x, y: anchor.y + .04 }, { x: anchor.x - .055, y: anchor.y }].map(clampPoint);
    let position = candidates.find((candidate) => !placed.some((item) => overlaps(candidate, item.position, zoom))) ?? candidates.at(-1)!;
    const leader = position !== candidates[0], compact = zoom < .8 || placed.some((item) => overlaps(position, item.position, zoom));
    if (compact) position = clampPoint({ x: position.x, y: position.y + placed.length % 3 * .018 });
    placed.push({ id: measurement.id, anchor, position, leader, compact });
  }
  return placed;
}

function overlaps(a: NormalizedPoint, b: NormalizedPoint, zoom: number) { const width = .1 / Math.max(.7, zoom), height = .035 / Math.max(.7, zoom); return Math.abs(a.x - b.x) < width && Math.abs(a.y - b.y) < height; }
function clampPoint(point: NormalizedPoint) { return { x: Math.max(.04, Math.min(.96, point.x)), y: Math.max(.035, Math.min(.965, point.y)) }; }
