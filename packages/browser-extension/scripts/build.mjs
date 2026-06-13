// Build script: bundles the MV3 extension with esbuild and assembles a loadable
// `dist/`. No framework — just esbuild + a few static copies + generated icons.
import { build, context } from "esbuild";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generateIcons } from "./gen-icons.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const srcDir = resolve(root, "src");
const distDir = resolve(root, "dist");
const watch = process.argv.includes("--watch");
const prod = !watch && process.env.NODE_ENV !== "development";

const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));

/** esbuild entry points -> output files in dist/ */
const entryPoints = {
  background: resolve(srcDir, "background/index.ts"),
  content: resolve(srcDir, "content/index.ts"),
  popup: resolve(srcDir, "popup/popup.ts"),
  options: resolve(srcDir, "options/options.ts"),
};

const shared = {
  bundle: true,
  format: "iife",
  target: ["chrome111"],
  platform: "browser",
  legalComments: "none",
  sourcemap: watch ? "inline" : false,
  minify: prod,
  define: { "process.env.NODE_ENV": JSON.stringify(prod ? "production" : "development") },
  logLevel: "info",
};

function copyStatic() {
  mkdirSync(distDir, { recursive: true });

  // manifest.json — inject version from package.json so they never drift.
  const manifest = JSON.parse(readFileSync(resolve(srcDir, "manifest.json"), "utf8"));
  manifest.version = pkg.version;
  writeFileSync(resolve(distDir, "manifest.json"), JSON.stringify(manifest, null, 2));

  // HTML for popup + options
  for (const page of ["popup", "options"]) {
    cpSync(resolve(srcDir, `${page}/${page}.html`), resolve(distDir, `${page}.html`));
    cpSync(resolve(srcDir, `${page}/${page}.css`), resolve(distDir, `${page}.css`));
  }

  generateIcons(resolve(distDir, "icons"));
}

async function run() {
  if (!watch && existsSync(distDir)) rmSync(distDir, { recursive: true, force: true });
  copyStatic();

  const buildOpts = {
    ...shared,
    entryPoints,
    entryNames: "[name]",
    outdir: distDir,
  };

  if (watch) {
    const ctx = await context(buildOpts);
    await ctx.watch();
    // re-copy static on a light interval; esbuild watch only covers JS graph.
    console.log("watching for changes… (re-run build to refresh static assets)");
  } else {
    await build(buildOpts);
    console.log(`built isitme-browser-extension v${pkg.version} -> dist/`);
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
