"""Prompt for advisory failure triage."""

TRIAGE_SYSTEM_PROMPT = (
    "Classify deterministic test evidence as product, test, environment, flaky, "
    "or unknown. Return only a JSON object with exactly these required "
    "fields: category (one of product, test, environment, flaky, unknown), "
    "confidence (number from 0 to 1), rationale (non-empty string), "
    "evidence_references (array of strings), and stop_conditions (array "
    "of strings). Do not use aliases such as classification. "
    "You have no authority to change a test result."
)
