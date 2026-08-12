import type { NormalizedPoint } from "../../types/photo-scene";

export type ScreenPoint = { x: number; y: number };
export type ImagePixelPoint = { x: number; y: number };
export type EditorViewportRect = { left: number; top: number; width: number; height: number };
export type SceneViewport = { zoom: number; pan_x: number; pan_y: number };

export type DisplayedImageRect = EditorViewportRect & {
  scale: number;
  right: number;
  bottom: number;
};

export type SceneTransform = {
  viewportRect: EditorViewportRect;
  displayedImageRect: DisplayedImageRect;
  transformedImageRect: DisplayedImageRect;
  intrinsicWidth: number;
  intrinsicHeight: number;
  viewport: SceneViewport;
};

export type PointerCoordinates = {
  screen: ScreenPoint;
  viewport: ScreenPoint;
  imageNormalized: NormalizedPoint;
  imagePixels: ImagePixelPoint;
  insideImage: boolean;
  displayedImageRect: DisplayedImageRect;
  transformedImageRect: DisplayedImageRect;
};

const EPSILON = 1e-9;

/** Calculates the exact content rectangle produced by preserveAspectRatio/object-fit: contain. */
export function getContainedImageRect(
  container: EditorViewportRect,
  intrinsicWidth: number,
  intrinsicHeight: number,
  alignment: { x: number; y: number } = { x: 0.5, y: 0.5 },
): DisplayedImageRect {
  assertPositiveRect(container);
  assertPositiveDimension(intrinsicWidth, "intrinsicWidth");
  assertPositiveDimension(intrinsicHeight, "intrinsicHeight");
  const scale = Math.min(container.width / intrinsicWidth, container.height / intrinsicHeight);
  const width = intrinsicWidth * scale;
  const height = intrinsicHeight * scale;
  const left = container.left + (container.width - width) * clamp01(alignment.x);
  const top = container.top + (container.height - height) * clamp01(alignment.y);
  return { left, top, width, height, scale, right: left + width, bottom: top + height };
}

/** Single image-to-screen affine transform used by every Scene Builder tool. */
export function getSceneTransform(
  viewportRect: EditorViewportRect,
  intrinsicWidth: number,
  intrinsicHeight: number,
  viewport: SceneViewport,
): SceneTransform {
  if (!Number.isFinite(viewport.zoom) || viewport.zoom <= 0) throw new RangeError("zoom must be a positive finite number");
  if (!Number.isFinite(viewport.pan_x) || !Number.isFinite(viewport.pan_y)) throw new RangeError("pan must be finite");
  const displayedImageRect = getContainedImageRect(viewportRect, intrinsicWidth, intrinsicHeight);
  const width = displayedImageRect.width * viewport.zoom;
  const height = displayedImageRect.height * viewport.zoom;
  const centerX = displayedImageRect.left + displayedImageRect.width / 2 + viewport.pan_x * displayedImageRect.width;
  const centerY = displayedImageRect.top + displayedImageRect.height / 2 + viewport.pan_y * displayedImageRect.height;
  const left = centerX - width / 2;
  const top = centerY - height / 2;
  return {
    viewportRect,
    displayedImageRect,
    transformedImageRect: {
      left,
      top,
      width,
      height,
      scale: displayedImageRect.scale * viewport.zoom,
      right: left + width,
      bottom: top + height,
    },
    intrinsicWidth,
    intrinsicHeight,
    viewport,
  };
}

/** Explicit inverse of the image-to-screen affine transform. */
export function getInverseSceneTransform(transform: SceneTransform) {
  const rect = transform.transformedImageRect;
  return {
    scaleX: 1 / rect.width,
    scaleY: 1 / rect.height,
    translateX: -rect.left / rect.width,
    translateY: -rect.top / rect.height,
  };
}

export function imageNormalizedToScreen(transform: SceneTransform, point: NormalizedPoint): ScreenPoint {
  const rect = transform.transformedImageRect;
  return { x: rect.left + point.x * rect.width, y: rect.top + point.y * rect.height };
}

export function screenToImageNormalized(
  transform: SceneTransform,
  point: ScreenPoint,
  options: { clamp?: boolean } = {},
): NormalizedPoint | null {
  const inverse = getInverseSceneTransform(transform);
  const mapped = {
    x: point.x * inverse.scaleX + inverse.translateX,
    y: point.y * inverse.scaleY + inverse.translateY,
  };
  if (!isNormalizedPointInsideImage(mapped)) {
    return options.clamp ? { x: clamp01(mapped.x), y: clamp01(mapped.y) } : null;
  }
  return mapped;
}

export function imagePixelsToScreen(transform: SceneTransform, point: ImagePixelPoint): ScreenPoint {
  return imageNormalizedToScreen(transform, {
    x: point.x / transform.intrinsicWidth,
    y: point.y / transform.intrinsicHeight,
  });
}

export function screenToImagePixels(
  transform: SceneTransform,
  point: ScreenPoint,
  options: { clamp?: boolean } = {},
): ImagePixelPoint | null {
  const normalized = screenToImageNormalized(transform, point, options);
  return normalized ? { x: normalized.x * transform.intrinsicWidth, y: normalized.y * transform.intrinsicHeight } : null;
}

export function isPointInsideImage(transform: SceneTransform, point: ScreenPoint) {
  const rect = transform.transformedImageRect;
  return point.x >= rect.left - EPSILON && point.x <= rect.right + EPSILON && point.y >= rect.top - EPSILON && point.y <= rect.bottom + EPSILON;
}

export function pointerCoordinates(transform: SceneTransform, screen: ScreenPoint, clamp = false): PointerCoordinates | null {
  const imageNormalized = screenToImageNormalized(transform, screen, { clamp });
  if (!imageNormalized) return null;
  return {
    screen,
    viewport: { x: screen.x - transform.viewportRect.left, y: screen.y - transform.viewportRect.top },
    imageNormalized,
    imagePixels: { x: imageNormalized.x * transform.intrinsicWidth, y: imageNormalized.y * transform.intrinsicHeight },
    insideImage: isPointInsideImage(transform, screen),
    displayedImageRect: transform.displayedImageRect,
    transformedImageRect: transform.transformedImageRect,
  };
}

/** Mirrors the browser transform in intrinsic SVG coordinates: fit is handled by viewBox. */
export function getSceneSvgTransform(intrinsicWidth: number, intrinsicHeight: number, viewport: SceneViewport) {
  assertPositiveDimension(intrinsicWidth, "intrinsicWidth");
  assertPositiveDimension(intrinsicHeight, "intrinsicHeight");
  const centerX = intrinsicWidth / 2;
  const centerY = intrinsicHeight / 2;
  return `translate(${centerX + viewport.pan_x * intrinsicWidth} ${centerY + viewport.pan_y * intrinsicHeight}) scale(${viewport.zoom}) translate(${-centerX} ${-centerY})`;
}

function isNormalizedPointInsideImage(point: NormalizedPoint) {
  return point.x >= -EPSILON && point.x <= 1 + EPSILON && point.y >= -EPSILON && point.y <= 1 + EPSILON;
}

function assertPositiveRect(rect: EditorViewportRect) {
  if (![rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) {
    throw new RangeError("container rectangle must be finite and non-empty");
  }
}

function assertPositiveDimension(value: number, name: string) {
  if (!Number.isFinite(value) || value <= 0) throw new RangeError(`${name} must be a positive finite number`);
}

function clamp01(value: number) { return Math.max(0, Math.min(1, value)); }
