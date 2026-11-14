"""How well Agent Cake judges sessions with known answers: the parts behind `agentcake eval` (plan step S3.9; GOAL T12).

Nothing here judges or writes a verdict: every module reads data, asks agentcake.detect for its verdict and compares
it with the answer. agentcake/eval.py is the command; the modules here are its parts, one job each.
"""
