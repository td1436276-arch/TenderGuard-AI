# Source notes

- OpenAI API integration follows the Responses API structured-output pattern using Pydantic and the current GPT-5.6 model family guidance.
- PDF extraction uses PyMuPDF page-level searchable text with page numbers retained.
- Spreadsheet extraction uses pandas with openpyxl and keeps original Excel row references.
- Streamlit supplies the upload, tab, editable review table and download interface.

Official references are linked in `README.md` and the app's About tab.
