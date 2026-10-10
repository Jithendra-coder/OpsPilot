"""Run the manually authored held-out signature-composition evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import app

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "heldout-signature-cases.json"


def evaluate(cases):
    results = []
    for case in cases:
        expected = case["expected"]
        if expected is not None and expected not in app.CAUSES:
            raise ValueError("Unknown expected cause in case " + str(case.get("id")))
        diagnosis = app.diagnose(case["evidence"], case.get("errors", []))
        correct = diagnosis["cause_id"] == expected if expected is not None else diagnosis["status"] == "inconclusive"
        results.append({"id": case["id"], "expected": expected, "predicted": diagnosis.get("cause_id"),
            "status": diagnosis["status"], "correct": correct})
    positives = sum(item["expected"] is not None for item in results)
    expected_abstentions = len(results) - positives
    supported = sum(item["status"] == "supported" for item in results)
    abstained = len(results) - supported
    correct_supported = sum(item["correct"] and item["expected"] is not None for item in results)
    correct_abstentions = sum(item["correct"] and item["expected"] is None for item in results)
    summary = {
        "case_count": len(results),
        "expected_supported": positives,
        "correct_supported": correct_supported,
        "supported_precision": round(correct_supported / supported, 4) if supported else 0,
        "supported_recall": round(correct_supported / positives, 4) if positives else 0,
        "expected_abstentions": expected_abstentions,
        "correct_abstentions": correct_abstentions,
        "abstention_precision": round(correct_abstentions / abstained, 4) if abstained else 0,
        "abstention_recall": round(correct_abstentions / expected_abstentions, 4) if expected_abstentions else 0,
        "false_supported": sum(item["expected"] is None and item["status"] == "supported" for item in results),
    }
    return {"evaluation_type": "heldout_signature_composition",
        "limitation": "These manual cases evaluate cause selection and abstention only after evidence has been mapped to supported signal IDs. They do not measure raw telemetry classification, provider mapping quality, or field accuracy.",
        "summary": summary, "cases": results}


def main():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = evaluate(fixture["cases"])
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
