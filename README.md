# TenderGuard AI Prototype

TenderGuard is a student prototype for preliminary review of Bills of Quantities and searchable PDF specifications. It flags possible issues and shows traceable evidence for a Quantity Surveyor to verify.

It does **not** make contractual conclusions, replace professional judgement or automatically change tender documents.

## Included features

- BOQ arithmetic validation (`Quantity x Rate` compared with `Amount`).
- Blank and zero-rate detection.
- Exact and highly similar description detection.
- Transparent keyword-to-unit consistency rules.
- Specification-to-BOQ potential omission screening.
- BOQ-row, specification-page and clause references.
- Optional OpenAI validation of shortlisted omission candidates.
- QS accept/reject/needs-investigation controls.
- Local SQLite audit log.
- CSV and JSON findings export.
- Built-in demo BOQ and two-page specification.

## Fast Windows installation

You already have Python installed, so the easiest method is:

1. Extract the downloaded ZIP file.
2. Open the extracted `TenderGuard-Prototype` folder.
3. Double-click `install_tenderguard.bat` once.
4. Wait for `TenderGuard installation completed successfully`.
5. Double-click `run_tenderguard.bat` whenever you want to use the program.
6. Keep the black terminal window open while the webpage is running.

To stop the program, close the terminal or press `Ctrl + C` inside it.

## Manual installation

In the VS Code terminal, opened inside this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## First demonstration

1. Leave **Document source** set to `Built-in demo`.
2. Leave optional AI validation switched off.
3. Select **Analyse tender documents**.
4. Review the summary and open the **Findings** and **Evidence** tabs.
5. Open **QS review**, change statuses and add reviewer notes.
6. Select **Save review decisions**.
7. Download the CSV report.

The demo intentionally contains:

- One arithmetic error in item D002.
- One zero-rate item in D003.
- One duplicate pair, D001 and D004.
- One unusual door unit in D005.
- One balcony waterproofing requirement that is not clearly represented in the BOQ.

## Uploading your own documents

Choose `Upload my documents` in the sidebar.

### BOQ format

The workbook must be `.xlsx` and contain these columns:

| Required column | Accepted alternatives |
| --- | --- |
| Item No. | Item No, Item Number, Item |
| Section | Trade |
| Description | Item Description |
| Unit | UOM |
| Quantity | Qty |
| Rate | Unit Rate |
| Amount | Total |

### Specification format

The specification must be a searchable `.pdf`. If the extracted page text is blank, the PDF is probably scanned and would need OCR, which is outside this first prototype.

## Optional AI validation

The core application works without AI or an API key. When AI validation is enabled, TenderGuard sends only shortlisted evidence passages—not the whole document—to the OpenAI Responses API and requests a structured finding. Requests use `store=False`.

1. Obtain an OpenAI API key from the API platform.
2. Switch on **Use optional AI validation**.
3. Paste the key into the password field.
4. Select a model:
   - `gpt-5.6-terra`: balanced quality and cost.
   - `gpt-5.6-sol`: strongest capability.
   - `gpt-5.6-luna`: efficient, high-volume option.
5. Run the analysis.

ChatGPT subscriptions and API usage are separate products. Do not put an API key directly into source code or share it in screenshots.

## Run the automated tests

Double-click `run_tests.bat`, or run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Prototype limitations

- English-language documents only.
- Searchable PDF text only; no OCR.
- No drawing interpretation or automated quantity take-off.
- Limited trade keywords, unit rules and location vocabulary.
- Excel BOQ structure must be recognisable.
- Similarity and omission findings can produce false positives.
- Local audit records are stored only on the computer running the app.
- AI output can be incorrect and always requires QS verification.

## Files you may edit later

- `tenderguard/boq.py`: header aliases, unit rules and BOQ checks.
- `tenderguard/specification.py`: trade/location vocabulary and omission heuristic.
- `tenderguard/ai_review.py`: structured AI review prompt and model call.
- `app.py`: webpage layout and workflow.

## Technical sources

- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI model guidance: https://developers.openai.com/api/docs/guides/latest-model
- Streamlit documentation: https://docs.streamlit.io/
- PyMuPDF text extraction: https://pymupdf.readthedocs.io/en/latest/recipes-text.html
- openpyxl documentation: https://openpyxl.readthedocs.io/

