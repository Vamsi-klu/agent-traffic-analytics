"""The image's health check (the Dockerfile's HEALTHCHECK): how long Docker waits for `agentcake status`.

    python3 -I -m unittest discover -s tests -p test_image_health_check.py -v      (from the AgentCake folder)

Docker counts a check that runs longer than its --timeout as failed, and three failures in a row show the container
unhealthy. The timeout is at least Docker's own default, so a check whose Python starts slowly, on a server with one
slow or shared CPU, still counts; and it is longer than the time `agentcake status` itself waits for /api/health
(health_timeout_s), so a server that does not answer fails the check within that wait. What the check runs is
test_server_docs.py's. Docker is not needed: the Dockerfile is read the way Docker reads it (deploy_files.py).
"""
import os
import re
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import config  # noqa: E402  (needs the path above)
from deploy_files import final_stage, instruction_values  # noqa: E402

DOCKER_DEFAULT_TIMEOUT_S = 30  # Docker's default HEALTHCHECK --timeout (the Dockerfile reference)
OPTION = re.compile(r"--([\w-]+)=(\S+)")
DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")  # a Docker duration: 30s, 1m30s, 500ms
DURATION_UNIT_S = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


def duration_s(text):
    """A Docker duration (30s, 1m30s, 500ms) in seconds."""
    parts = DURATION_PART.findall(text)
    if "".join(number + unit for number, unit in parts) != text:
        raise ValueError(f"not a Docker duration: {text!r}")
    return sum(float(number) * DURATION_UNIT_S[unit] for number, unit in parts)


def timeout_s():
    """The HEALTHCHECK's --timeout in seconds; Docker's default when it names none."""
    _, stage = final_stage()
    options = dict(OPTION.findall(instruction_values(stage, "HEALTHCHECK")[-1].partition("CMD")[0]))
    return duration_s(options.get("timeout", f"{DOCKER_DEFAULT_TIMEOUT_S}s"))


class HealthCheckTimeout(unittest.TestCase):
    def test_docker_waits_at_least_its_default_for_the_check(self):
        """On a server with one CPU, starting the check's Python took seconds while the monthly update converted the
        city database, longer than the 5 s the image allowed: a working server showed as unhealthy."""
        self.assertGreaterEqual(timeout_s(), DOCKER_DEFAULT_TIMEOUT_S)

    def test_a_server_that_does_not_answer_fails_within_the_wait_of_status_itself(self):
        self.assertLess(config.DEFAULTS["health_timeout_s"], timeout_s())


if __name__ == "__main__":
    unittest.main()
