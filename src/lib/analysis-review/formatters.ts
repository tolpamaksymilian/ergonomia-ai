export const UNKNOWN_VALUE = "Brak danych";

export function formatTimestamp(value: number | null | undefined): string {
  if (!isFiniteNumber(value) || value < 0) return UNKNOWN_VALUE;
  const totalTenths = Math.round(value * 10);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = (totalTenths % 600) / 10;
  return `${String(minutes).padStart(2, "0")}:${seconds.toFixed(1).padStart(4, "0")}`;
}

export function formatDuration(value: number | null | undefined): string {
  if (!isFiniteNumber(value) || value < 0) return UNKNOWN_VALUE;
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes} min ${seconds} s`;
}

export function formatAngle(value: number | null | undefined): string {
  return isFiniteNumber(value) ? `${Math.round(value)}°` : UNKNOWN_VALUE;
}

export function formatRatio(value: number | null | undefined): string {
  return isFiniteNumber(value) ? value.toLocaleString("pl-PL", { maximumFractionDigits: 2 }) : UNKNOWN_VALUE;
}

export function formatPercentage(value: number | null | undefined): string {
  return isFiniteNumber(value)
    ? new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 1 }).format(Math.max(0, Math.min(1, value)))
    : UNKNOWN_VALUE;
}

export function frameToTime(frame: number | null | undefined, fps: number | null | undefined): number | null {
  return isFiniteNumber(frame) && frame >= 0 && isFiniteNumber(fps) && fps > 0 ? frame / fps : null;
}

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
