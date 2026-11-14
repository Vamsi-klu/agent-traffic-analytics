"""tests/json_schema.py, the Python twin of web/scripts/json-schema.mjs (S5.1).

    python3 -I -m unittest discover -s tests -p test_json_schema.py -v      (from the Agent Cake folder)

The contract's own schemas pass check_schema() and every sample answer in web/src/data/fixtures/ fits its schema here
too, as `npm run check:ui` finds with the JavaScript validator; each keyword refuses what it should, with the same
"path: problem" lines.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json_schema  # noqa: E402

FIXTURES = os.path.join(json_schema.ROOT, "web", "src", "data", "fixtures")
LIBRARY = "library"  # cake's answers on the fixed test library
DEFS = {"Count": {"type": "integer", "minimum": 0}, "Text": {"type": "string", "minLength": 1}}


def samples():
    """(schema name, path under fixtures/, value) of every sample: fixtures/<name>.json, fixtures/<name>/**.json and
    fixtures/library/<name>.json (cake's answers on the fixed test library)."""
    for folder, _, names in sorted(os.walk(FIXTURES)):
        for name in sorted(n for n in names if n.endswith(".json")):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, FIXTURES).replace(os.sep, "/")
            parts = rel.removesuffix(".json").split("/")
            with open(path, encoding="utf-8") as f:
                yield parts[1] if parts[0] == LIBRARY else parts[0], rel, json.load(f)


def check(value, schema, extra=None):
    schemas = {"common.schema.json": {"$defs": DEFS}, "t.schema.json": schema, **(extra or {})}
    return json_schema.validate(value, schema, "t.schema.json", schemas)


class TheContract(unittest.TestCase):
    def test_every_schema_uses_only_the_known_keywords_and_closes_its_objects(self):
        schemas = json_schema.load_schemas()
        self.assertGreater(len(schemas), 1)
        for file in schemas:
            self.assertEqual(json_schema.check_schema(file, schemas), [], file)

    def test_every_sample_answer_fits_its_schema(self):
        schemas = json_schema.load_schemas()
        seen = set()
        for name, rel, value in samples():
            with self.subTest(sample=rel):
                self.assertEqual(json_schema.problems(value, name, schemas), [])
            seen.add(name + json_schema.SCHEMA_SUFFIX)
        self.assertEqual(set(schemas) - seen, {"common.schema.json"}, "every schema has a sample")


class Keywords(unittest.TestCase):
    def test_type_one_name_or_a_list(self):
        self.assertEqual(check("x", {"type": ["string", "null"]}), [])
        self.assertEqual(check(None, {"type": ["string", "null"]}), [])
        self.assertEqual(check(3, {"type": "string"}), ["$: 3 is not string"])

    def test_true_is_not_an_integer_but_three_point_zero_is(self):
        self.assertEqual(check(True, {"type": "integer"}), ["$: true is not integer"])
        self.assertEqual(check(3.0, {"type": "integer"}), [])
        self.assertEqual(check(2.5, {"type": "integer"}), ["$: 2.5 is not integer"])

    def test_enum_and_const_compare_as_javascript_does(self):
        self.assertEqual(check(1, {"enum": [True, "a"]}), ['$: 1 is not one of [true, "a"]'])
        self.assertEqual(check(None, {"enum": ["a", None]}), [])
        self.assertEqual(check(1.0, {"const": 1}), [])
        self.assertEqual(check(False, {"const": 0}), ["$: false is not 0"])

    def test_numbers_strings_and_arrays_have_their_limits(self):
        self.assertEqual(check(-1, {"minimum": 0, "maximum": 100}), ["$: -1 is below 0"])
        self.assertEqual(check(101, {"minimum": 0, "maximum": 100}), ["$: 101 is above 100"])
        self.assertEqual(check("abc", {"minimum": 0}), [], "a number keyword does not apply to a string")
        self.assertEqual(check("", {"minLength": 1}), ["$: shorter than 1"])
        self.assertEqual(check("ab", {"pattern": "^a"}), [])
        self.assertEqual(check("ba", {"pattern": "^a"}), ["$: does not match ^a"])
        self.assertEqual(check([], {"minItems": 1}), ["$: fewer than 1 items"])
        self.assertEqual(check([1, 2], {"maxItems": 1}), ["$: more than 1 items"])
        self.assertEqual(check([1, "x"], {"items": {"type": "integer"}}), ['$[1]: "x" is not integer'])

    def test_a_character_outside_the_bmp_counts_two_as_in_javascript(self):
        self.assertEqual(check("\U0001F370", {"minLength": 2}), [])

    def test_objects_report_missing_and_extra_keys(self):
        schema = {"type": "object", "additionalProperties": False, "required": ["a"], "properties": {"a": {}}}
        self.assertEqual(check({"b": 1}, schema), ['$: "a" is missing', '$: "b" is not in the contract'])
        open_ = {"type": "object", "additionalProperties": {"type": "integer"}, "properties": {}}
        self.assertEqual(check({"n": "x"}, open_), ['$.n: "x" is not integer'])

    def test_refs_inside_a_file_and_across_files(self):
        schema = {"$defs": {"Word": {"type": "string"}},
                  "type": "object", "additionalProperties": False,
                  "properties": {"w": {"$ref": "#/$defs/Word"}, "n": {"$ref": "common.schema.json#/$defs/Count"}}}
        self.assertEqual(check({"w": "x", "n": 2}, schema), [])
        self.assertEqual(check({"w": 1, "n": -2}, schema), ["$.w: 1 is not string", "$.n: -2 is below 0"])
        self.assertEqual(check(1, {"$ref": "#/$defs/Nowhere"}), ['$: $ref "#/$defs/Nowhere" points nowhere'])


class SchemaChecks(unittest.TestCase):
    def problems(self, schema):
        return json_schema.check_schema("t.schema.json", {"t.schema.json": schema, "common.schema.json": {"$defs": DEFS}})

    def test_an_unknown_keyword_fails_so_the_two_validators_stay_equal(self):
        self.assertEqual(self.problems({"type": "string", "format": "date"}),
                         ['t.schema.json #: unknown keyword "format"'])

    def test_objects_must_say_whether_they_are_closed_and_refs_must_lead_somewhere(self):
        self.assertEqual(self.problems({"properties": {"a": {}}, "required": ["a", "b"]}),
                         ["t.schema.json #: an object with properties must say additionalProperties",
                          't.schema.json #: required "b" is not in properties'])
        self.assertEqual(self.problems({"$ref": "common.schema.json#/$defs/Nope", "type": "string"}),
                         ['t.schema.json #: $ref "common.schema.json#/$defs/Nope" points nowhere',
                          "t.schema.json #: $ref must stand alone"])


if __name__ == "__main__":
    unittest.main()
