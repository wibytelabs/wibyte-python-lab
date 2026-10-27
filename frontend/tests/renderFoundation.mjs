/** Transpile actual local TSX in memory; React/compiler come from the locked install. */
import { readFile, access } from "node:fs/promises";
import ts from "typescript";
const cache = new Map();
const base = new URL("../src/features/foundation/", import.meta.url);
export async function component(name, replacements = {}) {
  const key = name + JSON.stringify(replacements);
  if (!cache.has(key)) cache.set(key, compile(name, replacements));
  return cache.get(key);
}
async function compile(name, replacements) {
  const file = new URL(name + ".tsx", base);
  const source = await readFile(file, "utf8");
  let output = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  const targets = new Map(Object.entries(replacements));
  const specifiers = [...new Set([...output.matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1]))];
  for (const specifier of specifiers) {
    if (targets.has(specifier)) continue;
    if (!specifier.startsWith(".")) { targets.set(specifier, import.meta.resolve(specifier));continue; }
    const local = new URL(specifier, file);
    const tsx = new URL(local.href + ".tsx");
    let hasTSX = true;
    try { await access(tsx); } catch (error) { if (error.code !== "ENOENT") throw error;hasTSX = false; }
    if (hasTSX) targets.set(specifier, (await component(specifier.replace(/^\.\//, ""))).url);
    else { const typed = new URL(local.href + ".ts");await access(typed);targets.set(specifier, typed.href); }
  }
  output = output.replace(/from\s+["']([^"']+)["']/g, (_match, specifier) => "from " + JSON.stringify(targets.get(specifier)));
  const url = "data:text/javascript;base64," + Buffer.from(output).toString("base64");
  return { view: (await import(url)).default, url };
}
