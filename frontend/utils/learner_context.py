from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from utils.pdf import extract_text_from_pdf


TEXT_FILE_SUFFIXES = {".txt", ".md", ".csv"}
IMAGE_FILE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def normalize_context_block(text):
    if text is None:
        return ""
    lines = [line.rstrip() for line in str(text).replace("\r\n", "\n").split("\n")]
    cleaned = "\n".join(line for line in lines if line.strip()).strip()
    return cleaned


def merge_learner_information(existing_information, *new_blocks):
    blocks = []
    seen = set()

    for block in (existing_information, *new_blocks):
        cleaned = normalize_context_block(block)
        if not cleaned:
            continue
        signature = cleaned.casefold()
        if signature in seen:
            continue
        seen.add(signature)
        blocks.append(cleaned)

    return "\n\n".join(blocks).strip()


def _extract_text_from_plain_file(uploaded_file):
    raw = uploaded_file.getvalue()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except Exception:
            continue
    return ""


def _summarize_image(uploaded_file):
    try:
        image = Image.open(BytesIO(uploaded_file.getvalue()))
        width, height = image.size
        return f"Image attachment: {uploaded_file.name} ({width}x{height})."
    except (UnidentifiedImageError, OSError):
        return f"Image attachment: {uploaded_file.name}."


def extract_attachment_context(uploaded_files):
    if not uploaded_files:
        return "", []

    blocks = []
    summaries = []
    for uploaded_file in uploaded_files:
        if uploaded_file is None:
            continue

        suffix = Path(uploaded_file.name or "").suffix.lower()
        uploaded_file.seek(0)

        if suffix == ".pdf":
            try:
                pdf_text = normalize_context_block(extract_text_from_pdf(uploaded_file))
            except Exception:
                pdf_text = ""
            if pdf_text:
                blocks.append(f"Attachment ({uploaded_file.name}):\n{pdf_text}")
                summaries.append(f"{uploaded_file.name} - PDF text extracted")
            else:
                summaries.append(f"{uploaded_file.name} - PDF added")
        elif suffix in TEXT_FILE_SUFFIXES:
            plain_text = normalize_context_block(_extract_text_from_plain_file(uploaded_file))
            if plain_text:
                blocks.append(f"Attachment ({uploaded_file.name}):\n{plain_text}")
                summaries.append(f"{uploaded_file.name} - text extracted")
            else:
                summaries.append(f"{uploaded_file.name} - text file added")
        elif suffix in IMAGE_FILE_SUFFIXES:
            image_summary = _summarize_image(uploaded_file)
            blocks.append(image_summary)
            summaries.append(f"{uploaded_file.name} - image added")
        else:
            summaries.append(f"{uploaded_file.name} - attachment added")

    return merge_learner_information("", *blocks), summaries
