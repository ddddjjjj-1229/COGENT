import ast


def convert_knowledge_perspectives_to_markdown(data):
    markdown_text = ""
    for category, items in data.items():
        markdown_text += f"- **{category.capitalize()}**\n"
        for item in items:
            markdown_text += f"  - {item}\n"
    return markdown_text


def prepare_markdown_document(document_structure, knowledge_points, knowledge_drafts):
    if isinstance(knowledge_points, str):
        knowledge_points = ast.literal_eval(knowledge_points)
    if isinstance(knowledge_drafts, str):
        knowledge_drafts = ast.literal_eval(knowledge_drafts)
    if isinstance(document_structure, str):
        document_structure = ast.literal_eval(document_structure)
    if not isinstance(document_structure, dict):
        document_structure = {}
    if isinstance(knowledge_points, dict) and "knowledge_points" in knowledge_points:
        knowledge_points = knowledge_points.get("knowledge_points")
    if isinstance(knowledge_drafts, dict) and "knowledge_drafts" in knowledge_drafts:
        knowledge_drafts = knowledge_drafts.get("knowledge_drafts")
    if not isinstance(knowledge_points, list):
        knowledge_points = []
    if not isinstance(knowledge_drafts, list):
        knowledge_drafts = []
    part_titles = {
        'foundational': "## Foundational Concepts",
        'practical': "## Practical Applications",
        'strategic': "## Strategic Insights"
    }

    title = str(document_structure.get("title", "")).strip() or "Learning Session"
    overview = str(document_structure.get("overview", "")).strip()
    summary = str(document_structure.get("summary", "")).strip()

    learning_document = f"# {title}"
    if overview:
        learning_document += f"\n\n{overview}"

    for k_type, part_title in part_titles.items():
        section_chunks = []
        for k_id, knowledge_point in enumerate(knowledge_points):
            if not isinstance(knowledge_point, dict) or knowledge_point.get('type') != k_type:
                continue
            if k_id >= len(knowledge_drafts):
                continue
            knowledge_draft = knowledge_drafts[k_id]
            if not isinstance(knowledge_draft, dict):
                continue
            draft_title = str(knowledge_draft.get('title', '')).strip()
            draft_content = str(knowledge_draft.get('content', '')).strip()
            if not draft_title and not draft_content:
                continue
            section_chunks.append(f"\n\n### {draft_title}\n\n{draft_content}\n")
        if section_chunks:
            learning_document += f"\n\n{part_title}\n"
            learning_document += "".join(section_chunks)
    if summary:
        learning_document += f"\n\n## Summary\n\n{summary}"
    return learning_document
