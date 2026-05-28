from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from .adapters import _post_json, _to_api_text
from .llm_client import OpenAICompatibleClient, extract_json_block
from .types import LearnerCase


class ContentAdapter(Protocol):
    def generate(
        self,
        case: LearnerCase,
        learner_profile: Dict[str, Any],
        skill_gap: Dict[str, Any],
        learning_path: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


def first_learning_session(learning_path: Dict[str, Any]) -> Any:
    steps = learning_path.get("learning_path") or learning_path.get("steps") or learning_path.get("path_steps") or []
    if isinstance(steps, list) and steps:
        return steps[0]
    return learning_path


def _content_prompt(
    case: LearnerCase,
    learner_profile: Dict[str, Any],
    skill_gap: Dict[str, Any],
    learning_path: Dict[str, Any],
    *,
    method_name: str,
    external_resources: str = "",
) -> list[Dict[str, str]]:
    system_parts = [
        "You are a learning-content generation baseline for a tutoring benchmark.",
        "Return valid JSON only, with keys: title, overview, content, summary, personalization_notes, confidence.",
    ]
    if method_name in {"dirgen", "dirprompt"}:
        system_parts.append("Generate the content directly from the learner profile, skill gap, and learning path without search, outline planning, or staged refinement.")
    elif method_name == "rag":
        system_parts.append("Use the supplied external_resources as retrieval context, but generate the final content directly.")
    elif method_name == "outlinerag":
        system_parts.append("First plan a concise outline internally, then write content that follows the outline and supplied external_resources.")

    payload = {
        "method": method_name,
        "case_id": case.case_id,
        "learning_goal": case.learning_goal,
        "learner_information": case.learner_information,
        "behavior_trace": case.behavior_trace,
        "learner_profile": learner_profile,
        "skill_gap": skill_gap,
        "learning_path": learning_path,
        "selected_learning_session": first_learning_session(learning_path),
        "external_resources": external_resources,
    }
    return [
        {"role": "system", "content": "\n".join(system_parts)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def fallback_learning_content(
    case: LearnerCase,
    learner_profile: Dict[str, Any],
    skill_gap: Dict[str, Any],
    learning_path: Dict[str, Any],
    *,
    note: str,
) -> Dict[str, Any]:
    session = first_learning_session(learning_path)
    if isinstance(session, dict):
        title = str(session.get("title") or session.get("name") or case.learning_goal)
        summary = str(session.get("abstract") or session.get("description") or "")
        skills = session.get("associated_skills") or session.get("skills") or []
    else:
        title = str(session or case.learning_goal)
        summary = ""
        skills = []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]
    skill_text = ", ".join(str(skill) for skill in skills[:6]) or case.learning_goal
    return {
        "title": title,
        "overview": summary or f"Focused learning content for {case.learning_goal}.",
        "content": (
            f"# {title}\n\n"
            f"## Learning Focus\nThis session supports the learner's goal: {case.learning_goal}.\n\n"
            f"## Target Skills\n{skill_text}\n\n"
            "## Guided Explanation\nStart from the learner's current profile, connect the topic to the identified skill gaps, "
            "and use concise worked examples before asking the learner to practice independently.\n\n"
            "## Practice Activity\nComplete a small applied exercise, compare the result with the expected reasoning, "
            "and note which concepts require follow-up reinforcement.\n"
        ),
        "summary": "Fallback content generated without backend retrieval because the original content service failed.",
        "personalization_notes": "Uses the shared learner profile, skill gap, and selected learning session from the benchmark context.",
        "fallback_note": note,
        "confidence": 0.5,
    }


@dataclass
class PromptContentAdapter:
    llm: OpenAICompatibleClient
    method_name: str
    external_resources: str = ""
    search_enabled: bool = False
    search_api_key_env: str = "SERPER_API_KEY"
    search_max_results: int = 5

    def _search_resources(self, case: LearnerCase, learning_path: Dict[str, Any]) -> str:
        if not self.search_enabled:
            return self.external_resources
        api_key = os.getenv(self.search_api_key_env, "").strip()
        if not api_key:
            return self.external_resources
        session = first_learning_session(learning_path)
        session_title = ""
        if isinstance(session, dict):
            session_title = str(session.get("title") or session.get("name") or "").strip()
        query = f"{case.job.title} {session_title or case.learning_goal} learning content"
        payload = json.dumps({"q": query, "num": self.search_max_results}).encode("utf-8")
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=payload,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                search_payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return self.external_resources

        resources = []
        for item in search_payload.get("organic", [])[: self.search_max_results]:
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            link = str(item.get("link", "")).strip()
            if title or snippet:
                resources.append(f"- {title}: {snippet} ({link})")
        if not resources:
            return self.external_resources
        prefix = self.external_resources.strip()
        joined = "\n".join(resources)
        return f"{prefix}\n{joined}".strip() if prefix else joined

    def generate(
        self,
        case: LearnerCase,
        learner_profile: Dict[str, Any],
        skill_gap: Dict[str, Any],
        learning_path: Dict[str, Any],
    ) -> Dict[str, Any]:
        external_resources = self._search_resources(case, learning_path)
        messages = _content_prompt(
            case,
            learner_profile,
            skill_gap,
            learning_path,
            method_name=self.method_name,
            external_resources=external_resources,
        )
        content = self.llm.chat(messages)
        try:
            return extract_json_block(content)
        except Exception as exc:
            return fallback_learning_content(
                case,
                learner_profile,
                skill_gap,
                learning_path,
                note=f"Prompt content JSON parsing failed: {exc}",
            )


@dataclass
class GenMentorContentApiAdapter:
    base_url: str
    variant: str = "genmentor"
    timeout_seconds: Optional[float] = None
    use_search: bool = True
    allow_parallel: bool = True
    with_quiz: bool = True
    fallback_on_error: bool = False

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _post_json(f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}", payload, self.timeout_seconds)

    def _post_with_search_fallback(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._post(endpoint, payload)
        except RuntimeError as exc:
            message = str(exc).lower()
            search_failed = "error sending request" in message or "mojeek.com" in message or "duckduckgo" in message
            if not payload.get("use_search") or not search_failed:
                raise
            retry_payload = dict(payload)
            retry_payload["use_search"] = False
            result = self._post(endpoint, retry_payload)
            result["_fallback_note"] = "Search failed; retried content generation with use_search=False."
            return result

    def generate(
        self,
        case: LearnerCase,
        learner_profile: Dict[str, Any],
        skill_gap: Dict[str, Any],
        learning_path: Dict[str, Any],
    ) -> Dict[str, Any]:
        learning_session = first_learning_session(learning_path)
        if self.variant == "without_refinement":
            knowledge_points = self._post(
                "/explore-knowledge-points",
                {
                    "learner_profile": _to_api_text(learner_profile),
                    "learning_path": _to_api_text(learning_path),
                    "learning_session": _to_api_text(learning_session),
                },
            )
            knowledge_drafts = self._post_with_search_fallback(
                "/draft-knowledge-points",
                {
                    "learner_profile": _to_api_text(learner_profile),
                    "learning_path": _to_api_text(learning_path),
                    "learning_session": _to_api_text(learning_session),
                    "knowledge_points": _to_api_text(knowledge_points),
                    "use_search": self.use_search,
                    "allow_parallel": self.allow_parallel,
                },
            )
            return {
                "knowledge_points": knowledge_points,
                "knowledge_drafts": knowledge_drafts,
                "note": "w/o Refinement baseline: uses section drafts before integration/refinement.",
            }

        payload = {
            "learner_profile": _to_api_text(learner_profile),
            "learning_path": _to_api_text(learning_path),
            "learning_session": _to_api_text(learning_session),
            "use_search": self.use_search,
            "allow_parallel": self.allow_parallel,
            "with_quiz": self.with_quiz,
        }
        try:
            return self._post_with_search_fallback("/tailor-knowledge-content", payload)
        except Exception as exc:
            if not self.fallback_on_error:
                raise
            return fallback_learning_content(
                case,
                learner_profile,
                skill_gap,
                learning_path,
                note=str(exc),
            )

