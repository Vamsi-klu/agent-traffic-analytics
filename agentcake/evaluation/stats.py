"""The arithmetic of the industry-style scoreboard (plan step S3.7, decision D36): exact binomial bounds and precision
at a prevalence.

    clopper_pearson(k, n, confidence) -> (low, high)    exact (Clopper–Pearson) interval of k successes in n trials
    precision_at(recall, false_positive_rate, prevalence) -> share of the sessions called agent that are agents

A rate measured on a few sessions says little on its own: 0 false positives in 11 humans still allows a true rate of
28%. The scoreboard prints every rate with its exact interval (the two-sided interval, so its upper end is the 97.5%
one-sided bound for a 95% confidence), as Akamai's research prototype and AgentShield report theirs. Precision at a
prevalence is Bayes' rule on recall and the false positive rate: when agents are 1% of the visits, a false positive
rate of 5% makes most sessions called agent humans whatever the recall (research note 21, section 3).

Standard library only: the binomial tail is summed in log space (math.lgamma) and the bound found by bisection, which
needs no inverse beta function.
"""
import math

BISECTION_STEPS = 60  # protocol: halves the bracket 60 times, below double precision for a share in [0, 1]
SIDES = 2  # protocol: a two-sided interval leaves half of what it does not cover on each side
MIDDLE = 0.5  # protocol: bisection tests the middle of the bracket


def clopper_pearson(k, n, confidence):
    """(low, high): the exact interval of the true rate after k successes in n trials; (None, None) when n is 0."""
    if not n:
        return None, None
    if not 0 <= k <= n:
        raise ValueError(f"k must lie in 0..n, got k={k}, n={n}")
    tail = (1 - confidence) / SIDES
    # low: the smallest rate at which k or more successes are at least `tail` likely; high: the largest rate at which
    # k or fewer still are. Both tails are monotone in the rate, so each bound is where a test turns true.
    low = 0.0 if k == 0 else _boundary(lambda p: 1 - binomial_cdf(k - 1, n, p) >= tail, 0.0, k / n)
    high = 1.0 if k == n else _boundary(lambda p: binomial_cdf(k, n, p) < tail, k / n, 1.0)
    return low, high


def binomial_cdf(k, n, p):
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    log_n = math.lgamma(n + 1)
    return min(1.0, sum(math.exp(log_n - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_p + (n - i) * log_q)
                        for i in range(k + 1)))


def precision_at(recall, false_positive_rate, prevalence):
    """Share of the sessions called agent that are agents, when agents are `prevalence` of all sessions; None when
    nothing is called agent (both rates 0) or a rate is unknown."""
    if recall is None or false_positive_rate is None:
        return None
    caught = recall * prevalence
    wrong = false_positive_rate * (1 - prevalence)
    return caught / (caught + wrong) if caught + wrong > 0 else None


def _boundary(rises, low, high):
    """The rate in [low, high] where rises(p) turns from false to true (rises must be monotone there)."""
    for _ in range(BISECTION_STEPS):
        middle = low + (high - low) * MIDDLE
        if rises(middle):
            high = middle
        else:
            low = middle
    return low + (high - low) * MIDDLE
