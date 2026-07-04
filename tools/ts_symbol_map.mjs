// Deterministic TypeScript/TSX symbol extractor for the Allocio code map.
//
// Parses frontend/src/**/*.ts and *.tsx with the TypeScript compiler API and
// prints a JSON array of per-file structural entries to stdout. It never writes
// files; tools/code_map.py owns persistence.
//
// Usage:
//   node tools/ts_symbol_map.mjs [--root <dir>]
//
// --root defaults to the repository root (the parent of tools/). Emitted paths
// are repo-relative to that root so the same output shape works when parsing a
// materialized git tree in a temp directory.

import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");

const ts = loadTypeScript();

main();

function main() {
  const root = parseRoot();
  const files = collectSourceFiles(root);
  const entries = files.map((absPath) => describeFile(absPath, root));
  process.stdout.write(JSON.stringify(entries, null, 2) + "\n");
}

function parseRoot() {
  const args = process.argv.slice(2);
  const rootFlag = args.indexOf("--root");
  if (rootFlag !== -1) {
    const value = args[rootFlag + 1];
    if (!value) {
      fail("--root requires a directory argument");
    }
    return path.resolve(value);
  }
  return repoRoot;
}

function loadTypeScript() {
  const require = createRequire(path.join(repoRoot, "frontend", "package.json"));
  try {
    return require("typescript");
  } catch {
    fail("Run: cd frontend && npm install");
  }
}

function collectSourceFiles(root) {
  const srcDir = path.join(root, "frontend", "src");
  const found = [];
  walk(srcDir, found);
  found.sort();
  return found;
}

function walk(dir, found) {
  let dirents;
  try {
    dirents = readdirSync(dir, { withFileTypes: true });
  } catch {
    return; // No frontend/src under this root; emit an empty frontend area.
  }
  for (const dirent of dirents) {
    const full = path.join(dir, dirent.name);
    if (dirent.isDirectory()) {
      walk(full, found);
    } else if (isSourceFile(dirent.name)) {
      found.push(full);
    }
  }
}

function isSourceFile(name) {
  if (name.endsWith(".d.ts")) return false;
  return name.endsWith(".ts") || name.endsWith(".tsx");
}

function describeFile(absPath, root) {
  const relPath = path.relative(root, absPath).split(path.sep).join("/");
  const text = readFileSync(absPath, "utf8");
  const scriptKind = absPath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(relPath, text, ts.ScriptTarget.Latest, true, scriptKind);

  const diagnostics = source.parseDiagnostics ?? [];
  if (diagnostics.length > 0) {
    const first = diagnostics[0];
    const message = ts.flattenDiagnosticMessageText(first.messageText, "\n");
    fail(`TypeScript parse error in ${relPath}: ${message}`);
  }

  const printer = ts.createPrinter({ removeComments: true });
  const context = { source, printer, root };

  const imports = [];
  const exports = new Set();
  const functions = [];
  const classes = [];
  const components = [];

  for (const statement of source.statements) {
    collectImports(statement, imports);
    collectExports(statement, exports);
    collectTopLevelFunction(statement, context, functions, components);
    collectClass(statement, context, classes, components);
    collectVariableComponents(statement, context, components);
  }

  return {
    path: relPath,
    language: "typescript",
    imports: unique(imports),
    exports: [...exports].sort(),
    functions: sortByName(functions),
    classes: sortByName(classes),
    components: sortByName(components),
  };
}

function collectImports(statement, imports) {
  if (ts.isImportDeclaration(statement) && ts.isStringLiteral(statement.moduleSpecifier)) {
    imports.push(statement.moduleSpecifier.text);
    return;
  }
  if (
    ts.isExportDeclaration(statement) &&
    statement.moduleSpecifier &&
    ts.isStringLiteral(statement.moduleSpecifier)
  ) {
    imports.push(statement.moduleSpecifier.text);
  }
}

function collectExports(statement, exports) {
  if (hasExportModifier(statement)) {
    for (const name of declaredNames(statement)) {
      exports.add(name);
    }
    if (hasDefaultModifier(statement)) {
      exports.add("default");
    }
  }
  if (ts.isExportDeclaration(statement) && statement.exportClause && ts.isNamedExports(statement.exportClause)) {
    for (const element of statement.exportClause.elements) {
      exports.add(element.name.text);
    }
  }
  if (ts.isExportAssignment(statement)) {
    exports.add("default");
  }
}

function collectTopLevelFunction(statement, context, functions, components) {
  if (!ts.isFunctionDeclaration(statement) || !statement.name) {
    return;
  }
  const name = statement.name.text;
  const symbol = describeSymbol(name, statement, context);
  functions.push(symbol);
  if (isPascalCase(name)) {
    components.push({ ...symbol, kind: "function" });
  }
}

function collectClass(statement, context, classes, components) {
  if (!ts.isClassDeclaration(statement) || !statement.name) {
    return;
  }
  const name = statement.name.text;
  const methods = [];
  for (const member of statement.members) {
    if (ts.isMethodDeclaration(member) && member.name && ts.isIdentifier(member.name)) {
      methods.push(describeSymbol(member.name.text, member, context));
    }
  }
  const symbol = describeSymbol(name, statement, context);
  classes.push({ ...symbol, methods: sortByName(methods) });
  if (isPascalCase(name) && extendsReactComponent(statement)) {
    components.push({ ...symbol, kind: "class" });
  }
}

function collectVariableComponents(statement, context, components) {
  if (!ts.isVariableStatement(statement)) {
    return;
  }
  for (const declaration of statement.declarationList.declarations) {
    if (!ts.isIdentifier(declaration.name) || !declaration.initializer) {
      continue;
    }
    const name = declaration.name.text;
    if (!isPascalCase(name)) {
      continue;
    }
    if (
      ts.isArrowFunction(declaration.initializer) ||
      ts.isFunctionExpression(declaration.initializer)
    ) {
      const symbol = describeSymbol(name, declaration, context);
      components.push({ ...symbol, kind: "variable" });
    }
  }
}

function describeSymbol(name, node, context) {
  const start = context.source.getLineAndCharacterOfPosition(node.getStart(context.source));
  const end = context.source.getLineAndCharacterOfPosition(node.getEnd());
  return {
    name,
    line_start: start.line + 1,
    line_end: end.line + 1,
    hash: hashNode(node, context),
  };
}

function hashNode(node, context) {
  const printed = context.printer.printNode(ts.EmitHint.Unspecified, node, context.source);
  const normalized = printed.replace(/\s+/g, " ").trim();
  return createHash("sha256").update(normalized).digest("hex").slice(0, 16);
}

function extendsReactComponent(classNode) {
  if (!classNode.heritageClauses) {
    return false;
  }
  for (const clause of classNode.heritageClauses) {
    if (clause.token !== ts.SyntaxKind.ExtendsKeyword) {
      continue;
    }
    for (const type of clause.types) {
      const text = type.expression.getText(classNode.getSourceFile());
      if (text === "Component" || text === "React.Component" || text === "React.PureComponent" || text === "PureComponent") {
        return true;
      }
    }
  }
  return false;
}

function declaredNames(statement) {
  if (ts.isFunctionDeclaration(statement) || ts.isClassDeclaration(statement)) {
    return statement.name ? [statement.name.text] : [];
  }
  if (ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement) || ts.isEnumDeclaration(statement)) {
    return [statement.name.text];
  }
  if (ts.isVariableStatement(statement)) {
    return statement.declarationList.declarations
      .filter((declaration) => ts.isIdentifier(declaration.name))
      .map((declaration) => declaration.name.text);
  }
  return [];
}

function hasExportModifier(statement) {
  return hasModifier(statement, ts.SyntaxKind.ExportKeyword);
}

function hasDefaultModifier(statement) {
  return hasModifier(statement, ts.SyntaxKind.DefaultKeyword);
}

function hasModifier(statement, kind) {
  const modifiers = ts.canHaveModifiers(statement) ? ts.getModifiers(statement) : undefined;
  return Boolean(modifiers && modifiers.some((modifier) => modifier.kind === kind));
}

function isPascalCase(name) {
  return /^[A-Z][A-Za-z0-9]*$/.test(name);
}

function unique(values) {
  return [...new Set(values)].sort();
}

function sortByName(symbols) {
  return [...symbols].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}

function fail(message) {
  process.stderr.write(message + "\n");
  process.exit(1);
}
