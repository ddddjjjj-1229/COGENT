import json
import httpx
from pathlib import Path
import streamlit as st
from config import backend_endpoint, use_mock_data, use_search

FRONTEND_DIR = Path(__file__).resolve().parents[1]

API_NAMES = {
    "chat_with_tutor": "chat-with-tutor",
    "refine_goal": "refine-learning-goal",
    "update_learning_approach_state": "update-learning-approach-state",
    "generate_learning_approach_assessment": "generate-learning-approach-assessment",
    "identify_skill_gap": "identify-skill-gap-with-info",
    "submit_diagnostic_assessment": "submit-diagnostic-assessment",
    "create_profile": "create-learner-profile-with-info",
    "update_profile": "update-learner-profile",
    "schedule_path": "schedule-learning-path",
    "reschedule_path": "reschedule-learning-path",
    "explore_knowledge_perspectives": "explore-knowledge-perspectives",
    "draft_knowledge_perspective": "draft-knowledge-perspective",
    "draft_point_perspectives": "draft-point-perspectives",
    "integrate_knowledge_document": "integrate-knowledge-document",
    "tailor_learning_content": "tailor-learning-content",
    "explore_knowledge_points": "explore-knowledge-points",
    "draft_knowledge_point": "draft-knowledge-point",
    "draft_knowledge_points": "draft-knowledge-points",
    "integrate_learning_document": "integrate-learning-document",
    "generate_document_quizzes": "generate-document-quizzes",
}


def _extract_model_pair(model_item):
    if isinstance(model_item, dict):
        if model_item.get("model_status") == "missing_key":
            return None
        provider = model_item.get("model_provider") or model_item.get("provider")
        name = model_item.get("model_name") or model_item.get("model")
        if provider and name:
            return str(provider), str(name)
    if isinstance(model_item, str) and "/" in model_item:
        provider, name = model_item.split("/", 1)
        if provider.strip() and name.strip():
            return provider.strip().lower(), name.strip()
    return None


def _get_backend_default_model_pair():
    try:
        preferred_models = [
            ("deepseek", "deepseek-v4-flash"),
            ("deepseek", "deepseek-chat"),
            ("qwen", "qwen-plus"),
            ("qwen", "qwen-max"),
        ]
        if "available_models" in st.session_state:
            for item in st.session_state.get("available_models", []):
                pair = _extract_model_pair(item)
                if pair:
                    for preferred in preferred_models:
                        if pair[0].lower() == preferred[0] and pair[1].lower() == preferred[1]:
                            return pair
        models = get_available_models(backend_endpoint)
        if models:
            resolved = []
            for item in models:
                pair = _extract_model_pair(item)
                if pair:
                    resolved.append(f"{pair[0]}/{pair[1]}")
                    for preferred in preferred_models:
                        if pair[0].lower() == preferred[0] and pair[1].lower() == preferred[1]:
                            st.session_state["available_models"] = resolved
                            return pair
            if resolved:
                st.session_state["available_models"] = resolved
    except Exception:
        pass
    return "deepseek", "deepseek-v4-flash"


def build_model_request_fields(llm_type="gpt4o", method_name=None):
    model_provider, model_name = _get_backend_default_model_pair()
    if isinstance(llm_type, str) and "/" in llm_type:
        provider, name = llm_type.split("/", 1)
        if provider.strip():
            model_provider = provider.strip().lower()
        if name.strip():
            model_name = name.strip()
    elif isinstance(llm_type, str) and llm_type.strip():
        normalized = llm_type.strip().lower()
        if normalized in {"gpt4o", "gpt-4o", "openai/gpt-4o", "openai"}:
            model_provider, model_name = _get_backend_default_model_pair()
        else:
            model_name = llm_type.strip()
    return {
        "model_provider": model_provider,
        "model_name": model_name,
        "method_name": "cogent",
    }


def make_post_request(api_name, data, mock_data_path=None, timeout=500):
    """Send a POST request to the backend API, or return mock data if enabled."""
    if use_mock_data and mock_data_path:
        resolved_path = Path(mock_data_path)
        if not resolved_path.is_absolute():
            resolved_path = FRONTEND_DIR / str(mock_data_path).lstrip("./\\")
        return json.loads(resolved_path.read_text(encoding="utf-8"))

    backend_url = f"{backend_endpoint}{api_name}"
    try:
        response = httpx.post(backend_url, json=data, timeout=timeout)
        
        if response.status_code == 200:
            return response.json()
        else:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            return {"_status_code": response.status_code, "_error_detail": detail}
    except Exception as e:
        return {"_status_code": -1, "_error_detail": str(e)}


def get_response_error_detail(response, default_message="Failed to fetch data."):
    if not isinstance(response, dict):
        return default_message
    detail = response.get("_error_detail")
    if detail:
        return str(detail)
    if "detail" in response:
        return str(response["detail"])
    return default_message

def get_available_models(backend_endpoint):
    backend_url = f"{backend_endpoint}list-llm-models"
    try:
        response = httpx.get(backend_url, timeout=30)
        if response.status_code == 200:
            payload = response.json()
            if payload.get("setup_required"):
                st.session_state["llm_setup_hint"] = payload.get(
                    "setup_hint",
                    "No LLM API key is configured.",
                )
            else:
                st.session_state.pop("llm_setup_hint", None)
            return payload.get("models", [])
        else:
            # st.write("Failed to fetch available models. Status code:", response.status_code)
            return []
    except Exception as e:
        # st.write("Failed to fetch available models. Error:", e)
        return []

def chat_with_tutor(chat_messages, learner_profile, llm_type="gpt4o", method_name="cogent"):
    data = {
        "messages": str(chat_messages),
        "learner_profile": str(learner_profile),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["chat_with_tutor"], data, "./assets/data_example/ai)tutor_chat.json")
    return response.get("response") if response else None

def refine_learning_goal(learning_goal, learner_information, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": str(learner_information),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["refine_goal"], data)
    return response.get("refined_goal") if response else "Refined learning goal"


def update_learning_approach_state(learner_profile, learner_interactions, session_information, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "session_information": str(session_information),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["update_learning_approach_state"], data)
    return response.get("learner_profile") if response else None


def generate_learning_approach_assessment(learning_goal, learner_information, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": str(learner_information),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["generate_learning_approach_assessment"], data, "./assets/data_example/learning_approach_assessment.json")
    return response.get("learning_approach_assessment") if response else None

def identify_skill_gap(learning_goal, learner_information, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": str(learner_information),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["identify_skill_gap"], data, "./assets/data_example/skill_gap.json")
    if not response:
        st.session_state["last_skill_gap_error"] = "No response from the capability mapper."
        return None
    if response.get("_status_code"):
        st.session_state["last_skill_gap_error"] = get_response_error_detail(
            response,
            "Capability mapping failed.",
        )
        return None
    skill_gaps = response.get("skill_gaps")
    if isinstance(skill_gaps, dict) and "skill_gaps" in skill_gaps:
        st.session_state.pop("last_skill_gap_error", None)
        return skill_gaps.get("skill_gaps")
    st.session_state.pop("last_skill_gap_error", None)
    return skill_gaps

def create_learner_profile(learning_goal, learner_information, skill_gaps, llm_type="gpt4o", method_name="cogent", initial_learning_approach_state=None):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": str(learner_information),
        "skill_gaps": str(skill_gaps),
        "initial_learning_approach_state": str(initial_learning_approach_state or ""),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["create_profile"], data, "./assets/data_example/learner_profile.json")
    return response.get("learner_profile") if response else None

def update_learner_profile(learner_profile, learner_interactions, learner_information="", session_information="", llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "learner_information": str(learner_information),
        "session_information": str(session_information),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["update_profile"], data, "./assets/data_example/learner_profile.json")
    return response.get("learner_profile") if response else None


def submit_diagnostic_assessment(learning_goal, skill_gaps, diagnostic_submission, learner_profile=None, learner_information="", llm_type="gpt4o", method_name="cogent"):
    data = {
        "learning_goal": str(learning_goal),
        "skill_gaps": str(skill_gaps),
        "diagnostic_submission": str(diagnostic_submission),
        "learner_profile": str(learner_profile or {}),
        "learner_information": str(learner_information),
        **build_model_request_fields(llm_type, method_name),
    }
    return make_post_request(API_NAMES["submit_diagnostic_assessment"], data)

# @st.cache_resource
def schedule_learning_path(learner_profile, session_count, llm_type="gpt4o", method_name=None):
    data = {
        "learner_profile": str(learner_profile),
        "session_count": session_count,
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["schedule_path"], data, "./assets/data_example/learning_path.json")
    if not response:
        st.session_state["last_learning_path_error"] = "No response from the learning path scheduler."
        return None
    if response.get("_status_code"):
        st.session_state["last_learning_path_error"] = get_response_error_detail(response, "Learning path scheduling failed.")
        return None
    learning_path = response.get("learning_path")
    if isinstance(learning_path, list):
        st.session_state.pop("last_learning_path_error", None)
        return learning_path
    st.session_state["last_learning_path_error"] = "The scheduler returned an empty or invalid learning path."
    return None

def reschedule_learning_path(learning_path, learner_profile, session_count, other_feedback="", llm_type="gpt4o", method_name=None):
    data = {
        "learning_path": str(learning_path),
        "learner_profile": str(learner_profile),
        "session_count": int(session_count),
        "other_feedback": str(other_feedback),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request(API_NAMES["reschedule_path"], data, "./assets/data_example/learning_path.json")
    if not response:
        st.session_state["last_learning_path_error"] = "No response from the learning path scheduler."
        return None
    if response.get("_status_code"):
        st.session_state["last_learning_path_error"] = get_response_error_detail(response, "Learning path rescheduling failed.")
        return None
    updated_path = response.get("rescheduled_learning_path") or response.get("learning_path")
    if isinstance(updated_path, list):
        st.session_state.pop("last_learning_path_error", None)
        return updated_path
    st.session_state["last_learning_path_error"] = "The scheduler returned an empty or invalid learning path."
    return None


def tailor_learning_content(learner_profile, learning_path, learning_session, variant_types=None, use_search=True, allow_parallel=True, with_quiz=True, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "variant_types": str(variant_types or ""),
        "use_search": use_search,
        "allow_parallel": allow_parallel,
        "with_quiz": with_quiz,
        **build_model_request_fields(llm_type, method_name),
    }
    return make_post_request(API_NAMES["tailor_learning_content"], data)

# @st.cache_resource
def generate_document_quizzes(learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count, llm_type="gpt4o", method_name=None):
    data = {
        "learner_profile": str(learner_profile),
        "learning_document": str(learning_document),
        "single_choice_count": single_choice_count,
        "multiple_choice_count": multiple_choice_count,
        "true_false_count": true_false_count,
        "short_answer_count": short_answer_count,
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request("generate-document-quizzes", data, "./assets/data_example/document_quiz.json")
    return response.get("document_quiz") if response else None

# @st.cache_resource
def explore_knowledge_points(learner_profile, learning_path, learning_session, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request("explore-knowledge-points", data, "./assets/data_example/knowledge_points.json")
    return response.get("knowledge_points") if response else None

# @st.cache_resource
def draft_knowledge_point(learner_profile, learning_path, learning_session, knowledge_points, knowledge_point, use_search, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "knowledge_point": str(knowledge_point),
        "use_search": use_search,
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request("draft-knowledge-point", data, "./assets/data_example/knowledge_point.json")
    return response.get("knowledge_draft") if response else None

# @st.cache_resource
def draft_knowledge_points(learner_profile, learning_path, learning_session, knowledge_points, allow_parallel, use_search, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "allow_parallel": allow_parallel,
        "use_search": use_search,
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request("draft-knowledge-points", data, "./assets/data_example/knowledge_points.json")
    return response.get("knowledge_drafts") if response else None

# @st.cache_resource
def integrate_learning_document(learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts, output_markdown=False, llm_type="gpt4o", method_name="cogent"):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "knowledge_drafts": str(knowledge_drafts),
        "output_markdown": output_markdown,
        **build_model_request_fields(llm_type, method_name),
    }
    response = make_post_request("integrate-learning-document", data, "./assets/data_example/learning_document.json")
    if output_markdown:
        return response.get("learning_document") if response else None
    else:
        return response.get("learning_document") if response else None
