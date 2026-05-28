from __future__ import annotations

import re
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.personalized_resource_delivery.prompts.document_quiz_generator import (
    document_quiz_generator_system_prompt,
    document_quiz_generator_task_prompt,
)
from modules.personalized_resource_delivery.schemas import DocumentQuiz


class DocumentQuizPayload(BaseModel):
    learner_profile: Any
    learning_document: Any
    single_choice_count: int = 0
    multiple_choice_count: int = 0
    true_false_count: int = 0
    short_answer_count: int = 0
    existing_questions: list[str] = Field(default_factory=list)

    @field_validator("learner_profile", "learning_document")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class DocumentQuizGenerator(BaseAgent):
    name: str = "DocumentQuizGenerator"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=document_quiz_generator_system_prompt, jsonalize_output=True)

    def generate(self, payload: DocumentQuizPayload | Mapping[str, Any] | str):
        if not isinstance(payload, DocumentQuizPayload):
            payload = DocumentQuizPayload.model_validate(payload)
        target_counts = {
            "single_choice_questions": payload.single_choice_count,
            "multiple_choice_questions": payload.multiple_choice_count,
            "true_false_questions": payload.true_false_count,
            "short_answer_questions": payload.short_answer_count,
        }
        existing_questions = list(payload.existing_questions)
        merged = {
            "single_choice_questions": [],
            "multiple_choice_questions": [],
            "true_false_questions": [],
            "short_answer_questions": [],
        }
        seen = {_normalize_question_text(q) for q in existing_questions}

        for _ in range(3):
            current_payload = payload.model_copy(update={"existing_questions": sorted(seen)})
            raw_output = self.invoke(current_payload.model_dump(), task_prompt=document_quiz_generator_task_prompt)
            sanitized = _sanitize_document_quiz(raw_output, seen)
            for key in merged:
                merged[key].extend(sanitized.get(key, []))
                merged[key] = _truncate_unique_questions(merged[key], target_counts[key], seen)
            if _quiz_counts_satisfied(merged, target_counts):
                break
            missing_questions = _collect_question_texts(merged)
            seen.update(missing_questions)

        validated_output = DocumentQuiz.model_validate(merged)
        return validated_output.model_dump()


def _normalize_question_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text).strip().lower())
    normalized = re.sub(r"[^\w\u4e00-\u9fff ]+", "", normalized)
    return normalized


def _coerce_single_correct_option(options: list[str], correct_option: Any) -> int | None:
    if isinstance(correct_option, int):
        return correct_option if 0 <= correct_option < len(options) else None
    if isinstance(correct_option, str):
        stripped = correct_option.strip()
        if stripped.isdigit():
            idx = int(stripped)
            return idx if 0 <= idx < len(options) else None
        for idx, option in enumerate(options):
            if stripped == option:
                return idx
    return None


def _coerce_multiple_correct_options(options: list[str], correct_options: list[Any]) -> list[int]:
    resolved: list[int] = []
    for item in correct_options:
        idx = _coerce_single_correct_option(options, item)
        if idx is not None and idx not in resolved:
            resolved.append(idx)
    return resolved


def _sanitize_options(options: list[Any]) -> list[str]:
    cleaned = []
    seen = set()
    for item in options:
        text = str(item).strip()
        if not text:
            continue
        key = _normalize_question_text(text)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _sanitize_document_quiz(raw_output: Mapping[str, Any], seen_questions: set[str]) -> dict[str, list[dict[str, Any]]]:
    sanitized = {
        "single_choice_questions": [],
        "multiple_choice_questions": [],
        "true_false_questions": [],
        "short_answer_questions": [],
    }

    for item in raw_output.get("single_choice_questions", []) or []:
        question = str(item.get("question", "")).strip()
        qkey = _normalize_question_text(question)
        options = _sanitize_options(list(item.get("options", []) or []))
        correct_option = _coerce_single_correct_option(options, item.get("correct_option"))
        if not question or qkey in seen_questions or len(options) < 2 or correct_option is None:
            continue
        seen_questions.add(qkey)
        sanitized["single_choice_questions"].append(
            {
                "question": question,
                "options": options,
                "correct_option": correct_option,
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )

    for item in raw_output.get("multiple_choice_questions", []) or []:
        question = str(item.get("question", "")).strip()
        qkey = _normalize_question_text(question)
        options = _sanitize_options(list(item.get("options", []) or []))
        correct_options = _coerce_multiple_correct_options(options, list(item.get("correct_options", []) or []))
        if not question or qkey in seen_questions or len(options) < 2 or not correct_options:
            continue
        seen_questions.add(qkey)
        sanitized["multiple_choice_questions"].append(
            {
                "question": question,
                "options": options,
                "correct_options": correct_options,
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )

    for item in raw_output.get("true_false_questions", []) or []:
        question = str(item.get("question", "")).strip()
        qkey = _normalize_question_text(question)
        if not question or qkey in seen_questions or not isinstance(item.get("correct_answer"), bool):
            continue
        seen_questions.add(qkey)
        sanitized["true_false_questions"].append(
            {
                "question": question,
                "correct_answer": bool(item.get("correct_answer")),
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )

    for item in raw_output.get("short_answer_questions", []) or []:
        question = str(item.get("question", "")).strip()
        qkey = _normalize_question_text(question)
        expected_answer = str(item.get("expected_answer", "")).strip()
        if not question or qkey in seen_questions or not expected_answer:
            continue
        seen_questions.add(qkey)
        sanitized["short_answer_questions"].append(
            {
                "question": question,
                "expected_answer": expected_answer,
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )

    return sanitized


def _quiz_counts_satisfied(quiz: dict[str, list[dict[str, Any]]], target_counts: dict[str, int]) -> bool:
    return all(len(quiz[key]) >= target_counts[key] for key in target_counts)


def _collect_question_texts(quiz: dict[str, list[dict[str, Any]]]) -> set[str]:
    result = set()
    for key, items in quiz.items():
        for item in items:
            result.add(_normalize_question_text(item.get("question", "")))
    return result


def _truncate_unique_questions(items: list[dict[str, Any]], limit: int, seen_questions: set[str]) -> list[dict[str, Any]]:
    result = []
    local_seen = set()
    for item in items:
        qkey = _normalize_question_text(item.get("question", ""))
        if not qkey or qkey in local_seen:
            continue
        local_seen.add(qkey)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def generate_document_quizzes_with_llm(
    llm,
    learner_profile,
    learning_document,
    single_choice_count: int = 3,
    multiple_choice_count: int = 0,
    true_false_count: int = 0,
    short_answer_count: int = 0,
):
    payload = {
        "learner_profile": learner_profile,
        "learning_document": learning_document,
        "single_choice_count": single_choice_count,
        "multiple_choice_count": multiple_choice_count,
        "true_false_count": true_false_count,
        "short_answer_count": short_answer_count,
    }
    gen = DocumentQuizGenerator(llm)
    return gen.generate(payload)
