import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const [packageJson, releaseSource, changelog] = await Promise.all([
  readFile(path.join(root, "package.json"), "utf8").then(JSON.parse),
  readFile(path.join(root, "src/config/release.ts"), "utf8"),
  readFile(path.join(root, "CHANGELOG.md"), "utf8"),
]);
const version = packageJson.version;
const releaseMatch = releaseSource.match(/version:\s*"([^"]+)"/);
const changelogMatch = changelog.match(/^## \[([^\]]+)\]/m);
const actual = { package: version, release: releaseMatch?.[1], changelog: changelogMatch?.[1] };
if (!version || Object.values(actual).some((value) => value !== version)) {
  console.error("RELEASE_VERSION_CONSISTENT=false", actual);
  process.exit(1);
}
console.log(`RELEASE_VERSION_CONSISTENT=true`);
console.log(`RELEASE_VERSION=${version}`);
