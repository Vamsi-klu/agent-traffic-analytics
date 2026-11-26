"""The verdict step (agentcake.detect.verdict): one conclusion per session from the four layers.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The 16 control sessions of the verdict's design each get the class, Agent row, name, verification, confidence and
reasons of the design table (tests/verdict_cases.py). Then the verdict's conflict table, one rule
per test: exclusion first, a verified signature names the infrastructure but not who acts, hard automation is not
overturned by behaviour, soft evidence needs company, only certain names make a Bot, a missing key is never
impersonation. Last, the lab's 26 recorded agent sessions: the four layers together are right on all of them,
against 16 of 26 for behaviour alone.
"""
import dataclasses, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import verdict_cases as cases  # noqa: E402
from verdict_cases import (AGENT_RUN, CHATGPT_USER, CHROME_LINUX, HUMAN_RUN, MANUS, T0, S, behavior,  # noqa: E402
                           declared, evidence, first_address, forged, hit, run, too_little, verified)
from agentcake.detect import verdict  # noqa: E402

UI_LAYERS = ("name", "verify", "environment", "behavior")
UI_STATES = ("human", "agent", "mixed", "unsure", "bot", "no_hit", "off")
REASON_KEYS = {"id", "layer", "source", "value", "grade", "tone", "text"}


def ids(result):
    return [r["id"] for r in result["reasons"]]


class ControlSessions(unittest.TestCase):
    """16 made-up sessions, each judged as the design table says."""

    def test_sixteen_controls(self):
        self.assertEqual(len(cases.CONTROLS), 16)
        for name, about, make, want in cases.CONTROLS:
            with self.subTest(name, about=about):
                result = verdict.decide(make())
                got = {key: result[key] for key in ("class", "row", "name", "verification", "confidence")}
                self.assertEqual(got, {key: want[key] for key in got})
                for reason_id in want["reasons"]:
                    self.assertIn(reason_id, ids(result))
                self.assertEqual(result.get("impersonating"), want.get("impersonating"))
                self.assertEqual(result["layers"]["behavior"]["state"], want["behavior"])

    def test_every_control_lists_layers_and_reasons_the_interface_reads(self):
        for name, _, make, _ in cases.CONTROLS:
            with self.subTest(name):
                result = verdict.decide(make())
                self.assertEqual(tuple(result["layers"]), UI_LAYERS)
                for layer in result["layers"].values():
                    self.assertIn(layer["state"], UI_STATES)
                for reason in result["reasons"]:
                    self.assertLessEqual(REASON_KEYS, set(reason))
                    self.assertTrue(reason["text"])
                    self.assertNotIn("unknown", reason["text"])


class Exclusion(unittest.TestCase):
    """Rule 0: a prefetch or prerender is not a visit."""

    def test_prefetched_page_drops_its_server_half(self):
        result = verdict.decide(evidence(hits=[hit("env.ext.cross-site-landing")], pages=[{"t": T0, "sp": "prefetch"}],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertNotIn("env.ext.cross-site-landing", ids(result))
        self.assertIn("exclude.prefetch", ids(result))
        self.assertEqual(result["class"], "human")

    def test_prerender_is_read_from_sec_purpose_parameters(self):
        result = verdict.decide(evidence(hits=[hit("env.auto.headless-ua-server")],
                                         pages=[{"t": T0, "sp": "prefetch;prerender"}],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertNotIn("env.auto.headless-ua-server", ids(result))
        self.assertEqual(result["class"], "human")

    def test_page_half_of_a_prefetched_page_still_counts(self):
        result = verdict.decide(evidence(hits=[hit("env.auto.webdriver")], pages=[{"t": T0, "sp": "prefetch"}],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["row"]), ("agent", "automated"))

    def test_page_prerendered_and_never_shown_is_left_out(self):
        pages = [{"t": T0}, {"t": T0 + 5 * S, "prerendered": True, "shown": False}]
        result = verdict.decide(evidence(hits=[hit("env.auto.webdriver", pages=(1,))], pages=pages,
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertNotIn("env.auto.webdriver", ids(result))
        self.assertIn("exclude.never-shown", ids(result))
        self.assertEqual(result["class"], "human")

    def test_no_page_left_is_not_a_visit(self):
        pages = [{"t": T0, "prerendered": True, "shown": False}]
        result = verdict.decide(evidence(hits=[hit("env.auto.webdriver")], pages=pages))
        self.assertEqual(result["class"], "excluded")
        self.assertIn("exclude.all", ids(result))
        self.assertIsNone(result["confidence"])


class Verification(unittest.TestCase):
    """Rule 2: a signature or a published range names the infrastructure; failing it is impersonation, unless the
    check could not be made."""

    def test_missing_or_expired_key_is_self_reported_never_impersonation(self):
        for code in ("key-missing", "key-expired", "expired", "not-yet-valid", "unknown-signer", "claim-only"):
            with self.subTest(code):
                result = verdict.decide(evidence(uas=CHROME_LINUX, signatures={"collector": declared("chatgpt.com",
                                                                                                    code)},
                                                 behavior_result=behavior("agent", AGENT_RUN)))
                self.assertEqual((result["class"], result["name"], result["verification"]),
                                 ("agent", "chatgpt", "self_reported"))
                self.assertIsNone(result.get("impersonating"))

    def test_signature_a_proxy_may_have_changed_could_not_verify(self):
        for component in ('"@path"', '"@target-uri"', '"@scheme"'):
            with self.subTest(component):
                sig = forged("chatgpt.com", covers=f'"@authority" {component} "signature-agent"')
                result = verdict.decide(evidence(uas=CHROME_LINUX, signatures={"collector": sig},
                                                 behavior_result=behavior("agent", AGENT_RUN)))
                self.assertEqual(result["verification"], "unverifiable")
                self.assertIsNone(result.get("impersonating"))
                self.assertIn("verify.signature-proxy", ids(result))

    def test_claimed_and_signing_signer_apart_is_a_reason(self):
        sig = dataclasses.replace(verified("chatgpt.com"), claimed="api.manus.im")
        result = verdict.decide(evidence(uas=CHROME_LINUX, signatures={"collector": sig},
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual(result["name"], "chatgpt")
        self.assertIn("name.signer-mismatch", ids(result))

    def test_agent_ua_verified_by_its_published_range(self):
        result = verdict.decide(evidence(uas=CHATGPT_USER, address=first_address("openai-chatgpt-user"),
                                         behavior_result=too_little()))
        self.assertEqual((result["class"], result["row"], result["name"], result["verification"],
                          result["confidence"]), ("agent", "ai", "chatgpt-user", "verified", "certain"))

    def test_agent_ua_outside_its_range_is_impersonation(self):
        result = verdict.decide(evidence(uas=CHATGPT_USER, behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["name"], result["impersonating"]),
                         ("agent", "automated", None, "chatgpt-user"))

    def test_an_impersonated_name_is_an_agent_in_the_name_layer_whatever_its_list_says(self):
        """A name a check proved false is an automation lying about what it is (rules 1 to 3): the name layer says
        Agent, as the class and the verification layer do, for a bot's name as for an agent's."""
        for ua, impersonated in ((cases.GOOGLEBOT, "googlebot"), (CHATGPT_USER, "chatgpt-user")):
            with self.subTest(impersonated):
                result = verdict.decide(evidence(uas=ua, platform="Linux x86_64",
                                                 behavior_result=behavior("agent", AGENT_RUN)))
                self.assertEqual((result["class"], result["impersonating"]), ("agent", impersonated))
                self.assertEqual(result["layers"]["name"], {"state": "agent", "leans": "agent", "percent": 99})
                self.assertEqual(result["layers"]["verify"]["state"], "agent")

    def test_an_impersonated_bots_name_counts_toward_the_percent_as_an_agents_does(self):
        """In local mode the verification layer is off, so the name layer alone says how sure the impersonation is: a
        bot's name proved false by a signature no list knows the signer of gives the percent an agent's name gets."""
        percents = {}
        for ua, impersonated in ((cases.GOOGLEBOT, "googlebot"), (CHATGPT_USER, "chatgpt-user")):
            result = verdict.decide(evidence(mode="local", uas=ua, signatures={"collector": forged("signer.example")},
                                             behavior_result=behavior("agent", AGENT_RUN)))
            self.assertEqual((result["class"], result["impersonating"]), ("agent", impersonated))
            percents[impersonated] = result["percent"]
        self.assertEqual(percents, {"googlebot": 99, "chatgpt-user": 99})

    def test_agent_range_without_a_name_is_the_operators_infrastructure(self):
        result = verdict.decide(evidence(address=first_address("openai-chatgpt-user"),
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["name"], result["confidence"]),
                         ("agent", "ai", None, "certain"))
        self.assertIn("verify.ip-agent-range", ids(result))

    def test_without_an_address_names_are_self_reported(self):
        result = verdict.decide(evidence(uas=cases.GOOGLEBOT, address=None))
        self.assertEqual((result["class"], result["verification"]), ("bot", "self_reported"))
        self.assertIn("verify.no-address", ids(result))

    def test_local_mode_has_no_verification_layer(self):
        result = verdict.decide(evidence(mode="local", uas=cases.GOOGLEBOT))
        self.assertEqual((result["class"], result["verification"]), ("bot", "self_reported"))
        self.assertEqual(result["layers"]["verify"], {"state": "off", "why": "local", "leans": None, "percent": None})

    def test_reverse_dns_verifies_or_unmasks(self):
        good = verdict.decide(evidence(uas=cases.GOOGLEBOT, rdns={"name": "googlebot", "verified": True}))
        self.assertEqual((good["class"], good["verification"], good["confidence"]), ("bot", "verified", "certain"))
        bad = verdict.decide(evidence(mode="local", uas=cases.GOOGLEBOT, rdns={"name": "googlebot", "verified": False},
                                      behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((bad["class"], bad["row"], bad["impersonating"]), ("agent", "automated", "googlebot"))

    def test_disagreeing_names_name_none(self):
        uas = {"page": [MANUS], "collector": [MANUS], "server": [CHATGPT_USER]}
        result = verdict.decide(evidence(mode="local", uas=uas, behavior_result=behavior("agent", AGENT_RUN)))
        self.assertIsNone(result["name"])
        self.assertIn("name.disagree", ids(result))


class Environment(unittest.TestCase):
    """Rule 4: hard automation is not overturned by behaviour; product and extension traces say an agent is here;
    soft evidence needs company; weak evidence only goes into the reasons."""

    def test_hard_automation_is_never_mixed(self):
        result = verdict.decide(evidence(mode="local", hits=[hit("env.auto.webdriver")],
                                         behavior_result=behavior("agent", AGENT_RUN,
                                                                  run("human", 61, 120, 15, 0.08))))
        self.assertEqual((result["class"], result["row"]), ("agent", "automated"))
        self.assertTrue(all(segment["who"] == "agent" for segment in result["segments"]))

    def test_product_rule_with_a_human_taking_over_is_mixed(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.product.muse")],
                                         behavior_result=behavior("agent", AGENT_RUN,
                                                                  run("human", 61, 120, 15, 0.08))))
        self.assertEqual((result["class"], result["row"], result["name"]), ("mixed", "ai", "muse"))
        self.assertEqual([h["to"] for h in result["handoffs"]], ["human"])

    def test_soft_alone_and_human_behaviour_is_human(self):
        result = verdict.decide(evidence(hits=[hit("env.auto.cdp-runtime-leak")],
                                         behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual(result["class"], "human")
        self.assertIn("env.soft-alone", ids(result))

    def test_soft_alone_and_no_answer_from_behaviour_is_not_sure(self):
        for result_of_behavior in (behavior("unsure", run("unsure", 0, 30, 8, 0.5)), too_little()):
            with self.subTest(result_of_behavior["verdict"]):
                result = verdict.decide(evidence(hits=[hit("env.auto.cdp-runtime-leak")],
                                                 behavior_result=result_of_behavior))
                self.assertEqual((result["class"], result["confidence"]), ("not_sure", "unsure"))

    def test_soft_with_agent_behaviour_is_an_agent(self):
        result = verdict.decide(evidence(hits=[hit("env.auto.cdp-runtime-leak")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["confidence"]), ("agent", "automated", "possible"))

    def test_two_soft_rules_confirm_each_other(self):
        result = verdict.decide(evidence(hits=[hit("env.auto.chrome-object-missing"), hit("env.auto.plugins-empty")],
                                         behavior_result=too_little()))
        self.assertEqual((result["class"], result["row"]), ("agent", "automated"))

    def test_cloud_host_with_agent_behaviour_is_an_unnamed_cloud_browser(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.cloud.linux-swiftshader")],
                                         behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["name"]), ("agent", "ai", None))
        self.assertIn("env.cloud-browser", ids(result))

    def test_session_without_environment_signals_shows_the_layer_off(self):
        case = dict(evidence(behavior_result=behavior("human", HUMAN_RUN)), env=None)
        result = verdict.decide(case)
        self.assertEqual(result["class"], "human")
        self.assertEqual(result["layers"]["environment"], {"state": "off", "why": "not_recorded", "leans": None,
                                                           "percent": None})

    def test_weak_hits_change_nothing(self):
        plain = verdict.decide(evidence(behavior_result=behavior("human", HUMAN_RUN)))
        weak = verdict.decide(evidence(hits=[hit("env.ext.cross-site-landing"), hit("env.ext.background-new-tab")],
                                       behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual({k: weak[k] for k in ("class", "row", "name", "confidence")},
                         {k: plain[k] for k in ("class", "row", "name", "confidence")})


class NamesAndBots(unittest.TestCase):
    """Rules 1 and 3: a Bot only by a listed name that is not impersonated; agents keep their names."""

    def test_declared_agent_is_named_and_self_reported(self):
        result = verdict.decide(evidence(uas=MANUS, platform="Linux x86_64", behavior_result=too_little()))
        self.assertEqual((result["class"], result["row"], result["name"], result["verification"],
                          result["confidence"]), ("agent", "ai", "manus", "self_reported", "likely"))

    def test_product_rule_names_before_a_declared_name_and_says_so(self):
        result = verdict.decide(evidence(uas=MANUS, hits=[hit("env.product.muse")], behavior_result=too_little()))
        self.assertEqual((result["name"], result["verification"]), ("muse", None))
        self.assertIn("name.outranked", ids(result))

    def test_named_agent_with_human_run_is_mixed(self):
        result = verdict.decide(evidence(uas=MANUS, behavior_result=behavior("human", HUMAN_RUN)))
        self.assertEqual((result["class"], result["name"]), ("mixed", "manus"))

    def test_bot_skips_the_behaviour_model(self):
        needed, why = verdict.needs_behavior(evidence(uas=cases.UPTIMEROBOT))
        self.assertEqual((needed, why), (False, "bot"))
        self.assertEqual(verdict.needs_behavior(evidence())[0], True)

    def test_judge_never_calls_the_model_for_a_bot(self):
        calls = []
        result = verdict.judge(evidence(uas=cases.UPTIMEROBOT), raw=[], model=lambda *a, **k: calls.append(a))
        self.assertEqual((result["class"], calls), ("bot", []))


class Behaviour(unittest.TestCase):
    """Rule 5: hand-offs, short runs, behaviour alone, assistive tools."""

    def test_human_and_agent_both_long_enough_is_mixed_without_other_evidence(self):
        result = verdict.decide(evidence(behavior_result=behavior("agent", AGENT_RUN,
                                                                  run("human", 61, 120, 15, 0.08))))
        self.assertEqual((result["class"], result["row"], result["confidence"]), ("mixed", "ai", "possible"))
        self.assertIn("behavior.handoff", ids(result))

    def test_short_human_run_is_not_a_hand_off(self):
        # cic-03 of the lab: Claude in Chrome typing, 12 "human" actions in 0.66 s
        short = {"who": "human", "start": T0 + 61 * S, "end": T0 + 61 * S + 660, "n": 12, "p": 0.2}
        result = verdict.decide(evidence(behavior_result=behavior("agent", AGENT_RUN, short)))
        self.assertEqual((result["class"], result["row"]), ("agent", "ai"))
        self.assertIn("behavior.short-run", ids(result))
        self.assertIn("behavior.local-agent", ids(result))
        self.assertEqual(result["shares"]["agent"], 1.0)

    def test_behaviour_alone_names_no_one(self):
        result = verdict.decide(evidence(behavior_result=behavior("agent", AGENT_RUN)))
        self.assertEqual((result["class"], result["row"], result["name"], result["confidence"]),
                         ("agent", "ai", None, "possible"))

    def test_an_indicator_no_list_names_does_not_leave_the_agent_to_behaviour_alone(self):
        """Comet's indicator on the page (a mark the lists name no product for) says its agent was working: the agent
        stays unnamed, and the reasons give the indicator's span, not the line that only behaviour points to an agent
        and that the page has no agent trace (attribute.py's local_agent reason)."""
        span = {"marker": "comet.overlay", "from": T0 + S, "to": T0 + 30 * S}
        marked = behavior("agent", run("agent", 1, 30, 9, 0.97))
        marked["timeline"]["marks"] = [span]
        result = verdict.decide(dict(evidence(mode="local", behavior_result=marked), marks=[span]))
        self.assertEqual((result["class"], result["row"], result["name"], result["category"]),
                         ("agent", "ai", None, "local_agent"))
        self.assertIn("behavior.indicator", ids(result))
        self.assertNotIn("behavior.local-agent", ids(result))

    def test_behaviour_unsure_is_not_sure_and_too_few_actions_too_little_data(self):
        self.assertEqual(verdict.decide(evidence(behavior_result=behavior("unsure", run("unsure", 0, 9, 4, 0.5)))
                                        )["class"], "not_sure")
        result = verdict.decide(evidence(behavior_result=too_little(n_actions=2)))
        self.assertEqual((result["class"], result["layers"]["behavior"]["why"]), ("too_little_data", "few_actions"))
        self.assertIn("behavior.too-little-data", ids(result))

    def test_a_confirmed_agent_part_of_three_clicks_or_inputs_beside_a_long_human_run_is_human_and_agent(self):
        # however fast: the model confirmed the agent's part, and its run holds verdict.json mixed.min_actions of its
        # own clicks or inputs, which the page's title and Share of actions count
        result = verdict.decide(evidence(behavior_result=behavior("agent", run("human", 0, 30, 6, 0.1),
                                                                  run("agent", 31, 32, 3, 0.9))))
        self.assertEqual(result["class"], "mixed")

    def test_an_agent_part_without_three_clicks_or_inputs_beside_a_long_human_run_leaves_a_human(self):
        """11/24: a person scrolled and hovered the browser beside their editor, and the model's agent part held no
        click or input: Human + agent with an agent share of 0%. Its scrolling and moving alone, or two clicks, never
        make the agent's side; the model's verdict stays in the reasons, with the agent run too short to count."""
        for agent in (run("agent", 31, 300, 6, 0.9, acts=0), run("agent", 31, 300, 6, 0.9, acts=2)):
            with self.subTest(acts=agent["acts"]):
                result = verdict.decide(evidence(behavior_result=behavior("agent", run("human", 0, 30, 6, 0.1),
                                                                          agent)))
                self.assertEqual((result["class"], result["handoffs"]), ("human", []))
                self.assertIn("behavior.agent", ids(result))
                short = next(r for r in result["reasons"] if r["id"] == "behavior.short-run")
                self.assertIn(f"included {agent['acts']} actions", short["detail"])
                self.assertEqual(result["layers"]["behavior"]["state"], "agent")  # the model's own conclusion

    def test_automation_with_the_models_agent_verdict_beside_a_human_looking_run_is_agent_in_every_part(self):
        automation = [hit("env.auto.webdriver"), hit("env.auto.cdp-runtime-leak"), hit("env.auto.chromium-only-brand")]
        result = verdict.decide(evidence(mode="local", hits=automation,
                                         behavior_result=behavior("agent", HUMAN_RUN, run("agent", 61, 120, 15, 0.9))))
        self.assertEqual((result["class"], result["handoffs"]), ("agent", []))
        self.assertEqual(result["layers"]["behavior"]["state"], "agent")  # no hand-off: no Human + agent layer
        self.assertNotIn("behavior.overruled", ids(result))  # the model judged an agent, not the session human

    def test_an_agent_run_the_model_did_not_confirm_leaves_a_human(self):
        result = verdict.decide(evidence(behavior_result=behavior("human", AGENT_RUN, run("human", 61, 120, 15, 0.08))))
        self.assertEqual(result["class"], "human")  # an agent part needs the model's two kinds

    def test_agent_evidence_of_one_kind_is_not_sure_and_says_which_kind(self):
        result_of_behavior = dict(behavior("unsure", run("unsure", 0, 9, 4, 0.5)), basis=[],
                                  evidence={"one_kind": "approach"})
        result = verdict.decide(evidence(behavior_result=result_of_behavior))
        self.assertEqual(result["class"], "not_sure")
        (said,) = [r for r in result["reasons"] if r["id"] == "behavior.one-kind"]
        self.assertEqual((said["facts"], said["text"]), ({"kind": "approach"}, "The behavior model can't identify an "
                                                         "agent from one kind of agent-like behavior alone."))
        self.assertEqual(said["detail"], "The behavior model detected agent-like behavior only in pointer movement "
                                         "toward clicks. For this session, the model needs two or more independent kinds of "
                                         "agent-like behavior to identify an agent.")
        self.assertNotIn("behavior.unsure", ids(result))

    def test_segments_and_shares_follow_the_class(self):
        result = verdict.decide(evidence(behavior_result=behavior("agent", AGENT_RUN,
                                                                  run("human", 61, 120, 15, 0.08))))
        self.assertEqual([(s["who"], s["model_who"]) for s in result["segments"]],
                         [("agent", "agent"), ("human", "human")])
        self.assertAlmostEqual(result["shares"]["human"], 15 / 35)


class Candidates(unittest.TestCase):
    """Every name a layer found is kept for the labels table (attribute.py ranks them)."""

    def test_candidates_carry_layer_method_and_certainty(self):
        result = verdict.decide(evidence(uas=CHROME_LINUX, hits=[hit("env.product.muse")],
                                         signatures={"collector": verified("chatgpt.com")},
                                         behavior_result=behavior("agent", AGENT_RUN)))
        found = {(c["name"], c["layer"], c["method"], c["certainty"]) for c in result["candidates"]}
        self.assertIn(("chatgpt", "verify", "signature", "certain"), found)
        self.assertIn(("muse", "environment", "product-rule", "likely"), found)
        self.assertEqual(result["name"], "chatgpt")


if __name__ == "__main__":
    unittest.main()
