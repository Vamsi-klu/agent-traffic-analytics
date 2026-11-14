"""The words of a verdict (agentcake.detect.verdict_text, reasons.json, judging.en.json).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Every reason the code can give is in reasons.json with a known layer, grade and tone; judging.en.json says what every
class means (the dashboard's "how cake judges", reads the same sentences) and labels every row, verification
and layer (how sure a verdict is, the page says only as its percent); a reason's moments read on the replay's clock
when its start is given; none of the interface text calls a visitor a person, people or a user.
"""
import json, os, re, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import hit  # noqa: E402
from agentcake import datafiles  # noqa: E402
from agentcake.detect import env_rules, markers, reasons_past, verdict, verdict_text, webbotauth  # noqa: E402
from tools.reasons_past import FACTS_COMMIT  # noqa: E402

DETECT = os.path.join(ROOT, "agentcake", "detect")
CODE_FILES = ("verdict.py", "verdict_identity.py", "verdict_marks.py", "attribute.py", "crawler.py", "behavior.py",
              "weak.py")
REASON_ID = re.compile(r"""["']((?:exclude|name|verify|env|behavior|crawler|weak)\.[a-z-]+)["']""")  # not rule ids
LAYERS = {"exclusion", "name", "verify", "environment", "behavior", "weak"}
TONES = {"agent", "human", "none"}
T_EPOCH = 1_794_608_433_697  # a replay's start, epoch ms on the events' clock
FORBIDDEN = re.compile(r"\b(?:person|people)\b|\busers?\b(?!-agent)", re.IGNORECASE)  # the User-Agent header is a name


def texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, inner in value.items():
            if not key.startswith("$"):
                yield from texts(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from texts(inner)


def history_before_facts():
    """Whether this checkout's git history holds FACTS_COMMIT, the commit the wordings of reasons_past.json are
    collected up to: a release folder has no history, and the published repository's begins at a release."""
    if not os.path.exists(os.path.join(ROOT, ".git")):
        return False
    found = subprocess.run(["git", "cat-file", "-e", FACTS_COMMIT + "^{commit}"], cwd=ROOT, capture_output=True)
    return found.returncode == 0


class ReasonsFile(unittest.TestCase):
    def test_every_reason_has_a_known_layer_grade_and_tone(self):
        grades = set(env_rules.load_rules().legend["grades"])
        for reason_id, entry in verdict_text.reasons()["reasons"].items():
            with self.subTest(reason_id):
                self.assertIn(entry["layer"], LAYERS)
                self.assertIn(entry["grade"], grades)
                self.assertIn(entry["tone"], TONES)
                self.assertTrue(entry["text"])

    def test_every_reason_the_code_gives_is_in_the_file(self):
        known = set(verdict_text.reasons()["reasons"])
        used = set()
        for name in CODE_FILES:
            with open(os.path.join(DETECT, name), encoding="utf-8") as f:
                used |= set(REASON_ID.findall(f.read()))
        self.assertTrue(used)
        self.assertEqual(used - known, set())

    def test_facts_fill_the_text_and_unknown_facts_say_so(self):
        filled = verdict_text.reason("behavior.too-little-data", "page", n=2, min=3)
        self.assertEqual((filled["text"], filled["detail"]), ("The behavior model doesn't judge the session because there are too few actions.", "The session has 2 actions; the model needs 3."))
        self.assertEqual((filled["layer"], filled["source"], filled["tone"]), ("behavior", "page", "none"))
        self.assertIn("unknown", verdict_text.reason("behavior.too-little-data")["detail"])

    def test_environment_hit_is_worded_by_its_rule(self):
        worded = verdict_text.env_reason(hit("env.auto.webdriver", pages=(0, 2)))
        self.assertEqual(worded["text"], env_rules.load_rules().rule("env.auto.webdriver").title)
        self.assertEqual((worded["layer"], worded["source"], worded["strength"], worded["pages"], worded["tone"]),
                         ("environment", "page", "hard", [0, 2], "agent"))
        self.assertEqual(verdict_text.env_reason(hit("env.ext.viewport-shrink"))["tone"], "none")


def _fill(template, **facts):
    return template.format(**facts)


class KeptFacts(unittest.TestCase):
    """A reason keeps its facts and is worded each time it is shown, so changed words reach old sessions."""

    def test_a_reason_keeps_its_facts_as_json_and_is_worded_from_them(self):
        kept = verdict_text.reason("behavior.too-little-data", "page", 2, n=2, min=3)
        self.assertEqual(kept["facts"], {"n": 2, "min": 3})
        self.assertEqual(json.loads(json.dumps(kept)), kept)
        self.assertEqual(verdict_text.words(dict(kept, text="Old words.", detail=None)), (kept["text"], kept["detail"]))

    def test_facts_that_name_a_phrase_are_worded_with_it(self):
        table = verdict_text.reasons()
        ua = verdict_text.reason("name.ua", "page", "x", half=["page", "server"], name="Claude-User", kind_label="AI agent")
        self.assertIn(f"{table['halves']['page']} and {table['halves']['server']}", ua["detail"])
        crawl = verdict_text.reason("crawler.like", "collector", [], signals=["fixed_interval_visits"], pages=3, every_s=300)
        self.assertIn(verdict_text.duration(300), crawl["detail"])
        mark = verdict_text.reason("behavior.indicator", "page", [], marker="comet.overlay", from_ms=42000, to_ms=None)
        self.assertIn(markers.words("comet.overlay", 42000, None), mark["text"])
        result = webbotauth.Verification("verified", "verified", signer="chatgpt.com", keyid="k1")
        signed = verdict_text.reason("verify.signature", "collector", "chatgpt.com", signature=webbotauth.as_facts(result))
        self.assertIn(webbotauth.explain(result), signed["text"])
        tool = verdict_text.reason("name.tool", None, "x", name="Playwright", method="automation-trace")
        self.assertIn(table["methods"]["automation-trace"], tool["detail"])

    def test_a_hand_off_says_its_moment_on_the_replays_clock(self):
        """The moment the reason keeps in its value, from the replay's start when it is given (the timeline's mark
        is at value minus that start too), else from the visit's start its facts keep."""
        replay_start, handoff_at = T_EPOCH, T_EPOCH + 47_927
        kept = verdict_text.reason("behavior.handoff", "page", handoff_at, to="human", at=39, **{"from": "agent"})
        self.assertEqual(verdict_text.words(kept, replay_start)[0], "The human took over from the agent at 0:47.")
        self.assertEqual(verdict_text.words(kept)[0], "The human took over from the agent at 0:39.")

    def test_an_indicators_span_says_its_moments_on_the_replays_clock(self):
        kept = verdict_text.reason("behavior.indicator", "page", [T_EPOCH + 16_500, T_EPOCH + 33_200],
                                   marker="comet.overlay", from_ms=8_000, to_ms=24_700)
        self.assertEqual(verdict_text.words(kept, T_EPOCH)[0], verdict_text.words(
            dict(kept, facts=dict(kept["facts"], from_ms=16_500, to_ms=33_200)))[0])
        self.assertIn(markers.words("comet.overlay", 16_500, 33_200), verdict_text.words(kept, T_EPOCH)[0])
        still_on = verdict_text.reason("behavior.indicator", "page", [T_EPOCH + 16_500, None], marker="comet.overlay",
                                       from_ms=8_000, to_ms=None)
        self.assertIn(markers.words("comet.overlay", 16_500, None), verdict_text.words(still_on, T_EPOCH)[0])

    def test_an_indicators_tail_says_until_when_on_the_replays_clock(self):
        kept = verdict_text.reason("behavior.indicator-tail", "page", [T_EPOCH + 16_500, T_EPOCH + 33_200,
                                                                      T_EPOCH + 28_300],
                                   marker="claude-chrome.working", from_ms=8_000, to_ms=24_700, until_ms=19_800)
        on_replay, from_visit = verdict_text.words(kept, T_EPOCH)[0], verdict_text.words(kept)[0]
        self.assertIn(markers.words("claude-chrome.working", 16_500, 33_200), on_replay)
        self.assertIn(" 0:28 ", on_replay)
        self.assertIn(markers.words("claude-chrome.working", 8_000, 24_700), from_visit)
        self.assertIn(" 0:19 ", from_visit)

    def test_an_environment_hit_is_worded_by_its_rule_whatever_it_was_kept_with(self):
        rule = env_rules.load_rules().rule("env.auto.webdriver")
        self.assertEqual(verdict_text.words({"id": rule.id, "text": "old title"}), (rule.title, rule.detail))

    def test_a_reason_kept_with_its_text_only_gets_its_facts_back_from_it(self):
        past = reasons_past._past()
        old = _fill(past["reasons"]["behavior.too-little-data"][0], n=2, min=3)
        today = verdict_text.reason("behavior.too-little-data", "page", 2, n=2, min=3)
        self.assertEqual(verdict_text.words({"id": "behavior.too-little-data", "text": old}), (today["text"], today["detail"]))
        span = _fill(past["spans"]["closed"][0], **{"from": "00:42", "to": "01:15"})
        sentence = _fill(past["reasons"]["behavior.indicator"][0], words=_fill(past["markers"]["comet.overlay"][0], span=span))
        self.assertEqual(reasons_past.facts({"id": "behavior.indicator", "text": sentence}),
                         {"marker": "comet.overlay", "from_ms": 42000, "to_ms": 75000})
        halves = f"{past['halves']['page'][0]} and {past['halves']['server'][0]}"
        ua = _fill(past["reasons"]["name.ua"][0], half=halves, name="Claude-User", kind_label="AI agent")
        self.assertEqual(reasons_past.facts({"id": "name.ua", "text": ua})["half"], ["page", "server"])

    @unittest.skipUnless(history_before_facts(), "needs the git history from before verdicts kept their facts (a release "
                         "folder has none, and the published repository's begins at a release)")
    def test_every_wording_from_before_facts_were_kept_can_be_read_back(self):
        """A build without the facts commit judged sessions with its own wordings (a branch merged later too)."""
        done = subprocess.run([sys.executable, "-I", "-B", os.path.join(ROOT, "tools", "reasons_past.py"), "--check"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_text_no_wording_makes_keeps_its_words(self):
        self.assertEqual(verdict_text.words({"id": "behavior.agent", "text": "Unknown words."}), ("Unknown words.", None))
        self.assertEqual(verdict_text.words({"id": "no.such-reason", "text": "Kept.", "detail": "d"}), ("Kept.", "d"))
        exclude = verdict_text.reason("exclude.all")
        self.assertEqual(verdict_text.words({"id": "exclude.all", "text": "Old."}), (exclude["text"], exclude["detail"]))


class JudgingFile(unittest.TestCase):
    def test_every_class_level_and_layer_is_worded(self):
        words = verdict_text.judging()
        for key in verdict.JUDGING_KEYS:
            with self.subTest(key):
                self.assertTrue(words["classes"][key]["how"])
        self.assertNotIn("agent_named", words["classes"], "a name is level 3, never a class of its own")
        self.assertTrue(words["named"]["how"])
        self.assertNotIn("confidence", words, "the session page says how sure a verdict is as its percent only")
        self.assertEqual(set(words["verification"]), {"verified", "self_reported", "unverifiable", "impersonation"})
        self.assertEqual(set(words["layers"]), LAYERS)

    def test_the_categories_name_every_value_the_api_gives(self):
        """The verdict (with an Agent session's split) and which agent have a label and a sentence for each value
        data/api.json maps cake's classes to, and Unnamed for an agent no name fits."""
        words, mapped = verdict_text.judging(), datafiles.load("data/api.json")
        self.assertEqual(set(words["verdicts"]), set(mapped["verdicts"].values()))
        self.assertEqual(set(words["turns"]), set(mapped["agent_turns"].values()))
        self.assertNotIn("kinds", words, "there are no kinds of agent: they are reasons now")
        self.assertEqual(set(words["names"]), set(mapped["certainty"].values()) | {"unnamed"})
        self.assertEqual(set(words["evidence"]), set(mapped["evidence"].values()), "thin evidence marks a Human")
        self.assertTrue(words["unsure"]["label"] and words["unsure"]["about"], "a stretch that couldn't tell")
        for level in ("verdicts", "turns", "names", "evidence"):
            for key, entry in words[level].items():
                with self.subTest(level, key=key):
                    self.assertTrue(entry["label"] and entry["about"])
        self.assertTrue(words["title"] and words["lead"], "the dashboard's categories block: the verdicts and the split")

    def test_when_the_model_runs_names_both_settings(self):
        joined = " ".join(verdict_text.judging()["when_model_runs"])
        self.assertIn("{quiet}", joined)
        self.assertIn("{interval}", joined)

    def test_interface_text_never_says_person_people_or_user(self):
        for name in ("reasons.json", "judging.en.json"):
            with open(os.path.join(ROOT, "agentcake", "data", name), encoding="utf-8") as f:
                data = json.load(f)
            for text in texts(data):
                with self.subTest(name, text=text[:60]):
                    self.assertIsNone(FORBIDDEN.search(text))


if __name__ == "__main__":
    unittest.main()
