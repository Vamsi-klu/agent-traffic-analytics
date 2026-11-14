"""A small three-valued predicate language over JSON signals (S3.3): what the environment rules' `match` is written in.

    check(node, data) -> Outcome(state, witness)     state: True (held), False (did not), None (input not recorded)
    validate(node, where)                           raises PredicateError on a malformed predicate

Grammar:
    {"path": "env.webdriver", "eq": true}       a test on one value; operators: eq ne in regex contains gt gte lt lte
                                                 nonempty exists; before the operator, "number": <regex> takes the
                                                 regex's first group as a number, "divide_by": <path> divides by it
    {"all": [...]} {"any": [...]} {"not": {...}} {"at_least": 2, "of": [...]}
    {"first": [...]}                             the first test whose input was recorded decides (two readers of the
                                                 same fact, e.g. env.js and BotD both reading navigator.webdriver)
    {"some": "dom_add", "where": {...}}          at least one item of a list; inside `where` paths start at the item,
                                                 and a test without "path" tests the item itself
A path is dotted keys. A key that is absent is unknown; a key that is present with null is a known "nothing". So a
signal that was not recorded makes a test unknown, never false: "no data" is never read as "no automation".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

COMBINATORS = ("all", "any", "first", "not", "at_least", "some")
OPERATORS = ("eq", "ne", "in", "regex", "contains", "gt", "gte", "lt", "lte", "nonempty", "exists")
TRANSFORMS = ("number", "divide_by")


class PredicateError(ValueError):
    """A predicate does not follow the grammar."""


class _Missing:
    """A key the signals do not have: that input was not recorded."""

    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


@dataclass(frozen=True)
class Outcome:
    """A predicate's result: state True (held), False (did not) or None (unknown), and what made it hold."""
    state: bool | None
    witness: object = None


_UNKNOWN = Outcome(None)
_NO = Outcome(False)


def resolve(data, path):
    """The value at a dotted path: MISSING when a key is absent, None when the path crosses a recorded null."""
    node = data
    for key in path.split(".") if path else ():
        if node is None:
            return None
        if not isinstance(node, dict) or key not in node:
            return MISSING
        node = node[key]
    return node


def plain(value):
    """A resolved value for output: MISSING becomes None."""
    return None if value is MISSING else value


def _same(value, expected):
    # JSON true and 1 are different facts; Python's True == 1 must not make them equal.
    if isinstance(value, bool) or isinstance(expected, bool):
        return type(value) is type(expected) and value == expected
    return value == expected


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@lru_cache(maxsize=None)
def _regex(pattern):
    return re.compile(pattern)


def _op_regex(value, pattern):
    found = _regex(pattern).search(value) if isinstance(value, str) else None
    return (True, found.group(0)) if found else (False, None)


def _op_contains(value, item):
    if isinstance(value, list):
        return any(_same(x, item) for x in value), item
    return isinstance(value, str) and isinstance(item, str) and item in value, item


def _op_nonempty(value, wanted):
    filled = isinstance(value, (list, dict, str)) and len(value) > 0
    return filled == wanted, value


def _compare(test):
    return lambda value, limit: (_is_number(value) and test(value, limit), value)


_OPS = {
    "eq": lambda value, expected: (_same(value, expected), value),
    "ne": lambda value, expected: (not _same(value, expected), value),
    "in": lambda value, options: (any(_same(value, x) for x in options), value),
    "regex": _op_regex,
    "contains": _op_contains,
    "gt": _compare(lambda a, b: a > b),
    "gte": _compare(lambda a, b: a >= b),
    "lt": _compare(lambda a, b: a < b),
    "lte": _compare(lambda a, b: a <= b),
    "nonempty": _op_nonempty,
}


def _transform(node, value, data):
    """Apply "number" and "divide_by"; returns the new value, or an Outcome when the test is already decided."""
    if "number" in node:
        found = _regex(node["number"]).search(value) if isinstance(value, str) else None
        if not found:
            return _NO
        value = float(found.group(1))
    if "divide_by" in node:
        divisor = resolve(data, node["divide_by"])
        if divisor is MISSING:
            return _UNKNOWN
        if not _is_number(value) or not _is_number(divisor) or divisor == 0:
            return _NO
        value = value / divisor
    return value


def _leaf(node, data):
    value = resolve(data, node.get("path", ""))
    if "exists" in node:
        present = value is not MISSING and value is not None
        return Outcome(present == node["exists"], value if present else None)
    if value is MISSING:
        return _UNKNOWN
    value = _transform(node, value, data)
    if isinstance(value, Outcome):
        return value
    op = next(name for name in _OPS if name in node)
    held, witness = _OPS[op](value, node[op])
    return Outcome(True, witness) if held else _NO


def _all(outcomes):
    if any(o.state is False for o in outcomes):
        return _NO
    if any(o.state is None for o in outcomes):
        return _UNKNOWN
    shown = [o.witness for o in outcomes if o.witness is not None and o.witness is not True]
    return Outcome(True, shown[0] if len(shown) == 1 else (shown or True))


def _any(outcomes):
    for o in outcomes:
        if o.state:
            return o
    return _UNKNOWN if any(o.state is None for o in outcomes) else _NO


def _first(outcomes):
    return next((o for o in outcomes if o.state is not None), _UNKNOWN)


def _at_least(count, outcomes):
    held = [o.witness for o in outcomes if o.state]
    unknown = sum(1 for o in outcomes if o.state is None)
    if len(held) >= count:
        return Outcome(True, held)
    return _UNKNOWN if len(held) + unknown >= count else _NO


def _some(node, data):
    items = resolve(data, node["some"])
    if items is MISSING:
        return _UNKNOWN
    if not isinstance(items, list):
        return _NO
    outcomes = [check(node["where"], item) for item in items]
    # A matching record (a dict) is shown whole; a matching string or number by the part the test matched.
    held = [item if isinstance(item, (dict, list)) else o.witness for item, o in zip(items, outcomes) if o.state]
    if held:
        return Outcome(True, held)
    return _UNKNOWN if any(o.state is None for o in outcomes) else _NO


def check(node, data):
    """Evaluate one predicate against a dict of signals (a page, a session, or a list item)."""
    if "all" in node:
        return _all([check(child, data) for child in node["all"]])
    if "any" in node:
        return _any([check(child, data) for child in node["any"]])
    if "first" in node:
        return _first([check(child, data) for child in node["first"]])
    if "not" in node:
        inner = check(node["not"], data)
        return inner if inner.state is None else Outcome(not inner.state, True if not inner.state else None)
    if "at_least" in node:
        return _at_least(node["at_least"], [check(child, data) for child in node["of"]])
    if "some" in node:
        return _some(node, data)
    return _leaf(node, data)


def validate(node, where):
    """Raise PredicateError, naming `where`, unless `node` follows the grammar (and every regex compiles)."""
    if not isinstance(node, dict):
        raise PredicateError(f"{where}: a predicate must be an object, got {node!r}")
    combinator = [key for key in COMBINATORS if key in node]
    if combinator:
        key = combinator[0]
        allowed = {"some": {"some", "where"}, "at_least": {"at_least", "of"}}.get(key, {key})
        if set(node) != allowed:
            raise PredicateError(f"{where}: {key} takes exactly {sorted(allowed)}, got {sorted(node)}")
        if key == "not":
            validate(node["not"], where + ".not")
        elif key == "some":
            validate(node["where"], where + ".where")
        else:
            children = node["of"] if key == "at_least" else node[key]
            if not isinstance(children, list) or not children:
                raise PredicateError(f"{where}: {key} needs a non-empty list")
            for i, child in enumerate(children):
                validate(child, f"{where}.{key}[{i}]")
        return
    ops = [key for key in OPERATORS if key in node]
    extra = set(node) - set(OPERATORS) - set(TRANSFORMS) - {"path"}
    if len(ops) != 1 or extra:
        raise PredicateError(f"{where}: a test needs exactly one operator of {OPERATORS}, got {sorted(node)}")
    for key in ("regex", "number"):
        if key in node:
            try:
                _regex(node[key])
            except re.error as err:
                raise PredicateError(f"{where}: bad {key} {node[key]!r}: {err}") from err
