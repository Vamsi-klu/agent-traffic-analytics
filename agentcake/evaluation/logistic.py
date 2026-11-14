"""The lab's logistic regression on segment features: one of the models `agentcake eval` prints beside cake's own.

    vector(features, names, log1p) -> [x]    each feature (log1p where listed, 0 when missing) and a missing flag
    fit(rows, labels, settings) -> model     balanced class weights, L2, plain gradient descent
    predict(model, x) -> P(agent)

Ported from our own code with the same arithmetic in the same order, so it gives the lab's numbers:
the behaviour lab's labcore.py (vec, fit_lr, pred_lr; 2026-11-11). It is only
measured here, never used to judge a session (D6). Settings: agentcake/data/eval.json "segments.logistic".
"""
import functools
import math
import operator
import statistics

CLASSES = 2  # protocol: agent and human; balanced weights give each class total / (classes x its size)


def vector(features, names, log1p):
    """The lab's vec(): per feature its value (log1p for counts and times) and 1 when it had no data."""
    x = []
    for name in names:
        value = features.get(name)
        missing = value is None
        value = 0.0 if missing else float(value)
        if name in log1p:
            value = math.log1p(max(0.0, value))
        x.append(value)
        x.append(1.0 if missing else 0.0)
    return x


def fit(rows, labels, settings):
    """A model from vectors and labels (1 agent, 0 human), each class weighted to half of the total."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    return _fit(rows, labels, settings, w_pos=len(labels) / (CLASSES * n_pos), w_neg=len(labels) / (CLASSES * n_neg))


def predict(model, x):
    z = [(x[j] - model["mu"][j]) / model["sd"][j] for j in range(len(x))]
    s = model["b"] + sum(wj * zj for wj, zj in zip(model["w"], z))
    limit = model["limit"]
    return 1 / (1 + math.exp(-max(-limit, min(limit, s))))


def _fit(rows, labels, settings, w_pos, w_neg):
    """labcore.fit_lr with its sums in the same order, so the result is the same to the last bit.

    The lab added e * z[j] into gw[j] one sample after another and summed each logit with sum(); here each gradient
    is the same sequence of additions (functools.reduce from 0.0, in sample order) over a column, and each logit the
    same sum() over the same products, which runs the loops in C instead of Python.
    """
    l2, iterations, rate, limit = (settings["l2"], settings["iterations"], settings["learning_rate"],
                                   settings["logit_limit"])
    n, d = len(rows), len(rows[0])
    mu = [statistics.mean(c) for c in zip(*rows)]
    sd = [statistics.pstdev(c) or 1.0 for c in zip(*rows)]
    z_rows = [[(x[j] - mu[j]) / sd[j] for j in range(d)] for x in rows]
    columns = [list(column) for column in zip(*z_rows)]
    w, b = [0.0] * d, 0.0
    weights = [w_pos if label else w_neg for label in labels]
    total = sum(weights)
    for _ in range(iterations):
        errors = [(1 / (1 + math.exp(-max(-limit, min(limit, b + sum(map(operator.mul, w, z)))))) - label) * weight
                  for z, label, weight in zip(z_rows, labels, weights)]
        gb = functools.reduce(operator.add, errors, 0.0)
        gw = [functools.reduce(operator.add, map(operator.mul, errors, column), 0.0) for column in columns]
        w = [wj - rate * (gj / total + l2 * wj / n) for wj, gj in zip(w, gw)]
        b -= rate * gb / total
    return {"w": w, "b": b, "mu": mu, "sd": sd, "limit": limit}
