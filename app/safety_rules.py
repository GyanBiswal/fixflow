"""Deterministic safety rules. No LLM and no database are used here.

The rules scan the complaint text for danger signs. We deliberately accept some
false alarms: it is safer to escalate a harmless complaint than to miss a real danger.
"""
import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.constants import URGENCY_LEVELS


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str  # "emergency" or "high"
    concern: str
    patterns: tuple[str, ...]
    actions: tuple[str, ...] = ()


RULES = (
    Rule(
        name="gas_leak",
        severity="emergency",
        concern="Possible gas leak",
        patterns=(
            r"\bgas\b.{0,25}\b(leak|leaks|leaking|leakage|smell|smells|smelling|odou?r)\b",
            r"\b(smell|smells|smelling|smelt)\b.{0,15}\bgas\b",
            r"\brotten eggs?\b",
            r"\blpg\b.{0,25}\b(leak|leaks|leaking|smell|smells)\b",
        ),
        actions=(
            "Do not use switches, lighters, or open flames.",
            "Open windows if it is safe, then leave the area.",
            "Call your local emergency number (112 in India) or the gas supplier from outside.",
        ),
    ),
    Rule(
        name="fire_or_smoke",
        severity="emergency",
        concern="Possible fire or smoke",
        patterns=(
            r"\bsmoke\b(?!\s+(alarm|alarms|detector|detectors)\b)",
            r"\bon fire\b|\bcaught fire\b|\bcatching fire\b|\bflames?\b",
            r"\bfire\b(?!\s+(alarm|alarms|extinguisher|extinguishers|exit|exits|door|doors|sprinkler|sprinklers|drill|safety|hose|panel)\b)",
            r"\b(burning|burnt)\b.{0,15}\b(smell|odou?r)\b",
            r"\b(smell|smells)\b.{0,15}\b(burning|burnt)\b",
            r"\b(fire|smoke) alarms?\b.{0,20}\b(going off|ringing|beeping|sounding|blaring)\b",
        ),
        actions=(
            "Leave the area immediately and raise the building fire alarm.",
            "Call your local fire or emergency number (112 in India).",
        ),
    ),
    Rule(
        name="electrical_hazard",
        severity="emergency",
        concern="Possible electric shock or exposed wiring",
        patterns=(
            r"\belectric(al)? shocks?\b",
            r"\b(got|get|gets|getting|received|feel|feeling|felt|giving|gives|gave)\b.{0,10}\bshocks?\b",
            r"\bgot shocked\b|\bgetting shocked\b|\bshocked me\b|\belectrocut\w*",
            r"\b(exposed|bare|open|live|hanging|dangling|loose|damaged|frayed|broken)\s+(electric(al)?\s+)?(wire|wires|wiring|cable|cables)\b",
            r"\bsparks?\b|\bsparking\b|\bsparked\b",
            r"\bshort[- ]?circuit\w*",
        ),
        actions=(
            "Do not touch the area or the wires.",
            "Switch off power at the main supply only if it is safe to reach.",
            "Keep people away until an electrician arrives.",
        ),
    ),
    Rule(
        name="water_near_electrics",
        severity="emergency",
        concern="Water near electrical fittings",
        patterns=(
            r"\b(water|wet|leak|leaks|leaking|leakage|dripping|flood|flooded|flooding|seepage)\b.{0,40}\b(socket|sockets|outlet|outlets|switchboard|switch board|switch|switches|fuse|fuse box|mcb|wiring|electrical|electricity|meter)\b",
            r"\b(socket|sockets|outlet|outlets|switchboard|switch board|switch|switches|fuse|fuse box|mcb|wiring|electrical|electricity|meter)\b.{0,40}\b(water|wet|leak|leaks|leaking|leakage|dripping|flood|flooded|flooding|seepage)\b",
        ),
        actions=(
            "Stay away from the wet area and electrical fittings.",
            "Switch off power at the main supply only if you can reach it without standing in water.",
        ),
    ),
    Rule(
        name="carbon_monoxide",
        severity="emergency",
        concern="Possible carbon monoxide",
        patterns=(
            r"\bcarbon monoxide\b",
            r"\bco (alarm|alarms|detector|detectors)\b",
        ),
        actions=(
            "Move to fresh air immediately.",
            "Call your local emergency number (112 in India).",
        ),
    ),
    Rule(
        name="structural_collapse",
        severity="emergency",
        concern="Possible structural collapse",
        patterns=(
            r"\bcollaps(e|ed|es|ing)\b",
            r"\bcaving in\b|\bcave in\b",
            r"\b(ceiling|roof|slab|balcony|wall)\b.{0,25}\b(falling|fell|fallen|sagging)\b",
        ),
        actions=(
            "Keep people away from the affected area.",
            "Call your local emergency number (112 in India) if anyone is in danger.",
        ),
    ),
    Rule(
        name="person_trapped_or_injured",
        severity="emergency",
        concern="Person may be trapped or injured",
        patterns=(
            r"\b(stuck|trapped)\s+(in|inside)\s+(the\s+|a\s+|an\s+)?(lift|elevator|bathroom|room|toilet)\b",
            r"\b(injured|unconscious|bleeding|not breathing|fainted)\b",
        ),
        actions=("Call your local emergency number (112 in India) now.",),
    ),
    Rule(
        name="flooding_or_burst_pipe",
        severity="high",
        concern="Flooding or burst pipe",
        patterns=(
            r"\b(flood|flooded|flooding|floods)\b",
            r"\b(burst|bursting|broken)\s+(water\s+)?pipes?\b",
            r"\bpipe\s+(burst|bursts|has burst|broke|broken)\b",
            r"\bwater\b.{0,20}\b(gushing|pouring|spraying)\b",
            r"\b(gushing|pouring|spraying)\b.{0,20}\bwater\b",
        ),
        actions=("Turn off the water supply valve if you can reach it safely.",),
    ),
    Rule(
        name="sewage_overflow",
        severity="high",
        concern="Sewage overflow (health hazard)",
        patterns=(
            r"\bsewage\b",
            r"\bsewer\b.{0,20}\b(overflow\w*|backup|backing|leak\w*|smell\w*)\b",
            r"\bseptic\b.{0,20}\boverflow\w*",
        ),
        actions=("Avoid contact with the water and keep the area clear.",),
    ),
    Rule(
        name="fire_safety_equipment",
        severity="high",
        concern="Fire safety equipment problem",
        patterns=(
            r"\bfire\s+(alarm|alarms|extinguisher|extinguishers|exit|exits|door|doors|sprinkler|sprinklers|hose|panel)\b",
            r"\bsmoke\s+(alarm|alarms|detector|detectors)\b",
        ),
        actions=("Make sure people know the nearest fire exits until this is fixed.",),
    ),
)


class SafetyResult(BaseModel):
    is_safety_critical: bool
    min_urgency: str | None  # "emergency", "high", or None
    triggered_rules: list[str]
    concerns: list[str]
    immediate_actions: list[str]


def check_safety(text: str) -> SafetyResult:
    """Scans the complaint text against every rule and returns what was found."""
    cleaned = " ".join((text or "").lower().split())

    triggered_rules: list[str] = []
    concerns: list[str] = []
    actions: list[str] = []
    has_emergency = False
    has_high = False

    for rule in RULES:
        if any(re.search(pattern, cleaned) for pattern in rule.patterns):
            triggered_rules.append(rule.name)
            concerns.append(rule.concern)
            for action in rule.actions:
                if action not in actions:
                    actions.append(action)
            if rule.severity == "emergency":
                has_emergency = True
            else:
                has_high = True

    if has_emergency:
        min_urgency = "emergency"
    elif has_high:
        min_urgency = "high"
    else:
        min_urgency = None

    return SafetyResult(
        is_safety_critical=has_emergency,
        min_urgency=min_urgency,
        triggered_rules=triggered_rules,
        concerns=concerns,
        immediate_actions=actions,
    )


def merge_urgency(llm_urgency: str | None, safety: SafetyResult) -> str:
    """Final urgency = the HIGHER of the LLM's guess and the rules' minimum.
    The LLM can raise urgency but can never lower what the rules require."""
    levels = []
    if llm_urgency in URGENCY_LEVELS:
        levels.append(URGENCY_LEVELS.index(llm_urgency))
    else:
        levels.append(URGENCY_LEVELS.index("medium"))  # unknown or missing -> medium
    if safety.min_urgency in URGENCY_LEVELS:
        levels.append(URGENCY_LEVELS.index(safety.min_urgency))
    return URGENCY_LEVELS[max(levels)]
