from __future__ import annotations

import itertools
import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import BinaryIO

import pandas as pd

from .models import Finding, RISK_ORDER


CANONICAL_COLUMNS = [
    "Item No.",
    "Section",
    "Description",
    "Unit",
    "Quantity",
    "Rate",
    "Amount",
]

HEADER_ALIASES = {
    "item no": "Item No.",
    "item no.": "Item No.",
    "item number": "Item No.",
    "item": "Item No.",
    "section": "Section",
    "trade": "Section",
    "description": "Description",
    "item description": "Description",
    "unit": "Unit",
    "uom": "Unit",
    "quantity": "Quantity",
    "qty": "Quantity",
    "rate": "Rate",
    "unit rate": "Rate",
    "amount": "Amount",
    "total": "Amount",
}

UNIT_RULES = {
    "membrane": {"m2", "m²", "sqm"},
    "waterproofing": {"m2", "m²", "sqm"},
    "sealant": {"m", "lm"},
    "door": {"nr", "no", "no.", "item", "each", "ea"},
    "window": {"nr", "no", "no.", "item", "each", "ea"},
    "excavation": {"m3", "m³", "cum"},
    "concrete": {"m3", "m³", "cum"},
    "reinforcement": {"kg", "t", "tonne"},
}


class BOQValidationError(ValueError):
    pass


def normalise_header(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    return HEADER_ALIASES.get(text, str(value).strip())


def normalise_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).lower().replace("²", "2").replace("³", "3")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_unit(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value).strip().lower())


def load_boq(source: str | BinaryIO) -> pd.DataFrame:
    try:
        boq = pd.read_excel(source, engine="openpyxl")
    except Exception as exc:
        raise BOQValidationError(f"The Excel workbook could not be read: {exc}") from exc

    boq = boq.dropna(how="all").copy()
    boq.columns = [normalise_header(column) for column in boq.columns]
    missing = [column for column in CANONICAL_COLUMNS if column not in boq.columns]
    if missing:
        raise BOQValidationError(
            "Missing required column(s): "
            + ", ".join(missing)
            + ". Use the built-in demo workbook as a formatting example."
        )

    boq = boq[CANONICAL_COLUMNS].copy()
    boq["BOQ Row"] = boq.index + 2
    for column in ["Quantity", "Rate", "Amount"]:
        boq[column] = pd.to_numeric(boq[column], errors="coerce")
    boq["Normalised Description"] = boq["Description"].map(normalise_text)
    boq["Normalised Unit"] = boq["Unit"].map(normalise_unit)
    return boq.reset_index(drop=True)


def _item_number(row: pd.Series) -> str:
    value = row.get("Item No.", "")
    return "" if pd.isna(value) else str(value)


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return max(sequence, 0.55 * sequence + 0.45 * jaccard)


def check_arithmetic(boq: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    for _, row in boq.iterrows():
        quantity, rate, amount = row["Quantity"], row["Rate"], row["Amount"]
        if any(pd.isna(value) for value in [quantity, rate, amount]):
            continue
        expected = float(quantity) * float(rate)
        difference = float(amount) - expected
        tolerance = max(0.01, abs(expected) * 0.00001)
        if abs(difference) > tolerance:
            findings.append(
                Finding(
                    check_type="Arithmetic",
                    title=f"Amount does not equal Quantity x Rate for item {_item_number(row)}",
                    risk="High",
                    boq_rows=[int(row["BOQ Row"])],
                    item_numbers=[_item_number(row)],
                    evidence=(
                        f"Quantity {quantity:g} x Rate {_money(float(rate))} = {_money(expected)}, "
                        f"but the BOQ amount is {_money(float(amount))}. Difference: {_money(difference)}."
                    ),
                    explanation="The stated amount is inconsistent with the quantity and rate in the same BOQ row.",
                    recommended_action="Confirm the quantity, rate and formula, then correct the amount if required.",
                )
            )
    return findings


def check_unpriced_and_missing(boq: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    for _, row in boq.iterrows():
        item = _item_number(row)
        description = str(row.get("Description", ""))
        rate = row["Rate"]
        quantity = row["Quantity"]
        amount = row["Amount"]
        if pd.isna(rate) or float(rate) == 0:
            displayed_rate = "blank" if pd.isna(rate) else f"{float(rate):g}"
            findings.append(
                Finding(
                    check_type="Unpriced item",
                    title=f"Blank or zero rate for item {item}",
                    risk="Medium",
                    boq_rows=[int(row["BOQ Row"])],
                    item_numbers=[item],
                    evidence=f"{description} has a rate of {displayed_rate}.",
                    explanation="The item may be unintentionally unpriced or included elsewhere.",
                    recommended_action="Confirm the pricing basis and whether the item should carry a rate.",
                )
            )
        missing_fields = [
            name for name, value in [("Quantity", quantity), ("Amount", amount)] if pd.isna(value)
        ]
        if missing_fields:
            findings.append(
                Finding(
                    check_type="Missing value",
                    title=f"Missing numeric value for item {item}",
                    risk="Medium",
                    boq_rows=[int(row["BOQ Row"])],
                    item_numbers=[item],
                    evidence=f"Missing field(s): {', '.join(missing_fields)}.",
                    explanation="The row cannot be completely validated while required numeric values are blank.",
                    recommended_action="Complete the missing values or confirm that the row is intentionally blank.",
                )
            )
    return findings


def check_duplicates(boq: pd.DataFrame, fuzzy_threshold: int = 92) -> list[Finding]:
    findings: list[Finding] = []
    exact_keys: set[tuple[str, str]] = set()
    grouped = boq.groupby(["Normalised Description", "Normalised Unit"], dropna=False)
    for (description, unit), group in grouped:
        if not description or len(group) < 2:
            continue
        exact_keys.add((description, unit))
        rows = [int(value) for value in group["BOQ Row"].tolist()]
        items = [str(value) for value in group["Item No."].tolist()]
        findings.append(
            Finding(
                check_type="Duplicate item",
                title="Exact duplicate BOQ descriptions",
                risk="Medium",
                boq_rows=rows,
                item_numbers=items,
                evidence=f"The same description and unit appear in BOQ rows {', '.join(map(str, rows))}: {group.iloc[0]['Description']}.",
                explanation="The rows may be duplicated, although repeated descriptions can be valid in different locations or sections.",
                recommended_action="Check the sections and scope boundaries before deleting or combining any item.",
            )
        )

    candidates: dict[tuple[str, str], list[pd.Series]] = defaultdict(list)
    for _, row in boq.iterrows():
        key = (normalise_text(row.get("Section", "")), row["Normalised Unit"])
        candidates[key].append(row)

    checked_pairs = 0
    for rows in candidates.values():
        for left, right in itertools.combinations(rows, 2):
            if checked_pairs >= 15000:
                break
            checked_pairs += 1
            left_description = left["Normalised Description"]
            right_description = right["Normalised Description"]
            if not left_description or (left_description, left["Normalised Unit"]) in exact_keys:
                continue
            length_ratio = min(len(left_description), len(right_description)) / max(
                len(left_description), len(right_description), 1
            )
            if length_ratio < 0.65:
                continue
            score = round(_similarity(left_description, right_description) * 100)
            if score >= fuzzy_threshold:
                findings.append(
                    Finding(
                        check_type="Similar item",
                        title=f"Descriptions are {score}% similar",
                        risk="Low",
                        confidence=score / 100,
                        method="Similarity rule",
                        boq_rows=[int(left["BOQ Row"]), int(right["BOQ Row"])],
                        item_numbers=[_item_number(left), _item_number(right)],
                        evidence=f"'{left['Description']}' compared with '{right['Description']}'.",
                        explanation="The descriptions are highly similar and may represent duplication or inconsistent phraseology.",
                        recommended_action="Compare the location, section and scope qualifiers for both items.",
                    )
                )
    return findings


def check_units(boq: pd.DataFrame) -> list[Finding]:
    findings: list[Finding] = []
    for _, row in boq.iterrows():
        description = row["Normalised Description"]
        actual_unit = row["Normalised Unit"]
        for keyword, expected_units in UNIT_RULES.items():
            if keyword in description and actual_unit not in {normalise_unit(unit) for unit in expected_units}:
                findings.append(
                    Finding(
                        check_type="Unit consistency",
                        title=f"Potential unusual unit for item {_item_number(row)}",
                        risk="Medium",
                        confidence=0.8,
                        method="Unit rule",
                        boq_rows=[int(row["BOQ Row"])],
                        item_numbers=[_item_number(row)],
                        evidence=(
                            f"Description contains '{keyword}'. Actual unit: {row['Unit']}. "
                            f"Expected example unit(s): {', '.join(sorted(expected_units))}."
                        ),
                        explanation="The unit differs from the prototype's editable trade-unit rule library.",
                        recommended_action="Confirm the measurement rule and amend either the unit or the description if necessary.",
                    )
                )
                break
    return findings


def run_boq_checks(boq: pd.DataFrame, fuzzy_threshold: int = 92) -> list[Finding]:
    findings = [
        *check_arithmetic(boq),
        *check_unpriced_and_missing(boq),
        *check_duplicates(boq, fuzzy_threshold=fuzzy_threshold),
        *check_units(boq),
    ]
    return sorted(
        findings,
        key=lambda item: (RISK_ORDER.get(item.risk, 99), item.check_type, item.reference),
    )
