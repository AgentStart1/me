import { build } from "esbuild";
import { readFile, writeFile, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
const template = await readFile(new URL("panel.html",import.meta.url),"utf8");
for(const [plugin,mode,title] of [["android-emulator-profile","emulator","Android Emulators"],["android-device-lock","locks","Device Leases"]]) {
  const result = await build({entryPoints:[fileURLToPath(new URL("panel.mjs",import.meta.url))],bundle:true,write:false,format:"esm",target:"es2022",minify:true,define:{PANEL_MODE:JSON.stringify(mode)}});
  const target = new URL(`../../plugins/${plugin}/`,import.meta.url);
  await writeFile(new URL("templates/status-panel.html",target),template.replaceAll("PANEL_TITLE",title).replace("/* PANEL_SCRIPT */",()=>result.outputFiles[0].text.replaceAll("</script","<\\/script")));
  await copyFile(new URL("android_probe.py",import.meta.url),new URL("scripts/android_probe.py",target));
}
