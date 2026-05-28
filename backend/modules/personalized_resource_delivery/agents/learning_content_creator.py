from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import BaseModel

from base import BaseAgent
from base.search_rag import SearchRagManager
from modules.personalized_resource_delivery.prompts.learning_content_creator import (
    learning_content_creator_system_prompt,
    learning_content_creator_task_prompt_content,
    learning_content_creator_task_prompt_draft,
    learning_content_creator_task_prompt_outline,
)
from modules.personalized_resource_delivery.schemas import ContentOutline, KnowledgeDraft, LearningContent


APPROACH_VARIANT_MAP = {
    "deep": {
        "content_style": "Detailed explanations with conceptual connections and reflection prompts",
        "activity_type": "Interactive inquiry, self-explanation, and comparison tasks",
    },
    "surface": {
        "content_style": "Concise summaries, key definitions, and stepwise recall supports",
        "activity_type": "Guided reading, repetition, and structured recall practice",
    },
    "achieving": {
        "content_style": "Goal-focused summaries, high-yield explanations, and exam-oriented checkpoints",
        "activity_type": "Targeted practice, milestone tracking, and performance-optimized exercises",
    },
}


class ContentBasePayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    external_resources: str | None = ""


class ContentDraftPayload(ContentBasePayload):
    document_section: Any


class LearningContentCreator(BaseAgent):
    name: str = "LearningContentCreator"

    def __init__(self, model: Any, *, search_rag_manager: Optional[SearchRagManager] = None):
        super().__init__(model=model, system_prompt=learning_content_creator_system_prompt, jsonalize_output=True)
        self.search_rag_manager = search_rag_manager

    def prepare_outline(self, payload: ContentBasePayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentBasePayload):
            payload = ContentBasePayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_outline)
        validated_output = ContentOutline.model_validate(raw_output)
        return validated_output.model_dump()

    def draft_section(self, payload: ContentDraftPayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentDraftPayload):
            payload = ContentDraftPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_draft)
        validated_output = KnowledgeDraft.model_validate(raw_output)
        return validated_output.model_dump()

    def create_content(self, payload: ContentBasePayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentBasePayload):
            payload = ContentBasePayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_content)
        validated_output = LearningContent.model_validate(raw_output)
        return validated_output.model_dump()


def prepare_content_outline_with_llm(llm, learner_profile, learning_path, learning_session, *, search_rag_manager: Optional[SearchRagManager] = None):
    creator = LearningContentCreator(llm, search_rag_manager=search_rag_manager)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
    }
    return creator.prepare_outline(payload)


def build_learning_approach_variant_profile(learner_profile, variant_type: str):
    if variant_type == "default":
        return learner_profile
    if not isinstance(learner_profile, dict):
        return learner_profile
    profile_copy = dict(learner_profile)
    learning_preferences = dict(profile_copy.get("learning_preferences", {}))
    mapping = APPROACH_VARIANT_MAP.get(variant_type, {})
    if mapping:
        learning_preferences["content_style"] = mapping["content_style"]
        learning_preferences["activity_type"] = mapping["activity_type"]
        notes = learning_preferences.get("additional_notes", "") or ""
        learning_preferences["additional_notes"] = f"{notes}\nContent variant requested for this session: {variant_type}.".strip()
    profile_copy["learning_preferences"] = learning_preferences
    return profile_copy


def create_learning_content_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    document_outline=None,
    allow_parallel=True,
    with_quiz=True,
    max_workers=3,
    use_search=True,
    output_markdown=True,
    method_name="cogent",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    from .goal_oriented_knowledge_explorer import explore_knowledge_points_with_llm
    from .search_enhanced_knowledge_drafter import draft_knowledge_points_with_llm
    from .learning_document_integrator import integrate_learning_document_with_llm
    from .document_quiz_generator import generate_document_quizzes_with_llm

    def _normalize_knowledge_points(raw_points):
        if isinstance(raw_points, dict) and "knowledge_points" in raw_points:
            raw_points = raw_points.get("knowledge_points")
        return raw_points if isinstance(raw_points, list) else []

    def _normalize_knowledge_drafts(raw_drafts):
        if isinstance(raw_drafts, dict) and "knowledge_drafts" in raw_drafts:
            raw_drafts = raw_drafts.get("knowledge_drafts")
        return raw_drafts if isinstance(raw_drafts, list) else []

    if method_name == "cogent":
        knowledge_points = explore_knowledge_points_with_llm(
            llm, learner_profile, learning_path, learning_session
        )
        knowledge_points = _normalize_knowledge_points(knowledge_points)

        knowledge_drafts = draft_knowledge_points_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            allow_parallel=allow_parallel,
            use_search=use_search,
            max_workers=max_workers,
            search_rag_manager=search_rag_manager,
        )
        knowledge_drafts = _normalize_knowledge_drafts(knowledge_drafts)
        learning_document = integrate_learning_document_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            knowledge_drafts,
            output_markdown=output_markdown,
        )
        learning_content = {"document": learning_document}
        if not with_quiz:
            return learning_content
        document_quiz = generate_document_quizzes_with_llm(
            llm,
            learner_profile,
            learning_document,
            single_choice_count=3,
            multiple_choice_count=0,
            true_false_count=0,
            short_answer_count=0,
        )
        learning_content["quizzes"] = document_quiz
        return learning_content
    else:
        creator = LearningContentCreator(llm, search_rag_manager=search_rag_manager)
        if document_outline is None:
            document_outline = prepare_content_outline_with_llm(
                llm,
                learner_profile,
                learning_path,
                learning_session,
                search_rag_manager=search_rag_manager,
            )
        outline = document_outline if isinstance(document_outline, dict) else document_outline
        payload = {
            "learner_profile": learner_profile,
            "learning_path": learning_path,
            "learning_session": learning_session,
            "external_resources": "",
        }
        return creator.create_content(payload)


def create_learning_content_variants_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    variant_types,
    **kwargs,
):
    variant_contents = {}
    for variant_type in variant_types:
        variant_profile = build_learning_approach_variant_profile(learner_profile, variant_type)
        variant_contents[variant_type] = create_learning_content_with_llm(
            llm,
            variant_profile,
            learning_path,
            learning_session,
            **kwargs,
        )
    return variant_contents
