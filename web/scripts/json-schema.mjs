// A small JSON Schema validator for the /api contract in src/data/schema/. It knows only the keywords below, so
// the Python half can check cake's answers with the same few rules and the standard library; checkKeywords() fails a
// schema that uses anything else, which keeps the two validators equal.
//
// Keywords: type (one name or a list), enum, const, properties, required, additionalProperties (false or a schema),
// items, minItems, maxItems, minimum, maximum, minLength, pattern, $ref ("#/$defs/X" or "<file>#/$defs/X"), $defs.
// Annotations ($schema, $id, title, description) are ignored. As in JSON Schema, a number keyword only applies to
// numbers and a string keyword only to strings.
import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"

const ANNOTATIONS = ["$schema", "$id", "title", "description"]
const RULES = ["type", "enum", "const", "properties", "required", "additionalProperties", "items", "minItems", "maxItems",
  "minimum", "maximum", "minLength", "pattern", "$ref", "$defs"]
export const KEYWORDS = new Set([...ANNOTATIONS, ...RULES])

/** Every *.schema.json in a folder, by file name. */
export function loadSchemas(dir) {
  return new Map(readdirSync(dir).filter((f) => f.endsWith(".schema.json")).map((f) => [f, JSON.parse(readFileSync(path.join(dir, f), "utf8"))]))
}

/** Problems with a schema itself: unknown keywords, objects left open by mistake, $refs that point nowhere. */
export function checkSchema(file, schemas) {
  const problems = []
  const walk = (node, at) => {
    if (typeof node !== "object" || node === null || Array.isArray(node)) { problems.push(`${file} ${at}: not a schema`); return }
    for (const key of Object.keys(node)) if (!KEYWORDS.has(key)) problems.push(`${file} ${at}: unknown keyword "${key}"`)
    if (node.properties && node.additionalProperties === undefined) problems.push(`${file} ${at}: an object with properties must say additionalProperties`)
    for (const key of node.required ?? []) if (!node.properties?.[key]) problems.push(`${file} ${at}: required "${key}" is not in properties`)
    if (node.$ref && !resolve(node.$ref, file, schemas)) problems.push(`${file} ${at}: $ref "${node.$ref}" points nowhere`)
    if (node.$ref && Object.keys(node).some((k) => k !== "$ref" && RULES.includes(k))) problems.push(`${file} ${at}: $ref must stand alone`)
    for (const [name, sub] of Object.entries(node.properties ?? {})) walk(sub, `${at}.properties.${name}`)
    for (const [name, sub] of Object.entries(node.$defs ?? {})) walk(sub, `${at}.$defs.${name}`)
    if (node.items) walk(node.items, `${at}.items`)
    if (typeof node.additionalProperties === "object") walk(node.additionalProperties, `${at}.additionalProperties`)
  }
  walk(schemas.get(file), "#")
  return problems
}

/** The schema a $ref names, and the file it lives in (relative refs stay in their file). */
function resolve(ref, file, schemas) {
  const [target, pointer = ""] = ref.split("#")
  const inFile = target || file
  let node = schemas.get(inFile)
  for (const part of pointer.split("/").filter(Boolean)) node = node?.[part]
  return node ? { node, file: inFile } : null
}

const TYPES = {
  null: (v) => v === null,
  boolean: (v) => typeof v === "boolean",
  integer: (v) => Number.isInteger(v),
  number: (v) => typeof v === "number" && Number.isFinite(v),
  string: (v) => typeof v === "string",
  array: (v) => Array.isArray(v),
  object: (v) => typeof v === "object" && v !== null && !Array.isArray(v),
}
const show = (v) => JSON.stringify(v)

/** Where `value` breaks `schema` (from `file`), as "path: problem" lines; empty when it fits. */
export function validate(value, schema, file, schemas, at = "$") {
  if (schema.$ref) {
    const target = resolve(schema.$ref, file, schemas)
    return target ? validate(value, target.node, target.file, schemas, at) : [`${at}: $ref "${schema.$ref}" points nowhere`]
  }
  const types = schema.type === undefined ? null : [schema.type].flat()
  if (types && !types.some((t) => TYPES[t]?.(value))) return [`${at}: ${show(value)} is not ${types.join(" or ")}`]
  if (schema.enum && !schema.enum.some((e) => e === value)) return [`${at}: ${show(value)} is not one of ${show(schema.enum)}`]
  if ("const" in schema && schema.const !== value) return [`${at}: ${show(value)} is not ${show(schema.const)}`]
  const problems = []
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) problems.push(`${at}: ${value} is below ${schema.minimum}`)
    if (schema.maximum !== undefined && value > schema.maximum) problems.push(`${at}: ${value} is above ${schema.maximum}`)
  }
  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) problems.push(`${at}: shorter than ${schema.minLength}`)
    if (schema.pattern !== undefined && !new RegExp(schema.pattern, "u").test(value)) problems.push(`${at}: does not match ${schema.pattern}`)
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) problems.push(`${at}: fewer than ${schema.minItems} items`)
    if (schema.maxItems !== undefined && value.length > schema.maxItems) problems.push(`${at}: more than ${schema.maxItems} items`)
    if (schema.items) value.forEach((item, i) => problems.push(...validate(item, schema.items, file, schemas, `${at}[${i}]`)))
  }
  if (TYPES.object(value)) {
    for (const key of schema.required ?? []) if (!(key in value)) problems.push(`${at}: "${key}" is missing`)
    for (const [key, item] of Object.entries(value)) {
      const sub = schema.properties?.[key]
      if (sub) problems.push(...validate(item, sub, file, schemas, `${at}.${key}`))
      else if (schema.additionalProperties === false) problems.push(`${at}: "${key}" is not in the contract`)
      else if (typeof schema.additionalProperties === "object") problems.push(...validate(item, schema.additionalProperties, file, schemas, `${at}.${key}`))
    }
  }
  return problems
}
