import pdfplumber


def extract_text_from_pdf(file):
    """Extracts text from the uploaded PDF file."""
    text = ""
    try:
        file.seek(0)
    except Exception:
        pass
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
    try:
        file.seek(0)
    except Exception:
        pass
    return text
