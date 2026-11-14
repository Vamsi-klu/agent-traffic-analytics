"""The predicate language the environment rules are written in (S3.3): agentcake/detect/predicate.py.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Three-valued: a key that was not recorded makes a test unknown, a recorded null is a known "nothing"; the combinators
keep unknown apart from false, and malformed predicates are refused.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake.detect.predicate import PredicateError, check, validate  # noqa: E402


class PredicateTest(unittest.TestCase):
    def state(self, node, data):
        return check(node, data).state

    def test_an_absent_key_is_unknown_and_a_recorded_null_is_known(self):
        self.assertIsNone(self.state({"path": "env.userAgent", "regex": "Headless"}, {}))
        self.assertIs(self.state({"path": "env.uaData.brands", "nonempty": True}, {"env": {"uaData": None}}), False)
        self.assertIs(self.state({"path": "env.uaData", "exists": True}, {"env": {"uaData": None}}), False)
        self.assertIs(self.state({"path": "env.uaData", "exists": True}, {}), False)

    def test_true_and_one_are_different_values(self):
        self.assertIs(self.state({"path": "x", "eq": True}, {"x": 1}), False)
        self.assertIs(self.state({"path": "x", "eq": 0}, {"x": False}), False)
        self.assertIs(self.state({"path": "x", "in": [1, 2]}, {"x": True}), False)

    def test_combinators_follow_three_valued_logic(self):
        known_true, known_false, unknown = {"path": "a", "eq": 1}, {"path": "a", "eq": 2}, {"path": "b", "eq": 1}
        data = {"a": 1}
        self.assertIs(self.state({"all": [known_true, unknown]}, data), None)
        self.assertIs(self.state({"all": [known_false, unknown]}, data), False)
        self.assertIs(self.state({"any": [known_true, unknown]}, data), True)
        self.assertIs(self.state({"any": [known_false, unknown]}, data), None)
        self.assertIs(self.state({"not": unknown}, data), None)
        self.assertIs(self.state({"not": known_false}, data), True)

    def test_first_lets_the_first_recorded_reader_decide(self):
        env_false, botd_true = {"path": "env.webdriver", "eq": True}, {"path": "botd.webdriver", "eq": True}
        both = {"env": {"webdriver": False}, "botd": {"webdriver": True}}
        self.assertIs(self.state({"first": [env_false, botd_true]}, both), False)
        self.assertIs(self.state({"first": [env_false, botd_true]}, {"botd": {"webdriver": True}}), True)
        self.assertIsNone(self.state({"first": [env_false, botd_true]}, {}))

    def test_at_least_counts_unknowns_as_possible(self):
        node = {"at_least": 2, "of": [{"path": "a", "eq": 1}, {"path": "b", "eq": 1}, {"path": "c", "eq": 1}]}
        self.assertIs(self.state(node, {"a": 1, "b": 1, "c": 0}), True)
        self.assertIsNone(self.state(node, {"a": 1, "b": 0}))
        self.assertIs(self.state(node, {"a": 1, "b": 0, "c": 0}), False)

    def test_some_reads_list_items_and_shows_the_matching_records(self):
        node = {"some": "items", "where": {"path": "tag", "eq": "DIV"}}
        self.assertEqual(check(node, {"items": [{"tag": "P"}, {"tag": "DIV"}]}).witness, [{"tag": "DIV"}])
        self.assertIs(self.state(node, {"items": []}), False)
        self.assertIs(self.state(node, {"items": None}), False)
        self.assertIsNone(self.state(node, {}))
        strings = {"some": "values", "where": {"regex": "HeadlessChrome/[0-9.]+"}}
        self.assertEqual(check(strings, {"values": ["x HeadlessChrome/149.0 y"]}).witness, ["HeadlessChrome/149.0"])

    def test_number_and_divide_by_transforms(self):
        major = {"path": "ua", "number": "Chrome/([0-9]+)", "gte": 139}
        self.assertIs(self.state(major, {"ua": "Chrome/141.0"}), True)
        self.assertIs(self.state(major, {"ua": "Firefox/140.0"}), False)
        ratio = {"path": "n", "divide_by": "d", "gt": 1.5}
        self.assertIs(self.state(ratio, {"n": 6, "d": 2}), True)
        self.assertIs(self.state(ratio, {"n": 6, "d": 0}), False)
        self.assertIsNone(self.state(ratio, {"n": 6}))

    def test_a_malformed_predicate_is_refused_with_its_place(self):
        for node in ({"path": "a", "eq": 1, "ne": 2}, {"path": "a", "equals": 1}, {"path": "a", "regex": "("},
                     {"some": "items"}, {"all": []}, {"not": {"path": "a"}}, ["path", "a"]):
            with self.subTest(node=node), self.assertRaises(PredicateError) as caught:
                validate(node, "rule.x")
            self.assertIn("rule.x", str(caught.exception))
        validate({"some": "items", "where": {"all": [{"path": "tag", "eq": "DIV"}, {"not": {"exists": True}}]}}, "ok")


if __name__ == "__main__":
    unittest.main()
