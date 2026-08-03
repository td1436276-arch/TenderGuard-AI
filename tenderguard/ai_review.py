from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import Finding


class ReviewedCandidate(BaseModel):
    finding_id: str
    potential_issue: bool
    risk: Literal["Low", "Medium", "High"]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    recommended_action: str


class ReviewResponse(BaseModel):
    findings: list[ReviewedCandidate]


SYSTEM_PROMPT = """You assist a Quantity Surveyor with a preliminary tender-document review.
Review only the supplied specification passages and candidate BOQ descriptions.
Do not make legal or contractual conclusions. Do not invent missing evidence.
A potential issue means that no clearly corresponding BOQ item is visible in the supplied evidence.
If an item may be covered by a candidate description, return potential_issue=false.
Keep the explanation concise and identify the evidence gap. Every final decision remains with the QS."""


def review_omission_candidates(
    candidates: list[Finding],
    api_key: str,
    model: str = "gpt-5.6-terra",
) -> tuple[list[Finding], str | None]:
    if not candidates:
        return [], None
    try:
        from openai import OpenAI
    except ImportError:
        return candidates, "The OpenAI package is not installed. Heuristic findings were retained."

    compact_candidates = [
        {
            "finding_id": item.finding_id,
            "reference": item.reference,
            "evidence": item.evidence,
        }
        for item in candidates[:20]
    ]
    prompt = (
        "Review these shortlisted potential omissions. Return one decision for every finding_id.\n\n"
        + str(compact_candidates)
    )
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.parse(
            model=model,
            reasoning={"effort": "low"},
            store=False,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text_format=ReviewResponse,
        )
        parsed = response.output_parsed
        if parsed is None:
            return candidates, "The AI returned no structured result. Heuristic findings were retained."
    except Exception as exc:
        return candidates, f"AI validation was unavailable ({exc}). Heuristic findings were retained."

    decisions = {item.finding_id: item for item in parsed.findings}
    confirmed: list[Finding] = []
    for finding in candidates:
        decision = decisions.get(finding.finding_id)
        if decision is None or not decision.potential_issue:
            continue
        finding.risk = decision.risk
        finding.confidence = decision.confidence
        finding.explanation = decision.explanation
        finding.recommended_action = decision.recommended_action
        finding.method = f"AI-assisted ({model})"
        confirmed.append(finding)
    return confirmed, None

