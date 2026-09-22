"""Routing must be deterministic and must not launch work the user only asked about."""

import pytest

from osiris_mobile.intent import Route, classify, describe_routes


@pytest.mark.parametrize("text,route", [
    ("run the mux benchmark phase B", Route.ORGANISM),
    ("benchmark the GRN on seeds 70-74", Route.ORGANISM),
    ("start the chat bridge", Route.ORGANISM),
    ("train the sovereign transformer", Route.NCLM),
    ("evolve livlm for 30 generations", Route.LIVLM),
    ("auto advance", Route.LADDER),
    ("auto-advance", Route.LADDER),
    ("write a function to parse the ledger", Route.BRAIN),
    ("refactor this module", Route.BRAIN),
])
def test_execution_routes(text, route):
    assert classify(text).route == route


@pytest.mark.parametrize("text", [
    "explain the mux benchmark",
    "what is PARAMS16?",
    "why did M2c fail",
    "how does the GRN admit genes",
    "describe the sovereign transformer",
    "summarize livlm's fitness function",
])
def test_explaining_a_subsystem_is_a_question_not_a_run(text):
    """The asymmetry that matters: explaining a run costs a sentence, launching one
    the user only asked about costs hours of battery."""
    result = classify(text)
    assert result.route == Route.BRAIN
    assert result.mode == "explain"
    assert not result.heavy


def test_slash_commands_bypass_scoring():
    for cmd, route in [("/power", Route.SYSTEM), ("/status", Route.SYSTEM),
                       ("/organism", Route.ORGANISM), ("/livlm", Route.LIVLM),
                       ("/advance", Route.LADDER), ("/brain", Route.BRAIN)]:
        result = classify(cmd)
        assert result.route == route, cmd
        assert not result.ambiguous


def test_unknown_slash_command_is_system_not_brain():
    assert classify("/nonsense").route == Route.SYSTEM


def test_empty_input_is_inert():
    for text in ("", "   ", "\t\n"):
        result = classify(text)
        assert result.route == Route.SYSTEM
        assert not result.heavy


def test_heavy_requires_execute_mode():
    """A heavy route reached in explain mode must not be gated as heavy -- it is a question."""
    assert classify("run the mux benchmark").heavy
    assert not classify("what does the mux benchmark measure?").heavy


def test_classification_is_pure_and_repeatable():
    text = "benchmark drift with structural hooks on seed 4"
    first = classify(text)
    for _ in range(25):
        again = classify(text)
        assert (again.route, again.mode, again.score) == (first.route, first.mode, first.score)


def test_every_route_is_described():
    table = describe_routes()
    for route in Route.ALL:
        assert route in table


def test_heavy_routes_are_a_subset_of_all_routes():
    assert set(Route.HEAVY).issubset(set(Route.ALL))
    assert Route.BRAIN not in Route.HEAVY
    assert Route.SYSTEM not in Route.HEAVY
