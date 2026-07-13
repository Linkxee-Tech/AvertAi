"""
NLP worker — parses raw feedback text ("FLOOD 2.5km North", "CROP OK") into
a structured (report_type, intent, confidence) tuple.

This is a lightweight keyword-based stand-in for the BERT-tiny model named in
the blueprint (no ML runtime/model weights available in this environment).
Swap this module's body for a real `transformers` pipeline loading a
fine-tuned bert-tiny checkpoint from GCS — the function signature
(`parse_feedback_text`) is the contract the feedback router depends on, so
that swap requires no router changes.
"""
import random
import re

NLP_KEYWORDS = {
    "sos_emergency": ["sos", "help", "emergency", "urgent rescue", "trapped"],
    "flood_sighting": ["flood", "water rising", "submerged", "bridge", "overflow", "knee height"],
    "drought_severe": ["drought", "dry", "borehole dry", "no rain", "pasture depleted"],
    "crop_pest_report": ["pest", "armyworm", "locust", "infestation"],
    "crop_status_ok": ["ok", "fine", "unaffected", "stable", "good"],
}

DISTANCE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*km", re.IGNORECASE)
DIRECTION_RE = re.compile(r"\b(north|south|east|west|ne|nw|se|sw)\b", re.IGNORECASE)


def parse_feedback_text(raw_text: str):
    """Returns (report_type, parsed_intent, confidence, geo_entity)."""
    text = raw_text.lower()

    # SOS is safety-critical: any match short-circuits everything else at
    # near-certain confidence rather than competing on keyword-count scoring,
    # since a missed or de-prioritized emergency is unacceptable.
    if any(kw in text for kw in NLP_KEYWORDS["sos_emergency"]):
        return "SOS", "sos_emergency", 0.99, None

    best_intent, best_score = "unknown", 0.4
    for intent, keywords in NLP_KEYWORDS.items():
        if intent == "sos_emergency":
            continue
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            score = min(0.95, 0.6 + hits * 0.12 + random.uniform(0, 0.08))
            if score > best_score:
                best_intent, best_score = intent, round(score, 2)

    if "flood" in best_intent:
        report_type = "FLOOD"
    elif "drought" in best_intent:
        report_type = "DROUGHT"
    elif "crop" in best_intent or "pest" in best_intent:
        report_type = "CROP"
    else:
        report_type = "OTHER"

    distance_match = DISTANCE_RE.search(raw_text)
    direction_match = DIRECTION_RE.search(raw_text)
    geo_entity = None
    if distance_match and direction_match:
        geo_entity = f"{distance_match.group(1)}km {direction_match.group(1)}"

    return report_type, best_intent, best_score, geo_entity
