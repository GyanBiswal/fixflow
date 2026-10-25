"""Manual check: classify 3 sample complaints with the real LLM and merge with the safety rules."""
from app.tools import check_complaint_safety, classify_complaint

SAMPLES = [
    "Water is leaking under my kitchen sink",
    "I can smell gas near the stove and the kitchen feels stuffy",
    "It's broken",
]

for text in SAMPLES:
    print("=" * 60)
    print("Complaint:", text)
    result = classify_complaint.invoke({"description": text})
    print("LLM result:", result)
    if result["ok"]:
        safety = check_complaint_safety.invoke(
            {"description": text, "llm_urgency": result["urgency"]}
        )
        print("Safety rules:", safety["triggered_rules"])
        print("Final urgency:", safety["final_urgency"], "| safety critical:", safety["is_safety_critical"])
