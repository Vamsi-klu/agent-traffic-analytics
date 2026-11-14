"""A small JSON Schema validator for the /api contract in web/src/data/schema/, standard library only.

The Python twin of web/scripts/json-schema.mjs: the same keywords, the same rules, the same "path: problem" lines, so
the Python tests check Agent Cake's answers exactly as `npm run check:ui` checks the samples. Keywords: type (one name
or a list), enum, const, properties, required, additionalProperties (false or a schema), items, minItems, maxItems,
minimum, maximum, minLength, pattern, $ref ("#/$defs/X" or "<file>#/$defs/X"), $defs. Annotations ($schema, $id,
title, description) are ignored. As in JSON Schema, a number keyword only applies to numbers and a string keyword only
to strings. Equality (enum, const) is JavaScript's ===: true is not 1. check_schema() fails a schema that uses any
other keyword, which keeps the two validators equal.

    load_schemas(folder) -> {file name: schema}
    check_schema(file, schemas) -> problems with the schema itself
    validate(value, schema, file, schemas) -> where value breaks the schema ([] when it fits)
    problems(value, name, schemas) -> validate() against <name>.schema.json
"""
import json
import math
import os
import re

ANNOTATIONS = ("$schema", "$id", "title", "description")
RULES = ("type", "enum", "const", "properties", "required", "additionalProperties", "items", "minItems", "maxItems",
         "minimum", "maximum", "minLength", "pattern", "$ref", "$defs")
KEYWORDS = frozenset(ANNOTATIONS + RULES)
SCHEMA_SUFFIX = ".schema.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(ROOT, "web", "src", "data", "schema")


def load_schemas(folder=SCHEMA_DIR):
    """Every *.schema.json in a folder, by file name."""
    out = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(SCHEMA_SUFFIX):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                out[name] = json.load(f)
    return out


def check_schema(file, schemas):
    """Problems with a schema itself: unknown keywords, objects left open by mistake, $refs that point nowhere."""
    found = []

    def walk(node, at):
        if not isinstance(node, dict):
            found.append(f"{file} {at}: not a schema")
            return
        found.extend(f'{file} {at}: unknown keyword "{key}"' for key in node if key not in KEYWORDS)
        if node.get("properties") and "additionalProperties" not in node:
            found.append(f"{file} {at}: an object with properties must say additionalProperties")
        found.extend(f'{file} {at}: required "{key}" is not in properties' for key in node.get("required", ())
                     if key not in (node.get("properties") or {}))
        if "$ref" in node:
            if _resolve(node["$ref"], file, schemas) is None:
                found.append(f'{file} {at}: $ref "{node["$ref"]}" points nowhere')
            if any(key != "$ref" and key in RULES for key in node):
                found.append(f"{file} {at}: $ref must stand alone")
        for name, sub in (node.get("properties") or {}).items():
            walk(sub, f"{at}.properties.{name}")
        for name, sub in (node.get("$defs") or {}).items():
            walk(sub, f"{at}.$defs.{name}")
        if node.get("items"):
            walk(node["items"], f"{at}.items")
        if isinstance(node.get("additionalProperties"), dict):
            walk(node["additionalProperties"], f"{at}.additionalProperties")

    walk(schemas[file], "#")
    return found


def problems(value, name, schemas=None):
    """Where value breaks <name>.schema.json, e.g. problems(answer, "overview")."""
    schemas = schemas or load_schemas()
    file = name + SCHEMA_SUFFIX
    return validate(value, schemas[file], file, schemas)


def validate(value, schema, file, schemas, at="$"):
    """Where value breaks schema (from file), as "path: problem" lines; empty when it fits."""
    if "$ref" in schema:
        target = _resolve(schema["$ref"], file, schemas)
        if target is None:
            return [f'{at}: $ref "{schema["$ref"]}" points nowhere']
        node, target_file = target
        return validate(value, node, target_file, schemas, at)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(name in TYPES and TYPES[name](value) for name in types):
            return [f"{at}: {_show(value)} is not {' or '.join(types)}"]
    if "enum" in schema and not any(_same(value, choice) for choice in schema["enum"]):
        return [f"{at}: {_show(value)} is not one of {_show(schema['enum'])}"]
    if "const" in schema and not _same(value, schema["const"]):
        return [f"{at}: {_show(value)} is not {_show(schema['const'])}"]
    found = []
    if _is_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"{at}: {_show(value)} is below {_show(schema['minimum'])}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"{at}: {_show(value)} is above {_show(schema['maximum'])}")
    if isinstance(value, str):
        if "minLength" in schema and _js_length(value) < schema["minLength"]:
            found.append(f"{at}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            found.append(f"{at}: does not match {schema['pattern']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append(f"{at}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append(f"{at}: more than {schema['maxItems']} items")
        if schema.get("items"):
            for index, item in enumerate(value):
                found.extend(validate(item, schema["items"], file, schemas, f"{at}[{index}]"))
    if isinstance(value, dict):
        found.extend(f'{at}: "{key}" is missing' for key in schema.get("required", ()) if key not in value)
        extra = schema.get("additionalProperties")
        for key, item in value.items():
            sub = (schema.get("properties") or {}).get(key)
            if sub is not None:
                found.extend(validate(item, sub, file, schemas, f"{at}.{key}"))
            elif extra is False:
                found.append(f'{at}: "{key}" is not in the contract')
            elif isinstance(extra, dict):
                found.extend(validate(item, extra, file, schemas, f"{at}.{key}"))
    return found


def _resolve(ref, file, schemas):
    """(the schema a $ref names, the file it lives in), or None; a relative ref stays in its file."""
    target, _, pointer = ref.partition("#")
    in_file = target or file
    node = schemas.get(in_file)
    for part in (p for p in pointer.split("/") if p):
        node = node.get(part) if isinstance(node, dict) else None
    return (node, in_file) if node is not None else None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_integer(value):
    """JavaScript's Number.isInteger: 3 and 3.0 are integers, true is not."""
    return _is_number(value) and float(value).is_integer()


TYPES = {
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
    "integer": _is_integer,
    "number": _is_number,
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _same(a, b):
    """JavaScript's === for JSON values: a boolean only equals a boolean, a number any equal number."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if _is_number(a) or _is_number(b):
        return _is_number(a) and _is_number(b) and a == b
    return type(a) is type(b) and a == b


def _js_length(text):
    """String length as JavaScript counts it: UTF-16 code units (a character outside the BMP counts twice)."""
    return len(text.encode("utf-16-le")) // 2


def _show(value):
    return json.dumps(value, ensure_ascii=False)
