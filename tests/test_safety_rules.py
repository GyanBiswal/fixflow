"""Unit tests for the deterministic safety rules."""
import pytest

from app.safety_rules import check_safety, merge_urgency

EMERGENCY_CASES = [
    ("I can smell gas in the kitchen", "gas_leak"),
    ("There is smoke coming from the socket", "fire_or_smoke"),
    ("Exposed wires hanging near the bathroom", "electrical_hazard"),
    ("I got an electric shock from the switch", "electrical_hazard"),
    ("Water is leaking near the switchboard", "water_near_electrics"),
    ("Someone is stuck in the lift", "person_trapped_or_injured"),
    ("Part of the ceiling collapsed", "structural_collapse"),
    ("The carbon monoxide alarm is beeping", "carbon_monoxide"),
]

HIGH_CASES = [
    ("A pipe burst and water is flooding the corridor", "flooding_or_burst_pipe"),
    ("The fire alarm in my corridor is not working", "fire_safety_equipment"),
    ("The smoke alarm battery needs replacing", "fire_safety_equipment"),
    ("Sewage is overflowing in the bathroom", "sewage_overflow"),
]

NORMAL_CASES = [
    "The tap in the kitchen is dripping slowly",
    "Please clean the stairwell",
    "Light bulb in the hallway needs replacing",
    "My AC is not cooling the room",
    "The kitchen sink is leaking",
]


@pytest.mark.parametrize("text, rule", EMERGENCY_CASES)
def test_emergency_cases_are_safety_critical(text, rule):
    result = check_safety(text)
    assert result.is_safety_critical is True
    assert result.min_urgency == "emergency"
    assert rule in result.triggered_rules


@pytest.mark.parametrize("text, rule", HIGH_CASES)
def test_high_cases_are_urgent_but_not_safety_critical(text, rule):
    result = check_safety(text)
    assert result.is_safety_critical is False
    assert result.min_urgency == "high"
    assert rule in result.triggered_rules


@pytest.mark.parametrize("text", NORMAL_CASES)
def test_normal_cases_trigger_nothing(text):
    result = check_safety(text)
    assert result.is_safety_critical is False
    assert result.min_urgency is None
    assert result.triggered_rules == []


def test_llm_cannot_downgrade_an_emergency():
    safety = check_safety("I can smell gas in the kitchen")
    assert merge_urgency("low", safety) == "emergency"


def test_llm_urgency_is_kept_when_no_rule_fires():
    safety = check_safety("The tap in the kitchen is dripping slowly")
    assert merge_urgency("high", safety) == "high"
    assert merge_urgency("low", safety) == "low"


def test_missing_or_invalid_llm_urgency_defaults_to_medium():
    safety = check_safety("Please clean the stairwell")
    assert merge_urgency(None, safety) == "medium"
    assert merge_urgency("nonsense", safety) == "medium"


def test_gas_leak_includes_immediate_actions():
    result = check_safety("There is a gas leak in the kitchen")
    assert result.immediate_actions
    assert "emergency" in " ".join(result.immediate_actions).lower()
