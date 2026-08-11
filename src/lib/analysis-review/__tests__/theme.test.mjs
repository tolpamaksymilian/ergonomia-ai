import assert from "node:assert/strict";
import test from "node:test";

import { normalizeTheme, oppositeTheme, persistTheme, readStoredTheme, THEME_STORAGE_KEY, themeBootstrapScript } from "../../theme.ts";

test("light is the default theme", () => {
  assert.equal(normalizeTheme(undefined), "light");
  assert.equal(readStoredTheme({ getItem: () => null }), "light");
});

test("dark theme is read and theme selection is persisted", () => {
  assert.equal(readStoredTheme({ getItem: () => "dark" }), "dark");
  const values = new Map();
  persistTheme({ setItem: (key, value) => values.set(key, value) }, "dark");
  assert.equal(values.get(THEME_STORAGE_KEY), "dark");
});

test("theme toggle is reversible", () => {
  assert.equal(oppositeTheme("light"), "dark");
  assert.equal(oppositeTheme("dark"), "light");
});

test("bootstrap defaults to light without following system preference", () => {
  const script = themeBootstrapScript();
  assert.match(script, /localStorage\.getItem/);
  assert.doesNotMatch(script, /matchMedia|prefers-color-scheme/);
});
