import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";
const result = await build({ entryPoints: [new URL("panel.mjs", import.meta.url).pathname], bundle: true, write: false, format: "esm", target: "es2022", minify: true });
const html = await readFile(new URL("panel.html", import.meta.url), "utf8");
await writeFile(new URL("../templates/status-panel.html", import.meta.url), html.replace("/* PANEL_SCRIPT */", () => result.outputFiles[0].text.replaceAll("</script", "<\\/script")));
