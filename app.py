from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from tenderguard.ai_review import review_omission_candidates
from tenderguard.boq import BOQValidationError, load_boq, run_boq_checks
from tenderguard.demo import demo_boq_bytes, demo_specification_bytes
from tenderguard.models import Finding, RISK_ORDER
from tenderguard.reviews import read_reviews, save_reviews
from tenderguard.specification import extract_pdf_pages, run_specification_checks, split_clauses


PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_ROOT / "data" / "tenderguard_reviews.db"

st.set_page_config(
    page_title="TenderGuard AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1250px;}
    [data-testid="stMetricValue"] {font-size: 1.75rem;}
    .tg-note {border-left: 4px solid #2f6f8f; padding: .7rem 1rem; background: #f3f8fb; border-radius: 4px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def analysis_id(boq_data: bytes, specification_data: bytes) -> str:
    digest = hashlib.sha256(boq_data + specification_data).hexdigest()[:12].upper()
    return f"AN-{digest}"


def risk_sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda item: (RISK_ORDER.get(item.risk, 99), item.check_type, item.reference))


def export_dataframe(findings: list[Finding], review_table: pd.DataFrame | None = None) -> pd.DataFrame:
    records = []
    review_lookup: dict[str, dict[str, object]] = {}
    if review_table is not None and not review_table.empty:
        review_lookup = {str(row["ID"]): row.to_dict() for _, row in review_table.iterrows()}
    for finding in findings:
        review = review_lookup.get(finding.finding_id, {})
        records.append(
            {
                "Finding ID": finding.finding_id,
                "Risk": finding.risk,
                "Check": finding.check_type,
                "Finding": finding.title,
                "Reference": finding.reference,
                "Method": finding.method,
                "Confidence": round(finding.confidence, 2),
                "Evidence": finding.evidence,
                "Explanation": finding.explanation,
                "Recommended action": finding.recommended_action,
                "Status": review.get("Status", "Unreviewed"),
                "Reviewer": review.get("Reviewer", ""),
                "Reviewer note": review.get("Reviewer note", ""),
            }
        )
    return pd.DataFrame(records)


st.title("🛡️ TenderGuard AI")
st.caption("Explainable pre-tender quality assurance for Quantity Surveyors")
st.markdown(
    '<div class="tg-note"><strong>Professional-use boundary:</strong> Findings are potential issues for QS review, not contractual conclusions or automatic corrections.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Analysis settings")
    source_mode = st.radio("Document source", ["Built-in demo", "Upload my documents"])
    fuzzy_threshold = st.slider("Similar-description threshold", 80, 100, 92, help="Higher values produce fewer possible-duplicate findings.")
    reviewer_name = st.text_input("Reviewer name", value="QS reviewer")
    st.divider()
    use_ai = st.toggle("Use optional AI validation", value=False)
    model = st.selectbox(
        "AI model",
        ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna"],
        disabled=not use_ai,
        help="Terra balances quality and cost; Sol prioritises capability; Luna prioritises efficiency.",
    )
    entered_api_key = st.text_input("OpenAI API key", type="password", disabled=not use_ai)
    api_key = entered_api_key.strip() or os.getenv("OPENAI_API_KEY", "").strip()
    st.caption("The key is used only for this running session and is not saved by TenderGuard.")
    st.warning("Use public or synthetic documents for this student prototype. Do not upload confidential tenders without permission.")

st.header("1. Select tender documents")

boq_data: bytes | None = None
specification_data: bytes | None = None

if source_mode == "Built-in demo":
    boq_data = demo_boq_bytes()
    specification_data = demo_specification_bytes()
    left, right = st.columns(2)
    with left:
        st.success("Demo BOQ ready")
        st.download_button(
            "Download demo BOQ",
            data=boq_data,
            file_name="TenderGuard_Demo_BOQ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with right:
        st.success("Demo specification ready")
        st.download_button(
            "Download demo specification",
            data=specification_data,
            file_name="TenderGuard_Demo_Specification.pdf",
            mime="application/pdf",
        )
    st.caption("The demo contains one arithmetic error, one zero rate, one duplicate pair, one unusual unit and one specification-to-BOQ location gap.")
else:
    left, right = st.columns(2)
    with left:
        boq_file = st.file_uploader("BOQ spreadsheet", type=["xlsx"], help="Required columns: Item No., Section, Description, Unit, Quantity, Rate and Amount.")
        if boq_file is not None:
            boq_data = boq_file.getvalue()
    with right:
        specification_file = st.file_uploader("Specification", type=["pdf"], help="The first version supports searchable PDFs, not scanned-image PDFs.")
        if specification_file is not None:
            specification_data = specification_file.getvalue()

analyse = st.button(
    "Analyse tender documents",
    type="primary",
    disabled=not (boq_data and specification_data),
    width="stretch",
)

if analyse and boq_data and specification_data:
    try:
        with st.spinner("Extracting documents and running checks..."):
            boq = load_boq(io.BytesIO(boq_data))
            pages = extract_pdf_pages(specification_data)
            clauses = split_clauses(pages)
            deterministic_findings = run_boq_checks(boq, fuzzy_threshold=fuzzy_threshold)
            omission_candidates = run_specification_checks(boq, clauses)
            ai_message = None
            if use_ai:
                if not api_key:
                    ai_message = "No API key was supplied. Evidence-heuristic omission findings were retained."
                else:
                    omission_candidates, ai_message = review_omission_candidates(
                        omission_candidates,
                        api_key=api_key,
                        model=model,
                    )
            findings = risk_sorted([*deterministic_findings, *omission_candidates])
            current_analysis_id = analysis_id(boq_data, specification_data)
            st.session_state["analysis"] = {
                "id": current_analysis_id,
                "boq": boq,
                "pages": pages,
                "clauses": clauses,
                "findings": findings,
                "ai_message": ai_message,
            }
            st.session_state.pop("review_editor", None)
    except BOQValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Analysis could not be completed: {exc}")

analysis = st.session_state.get("analysis")
if not analysis:
    st.info("Choose the built-in demo or upload both documents, then select Analyse tender documents.")
    st.stop()

findings: list[Finding] = analysis["findings"]
boq: pd.DataFrame = analysis["boq"]
pages = analysis["pages"]
current_analysis_id = analysis["id"]

st.header("2. Review analysis")
if analysis.get("ai_message"):
    st.warning(analysis["ai_message"])

metrics = st.columns(5)
metrics[0].metric("Total findings", len(findings))
metrics[1].metric("High risk", sum(item.risk == "High" for item in findings))
metrics[2].metric("Medium risk", sum(item.risk == "Medium" for item in findings))
metrics[3].metric("Rule-based", sum(item.method in {"Deterministic", "Unit rule", "Similarity rule"} for item in findings))
metrics[4].metric("Document comparison", sum(item.check_type == "Potential omission" for item in findings))

findings_tab, evidence_tab, review_tab, documents_tab, audit_tab, about_tab = st.tabs(
    ["Findings", "Evidence", "QS review", "Documents", "Audit log", "About"]
)

with findings_tab:
    if findings:
        st.dataframe(
            pd.DataFrame([item.table_record() for item in findings]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.success("No potential issues were identified by the enabled checks.")

with evidence_tab:
    if not findings:
        st.info("No findings to display.")
    for finding in findings:
        icon = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}.get(finding.risk, "⚪")
        with st.expander(f"{icon} {finding.title} — {finding.reference}"):
            left, right = st.columns([1, 1])
            with left:
                st.markdown(f"**Check:** {finding.check_type}")
                st.markdown(f"**Risk:** {finding.risk}")
                st.markdown(f"**Method:** {finding.method}")
                st.markdown(f"**Confidence:** {finding.confidence:.0%}")
                st.markdown(f"**Reference:** {finding.reference}")
            with right:
                st.markdown("**Why it was flagged**")
                st.write(finding.explanation)
                st.markdown("**Recommended QS action**")
                st.write(finding.recommended_action)
            st.markdown("**Supporting evidence**")
            st.code(finding.evidence, language=None)

with review_tab:
    if findings:
        base_review = pd.DataFrame(
            [
                {
                    "ID": item.finding_id,
                    "Risk": item.risk,
                    "Finding": item.title,
                    "Reference": item.reference,
                    "Status": "Unreviewed",
                    "Reviewer": reviewer_name or "QS reviewer",
                    "Reviewer note": "",
                }
                for item in findings
            ]
        )
        edited_reviews = st.data_editor(
            base_review,
            key="review_editor",
            width="stretch",
            hide_index=True,
            disabled=["ID", "Risk", "Finding", "Reference"],
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    options=["Unreviewed", "Accepted", "Rejected", "Needs investigation"],
                    required=True,
                ),
                "Reviewer note": st.column_config.TextColumn(width="large"),
            },
        )
        st.session_state["current_review_table"] = edited_reviews
        if st.button("Save review decisions"):
            saved = save_reviews(DATABASE_PATH, current_analysis_id, edited_reviews)
            st.success(f"Saved {saved} reviewed finding(s) to the local audit log.")

        report = export_dataframe(findings, edited_reviews)
        left, right = st.columns(2)
        with left:
            st.download_button(
                "Download findings as CSV",
                data=report.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"TenderGuard_Findings_{current_analysis_id}.csv",
                mime="text/csv",
                width="stretch",
            )
        with right:
            st.download_button(
                "Download findings as JSON",
                data=json.dumps(report.to_dict(orient="records"), ensure_ascii=False, indent=2),
                file_name=f"TenderGuard_Findings_{current_analysis_id}.json",
                mime="application/json",
                width="stretch",
            )
    else:
        st.info("No findings require review.")

with documents_tab:
    st.subheader("Normalised BOQ")
    visible_columns = [column for column in boq.columns if not column.startswith("Normalised")]
    st.dataframe(boq[visible_columns], width="stretch", hide_index=True)
    st.subheader("Specification text by page")
    for page in pages:
        with st.expander(f"Specification page {page.page}"):
            if page.text:
                st.text(page.text)
            else:
                st.warning("No searchable text was extracted. The page may be scanned and require OCR.")

with audit_tab:
    audit = read_reviews(DATABASE_PATH, current_analysis_id)
    if audit.empty:
        st.info("No review decisions have been saved for this analysis.")
    else:
        st.dataframe(audit, width="stretch", hide_index=True)
        st.download_button(
            "Download audit log",
            data=audit.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"TenderGuard_Audit_{current_analysis_id}.csv",
            mime="text/csv",
        )

with about_tab:
    st.markdown(
        """
        ### Prototype scope

        TenderGuard performs arithmetic, missing/zero-rate, duplicate/similar-description,
        unit-rule and specification-to-BOQ evidence checks. The built-in rules are deliberately
        transparent and editable. Optional AI validation uses only shortlisted passages and
        returns structured findings; it does not replace QS judgement.

        **Current limitations:** English-language documents, `.xlsx` BOQs with recognisable
        columns, searchable PDFs, a limited trade vocabulary and no drawing interpretation.

        **Technical references:**

        - [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
        - [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
        - [Streamlit documentation](https://docs.streamlit.io/)
        - [PyMuPDF text extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
        """
    )
