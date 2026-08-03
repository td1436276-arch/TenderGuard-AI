from __future__ import annotations

import io
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import BinaryIO

import pandas as pd
import pymupdf

from .boq import normalise_text
from .models import Finding


@dataclass
class PageText:
    page: int
    text: str


@dataclass
class Clause:
    page: int
    reference: str
    text: str


TRADE_KEYWORDS = {
    "waterproofing": {"waterproof", "waterproofing", "membrane", "tanking", "damp proof"},
    "sealants": {"sealant", "caulking", "movement joint"},
    "doors": {"door", "doors", "ironmongery", "door frame"},
    "windows": {"window", "glazing", "glass"},
    "concrete": {"concrete", "formwork", "reinforcement", "rebar"},
    "finishes": {"paint", "painting", "tiling", "tile", "plaster", "screed"},
    "drainage": {"drain", "drainage", "pipework", "gully", "manhole"},
}

LOCATION_TERMS = {
    "toilet",
    "toilets",
    "balcony",
    "balconies",
    "roof",
    "roofs",
    "basement",
    "bathroom",
    "bathrooms",
    "kitchen",
    "wet area",
    "external",
    "internal",
}

REQUIREMENT_WORDS = {
    "provide",
    "supply",
    "install",
    "include",
    "allow",
    "construct",
    "apply",
    "test",
    "complete",
    "remove",
}


def extract_pdf_pages(source: bytes | BinaryIO) -> list[PageText]:
    if hasattr(source, "read"):
        data = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
    else:
        data = source
    document = pymupdf.open(stream=data, filetype="pdf")
    pages = [
        PageText(page=index + 1, text=page.get_text("text", sort=True).strip())
        for index, page in enumerate(document)
    ]
    document.close()
    return pages


def split_clauses(pages: list[PageText]) -> list[Clause]:
    clauses: list[Clause] = []
    clause_pattern = re.compile(r"(?im)^\s*(?:clause\s+)?(\d+(?:\.\d+)+)\s*$")
    for page in pages:
        text = re.sub(r"(?im)^\s*page\s+\d+\s*$", "", page.text).strip()
        if not text:
            continue
        matches = list(clause_pattern.finditer(text))
        if matches:
            for index, match in enumerate(matches):
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                body = re.sub(r"\s+", " ", text[start:end]).strip()
                if body:
                    clauses.append(Clause(page.page, f"Clause {match.group(1)}", body))
        else:
            paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", text)]
            for index, paragraph in enumerate(paragraphs, start=1):
                if paragraph:
                    clauses.append(Clause(page.page, f"Page {page.page}, passage {index}", paragraph))
    return clauses


def _trade_for(text: str) -> tuple[str, set[str]] | None:
    normalised = normalise_text(text)
    for trade, keywords in TRADE_KEYWORDS.items():
        if any(normalise_text(keyword) in normalised for keyword in keywords):
            return trade, keywords
    return None


def _requirement_clause(clause: Clause) -> bool:
    words = set(normalise_text(clause.text).split())
    return bool(words & REQUIREMENT_WORDS)


def _similarity(left: str, right: str) -> float:
    left = normalise_text(left)
    right = normalise_text(right)
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return 0.55 * sequence + 0.45 * jaccard


def _location_tokens(text: str) -> set[str]:
    normalised = normalise_text(text)
    return {
        term
        for term in LOCATION_TERMS
        if re.search(rf"\b{re.escape(normalise_text(term))}\b", normalised)
    }


def run_specification_checks(boq: pd.DataFrame, clauses: list[Clause]) -> list[Finding]:
    findings: list[Finding] = []
    for clause in clauses:
        if not _requirement_clause(clause):
            continue
        trade_match = _trade_for(clause.text)
        if not trade_match:
            continue
        trade, keywords = trade_match
        candidates = boq[
            boq["Normalised Description"].apply(
                lambda description: any(normalise_text(keyword) in description for keyword in keywords)
            )
        ]
        best_score = 0.0
        best_row = None
        for _, candidate in candidates.iterrows():
            score = _similarity(clause.text, str(candidate["Description"]))
            if score > best_score:
                best_score = score
                best_row = candidate

        required_locations = _location_tokens(clause.text)
        candidate_location_match = False
        if required_locations and not candidates.empty:
            candidate_location_match = any(
                bool(required_locations & _location_tokens(str(description)))
                for description in candidates["Description"].tolist()
            )

        missing_trade = candidates.empty
        location_gap = bool(required_locations) and not candidate_location_match
        if not (missing_trade or location_gap):
            continue

        candidate_rows = [int(value) for value in candidates["BOQ Row"].head(5).tolist()]
        candidate_items = [str(value) for value in candidates["Item No."].head(5).tolist()]
        if best_row is None:
            comparison = "No candidate BOQ item was found for this trade."
        else:
            comparison = (
                f"Closest BOQ item: row {int(best_row['BOQ Row'])}, "
                f"'{best_row['Description']}' (similarity {best_score:.0%})."
            )
        reason = "No matching trade item was found."
        if location_gap:
            reason = f"Location term(s) {', '.join(sorted(required_locations))} were not found in candidate BOQ descriptions."
        findings.append(
            Finding(
                check_type="Potential omission",
                title=f"Specification requirement may be absent from the BOQ ({trade})",
                risk="Medium",
                confidence=0.78 if location_gap or missing_trade else 0.65,
                method="Evidence heuristic",
                boq_rows=candidate_rows,
                item_numbers=candidate_items,
                specification_pages=[clause.page],
                clause_reference=clause.reference,
                evidence=f"Specification: {clause.text}\n\n{comparison}\n{reason}",
                explanation="TenderGuard could not identify a clearly corresponding BOQ description using the prototype trade and location rules.",
                recommended_action="A QS should confirm whether the requirement is included elsewhere, measured under another description, or should be added.",
            )
        )
    return findings
