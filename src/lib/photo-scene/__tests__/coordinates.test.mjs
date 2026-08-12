import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  getContainedImageRect,
  getSceneTransform,
  imageNormalizedToScreen,
  imagePixelsToScreen,
  isPointInsideImage,
  screenToImageNormalized,
  screenToImagePixels,
} from "../coordinates.ts";

const images = [
  [1000, 1000], [1600, 1200], [1200, 1600], [1920, 1080], [1080, 1920],
  [2520, 1080], [2000, 1000], [1000, 2000], [4032, 3024], [3024, 4032],
  [1573, 847], [847, 1573],
];
const normalizedPoints = [
  { x: .05, y: .05 }, { x: .5, y: .5 }, { x: .95, y: .05 },
  { x: .95, y: .95 }, { x: .05, y: .95 },
];

function close(actual, expected, tolerance = 1e-10) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} differs from ${expected}`);
}

test("contained image rect includes portrait and ultrawide letterbox offsets", () => {
  const portrait = getContainedImageRect({ left: 10, top: 20, width: 1200, height: 700 }, 500, 1000);
  close(portrait.width, 350); close(portrait.height, 700); close(portrait.left, 435); close(portrait.top, 20);
  const ultrawide = getContainedImageRect({ left: 10, top: 20, width: 900, height: 700 }, 2100, 900);
  close(ultrawide.width, 900); close(ultrawide.height, 900 / 2100 * 900); close(ultrawide.left, 10);
  close(ultrawide.top, 20 + (700 - ultrawide.height) / 2);
});

for (const [width, height] of images) {
  for (const zoom of [.5, 1, 2, 4]) {
    test(`round trip ${width}x${height}, zoom ${zoom}`, () => {
      const transform = getSceneTransform({ left: 31, top: 47, width: 1200, height: 700 }, width, height, { zoom, pan_x: .13, pan_y: -.09 });
      for (const point of normalizedPoints) {
        const screen = imageNormalizedToScreen(transform, point);
        const roundTrip = screenToImageNormalized(transform, screen);
        assert.ok(roundTrip); close(roundTrip.x, point.x); close(roundTrip.y, point.y);
      }
    });
  }
}

test("resize and panel width changes preserve the normalized image point", () => {
  for (const container of [
    { left: 0, top: 0, width: 1200, height: 700 },
    { left: 240, top: 80, width: 900, height: 700 },
    { left: 80, top: 30, width: 1600, height: 900 },
  ]) {
    const transform = getSceneTransform(container, 847, 1573, { zoom: 2, pan_x: -.12, pan_y: .07 });
    const source = { x: .95, y: .05 };
    const mapped = screenToImageNormalized(transform, imageNormalizedToScreen(transform, source));
    assert.ok(mapped); close(mapped.x, source.x); close(mapped.y, source.y);
  }
});

test("reported top-right offset does not grow away from image center", () => {
  const transform = getSceneTransform({ left: 111, top: 73, width: 1200, height: 700 }, 847, 1573, { zoom: 1.75, pan_x: .08, pan_y: -.12 });
  for (const source of normalizedPoints) {
    const roundTrip = screenToImageNormalized(transform, imageNormalizedToScreen(transform, source));
    assert.ok(roundTrip);
    close(Math.hypot(roundTrip.x - source.x, roundTrip.y - source.y), 0, 1e-10);
  }
});

test("clicks in contain margins are ignored, not clamped to an image edge", () => {
  const transform = getSceneTransform({ left: 0, top: 0, width: 1200, height: 700 }, 500, 1000, { zoom: 1, pan_x: 0, pan_y: 0 });
  assert.equal(isPointInsideImage(transform, { x: 10, y: 350 }), false);
  assert.equal(screenToImageNormalized(transform, { x: 10, y: 350 }), null);
  assert.deepEqual(screenToImageNormalized(transform, { x: 10, y: 350 }, { clamp: true }), { x: 0, y: .5 });
});

test("intrinsic pixel transforms share the same inverse", () => {
  const transform = getSceneTransform({ left: 90, top: 25, width: 980, height: 640 }, 4032, 3024, { zoom: 4, pan_x: -.2, pan_y: .15 });
  const source = { x: 4011, y: 19 };
  const result = screenToImagePixels(transform, imagePixelsToScreen(transform, source));
  assert.ok(result); close(result.x, source.x, 1e-8); close(result.y, source.y, 1e-8);
});

test("screen to image to screen is reversible with fractional browser layout coordinates", () => {
  const transform = getSceneTransform({ left: 17.375, top: 29.625, width: 913.75, height: 641.25 }, 1080, 1920, { zoom: .5, pan_x: .173, pan_y: -.081 });
  const source = imageNormalizedToScreen(transform, { x: .91, y: .13 });
  const normalized = screenToImageNormalized(transform, source); assert.ok(normalized);
  const roundTrip = imageNormalizedToScreen(transform, normalized);
  close(roundTrip.x, source.x); close(roundTrip.y, source.y);
});

test("object, measurement, floor, calibration and human tools use the central coordinate engine", () => {
  const source = readFileSync(new URL("../../../components/photo-scene/photo-scene-editor.tsx", import.meta.url), "utf8");
  assert.match(source, /getSceneTransform/);
  assert.match(source, /getSceneSvgTransform/);
  assert.match(source, /coordinatesFor\(event/);
  assert.doesNotMatch(source, /pointFromSvg/);
  assert.doesNotMatch(source, /\(event\.clientX - rect\.left\) \/ rect\.width/);
  for (const tool of ["ADD_OBJECT", "FLOOR", "REFERENCE", "HUMAN"]) assert.match(source, new RegExp(`"${tool}"`));
});

test("invalid transforms fail instead of inventing coordinates", () => {
  assert.throws(() => getContainedImageRect({ left: 0, top: 0, width: 0, height: 10 }, 100, 100), RangeError);
  assert.throws(() => getSceneTransform({ left: 0, top: 0, width: 10, height: 10 }, 100, 100, { zoom: 0, pan_x: 0, pan_y: 0 }), RangeError);
});
