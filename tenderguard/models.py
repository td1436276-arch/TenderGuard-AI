from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field


RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def stable_finding_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10].upper()
    return f"TG-{digest}"


@dataclass
class Finding:
    check_type: str
    title: str
    risk: str
    explanation: str
    recommended_action: str
    evidence: str
    method: str = "Deterministic"
    confidence: float = 1.0
    boq_rows: list[int] = field(default_factory=list)
    item_numbers: list[str] = field(default_factory=list)
    specification_pages: list[int] = field(default_factory=list)
    clause_reference: str = ""
    finding_id: str = ""

    def __post_init__(self) -> None:
        if not self.finding_id:
            self.finding_id = stable_finding_id(
                self.check_type,
                self.title,
                self.boq_rows,
                self.item_numbers,
                self.specification_pages,
                self.clause_reference,
                self.evidence,
            )

    @property
    def reference(self) -> str:
        references: list[str] = []
        if self.boq_rows:
            label = "BOQ row" if len(self.boq_rows) == 1 else "BOQ rows"
            references.append(f"{label} {', '.join(map(str, self.boq_rows))}")
        if self.specification_pages:
            label = "Specification page" if len(self.specification_pages) == 1 else "Specification pages"
            references.append(f"{label} {', '.join(map(str, self.specification_pages))}")
        if self.clause_reference:
            references.append(self.clause_reference)
        return "; ".join(references) or "Document-level"

    def table_record(self) -> dict[str, object]:
        return {
            "ID": self.finding_id,
            "Risk": self.risk,
            "Check": self.check_type,
            "Finding": self.title,
            "Reference": self.reference,
            "Method": self.method,
            "Confidence": f"{self.confidence:.0%}",
        }

    def export_record(self) -> dict[str, object]:
        record = asdict(self)
        record["reference"] = self.reference
        return record
