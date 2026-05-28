import json
import time
import copy
import re
from pathlib import Path
import streamlit as st
from components.time_tracking import track_session_learning_start_time
from utils.request_api import draft_knowledge_points, explore_knowledge_points, generate_document_quizzes, get_response_error_detail, integrate_learning_document, tailor_learning_content, update_learner_profile
from utils.format import prepare_markdown_document
from utils.state import get_current_session_uid, initialize_session_state, save_persistent_state, get_selected_goal, resolve_selected_goal_id
from config import use_mock_data, use_search

FRONTEND_DIR = Path(__file__).resolve().parents[1]
CSS_PATH = FRONTEND_DIR / "assets" / "css" / "main.css"
DATA_EXAMPLE_DIR = FRONTEND_DIR / "assets" / "data_example"

st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


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


def get_candidate_learning_approach_variants(goal):
    state = goal.get("learner_profile", {}).get("learning_preferences", {}).get("learning_approach_state", {}) or {}
    distribution = state.get("distribution", {}) or {}
    confidence = str(state.get("confidence", "")).lower()
    if not distribution:
        return []
    ranked = sorted(
        ((str(k), float(v)) for k, v in distribution.items() if str(k).strip()),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return []
    top_type, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    third_score = ranked[2][1] if len(ranked) > 2 else 0.0
    margin = top_score - second_score
    if margin >= 0.15 and confidence != "low":
        return []
    if margin < 0.10 and (top_score - third_score) < 0.20 and len(ranked) >= 3:
        return [item[0] for item in ranked[:3]]
    if len(ranked) > 1:
        return [top_type, ranked[1][0]]
    return [top_type]


def get_selected_learning_approach_variant(goal, *, render_selector=True):
    session_uid = get_current_session_uid()
    variants = get_candidate_learning_approach_variants(goal)
    if len(variants) <= 1:
        return "default"

    selector_key = f"content_variant_selector::{session_uid}"
    if selector_key not in st.session_state or st.session_state[selector_key] not in variants:
        st.session_state[selector_key] = variants[0]

    if render_selector:
        st.warning("Your current learning-approach state is ambiguous, so two content versions are available for this chapter.")
        selected_variant = st.radio(
            "Choose the content style you want for this chapter:",
            options=variants,
            key=selector_key,
            horizontal=True,
        )
        return selected_variant
    return st.session_state[selector_key]


def build_learning_approach_variant_profile(learner_profile, variant_type):
    if variant_type == "default":
        return learner_profile
    profile_copy = copy.deepcopy(learner_profile)
    learning_preferences = profile_copy.get("learning_preferences", {})
    mapping = APPROACH_VARIANT_MAP.get(variant_type, {})
    if mapping:
        learning_preferences["content_style"] = mapping["content_style"]
        learning_preferences["activity_type"] = mapping["activity_type"]
        extra_note = f"Content variant selected for this chapter: {variant_type}."
        existing_notes = learning_preferences.get("additional_notes", "") or ""
        learning_preferences["additional_notes"] = f"{existing_notes}\n{extra_note}".strip()
    profile_copy["learning_preferences"] = learning_preferences
    return profile_copy


def is_incomplete_learning_document(document):
    if not isinstance(document, str):
        return True
    text = document.strip()
    if not text:
        return True
    level2_headers = re.findall(r"(?m)^##\s+(.+)$", text)
    non_summary_headers = [
        header.strip().lower()
        for header in level2_headers
        if header.strip().lower() != "summary"
    ]
    has_section_body = bool(re.search(r"(?m)^###\s+.+$", text))
    return not non_summary_headers or not has_section_body


def render_learning_content():
    try:
        initialize_session_state()
    except Exception:
        pass

    if "goals" not in st.session_state or not st.session_state.get("goals"):
        st.warning("No active goal is loaded. Please start from onboarding or goal management.")
        try:
            st.switch_page("pages/onboarding.py")
        except Exception:
            pass
        return

    goal = get_selected_goal()
    if not goal:
        st.warning("No valid active goal is selected. Please return to the learning path.")
        try:
            st.switch_page("pages/learning_path.py")
        except Exception:
            pass
        return

    if 'if_render_qizzes' not in st.session_state:
        st.session_state['if_render_qizzes'] = False
        try:
            save_persistent_state()
        except Exception:
            pass

    if not goal["learning_path"]:
        st.error("Learning path is still scheduling. Please visit this page later.")
        return

    render_session_details(goal)
    session_uid = get_current_session_uid()
    selected_variant = get_selected_learning_approach_variant(goal)
    cache_key = session_uid if selected_variant == "default" else f"{session_uid}::{selected_variant}"
    session_id = st.session_state["selected_session_id"]
    selected_gid = resolve_selected_goal_id() or 0
    is_document_available = st.session_state["document_caches"].get(cache_key, False)
    if is_document_available:
        cached_document = st.session_state["document_caches"].get(cache_key, {}).get("document", "")
        if is_incomplete_learning_document(cached_document):
            st.session_state["document_caches"].pop(cache_key, None)
            try:
                save_persistent_state()
            except Exception:
                pass
            is_document_available = False
    if not is_document_available and not st.session_state["if_updating_learner_profile"]:
        learning_content = render_content_preparation(goal, selected_variant=selected_variant, cache_key=cache_key)
        if learning_content is None:
            st.error("Failed to prepare knowledge content.")
            return
    else:
        learning_content = st.session_state["document_caches"].get(cache_key, "")

    track_session_learning_start_time()
    render_type = "by_section"
    document = learning_content.get("document", "")
    if not isinstance(document, str):
        document = str(document)
    if render_type == "by_section":
        render_document_content_by_section(document)
    else:
        render_document_content_by_document(document)

    if st.session_state['if_render_qizzes']:
        quiz_data = learning_content["quizzes"]
        render_questions(quiz_data)
        render_quiz_mastery_result(goal)
        st.divider()
        selected_sid = st.session_state["selected_session_id"]
        complete_button_status = True if goal["learning_path"][st.session_state["selected_session_id"]]["if_learned"] else False
        if complete_button_status:
            st.info("This session is already marked completed, so the completion button is disabled.")
        if st.button("Regenerate", icon=":material/refresh:"):
            st.session_state["document_caches"].pop(cache_key)
            try:
                save_persistent_state()
            except Exception:
                pass
            goal['learner_profile']['behavioral_patterns']['additional_notes'] += f"I have regenerated Session {selected_sid} content.\n"
            st.rerun()
        if st.button("Complete Session", 
                    key="complete-session", type="primary", icon=":material/task_alt:", 
                    use_container_width=True, disabled=complete_button_status or st.session_state["if_updating_learner_profile"]):
            st.session_state["if_updating_learner_profile"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

        st.divider()
        render_content_feedback_form(goal)
        render_motivataional_triggers()


def render_motivataional_triggers():
    curr_time = time.time()
    session_uid = get_current_session_uid()
    session_learning_times = st.session_state["session_learning_times"][session_uid]
    last_session_trigger_time = session_learning_times["trigger_time_list"][-1]
    last_session_trigger_time_index = len(session_learning_times["trigger_time_list"])
    trigger_interval = 60 * 3
    if curr_time - last_session_trigger_time > trigger_interval:
        if last_session_trigger_time_index % 2 == 0:
            st.toast("🌟 Stay hydrated and keep a healthy posture.")
        else:
            st.toast("Progress saved.")
        session_learning_times["trigger_time_list"].append(curr_time)

def render_session_details(goal):
    selected_sid = st.session_state["selected_session_id"]
    session_uid = get_current_session_uid()
    selected_variant = get_selected_learning_approach_variant(goal, render_selector=False)
    cache_key = session_uid if selected_variant == "default" else f"{session_uid}::{selected_variant}"
    session_info = goal["learning_path"][selected_sid]

    col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
    with col1:
        if st.button("Back", icon=":material/arrow_back:", key="back-learning-center"):
            st.session_state["selected_page"] = "Learning Path"
            st.session_state["current_page"][session_uid] = 0

            st.switch_page("pages/learning_path.py")
            try:
                save_persistent_state()
            except Exception:
                pass

    with col3:
        if st.button("Regenerate", icon=":material/refresh:", key="regenerate-content-top"):
            st.session_state["document_caches"].pop(cache_key, None)
            try:
                save_persistent_state()
            except Exception:
                pass
            goal['learner_profile']['behavioral_patterns']['additional_notes'] += f"I have regenerated Session {selected_sid} content.\n"
            st.session_state["current_page"][session_uid] = 0
            st.rerun()

    with col4:
        complete_button_status = True if session_info["if_learned"] else False
        if complete_button_status:
            st.caption("Completed")

        if st.button("Complete Session", 
                     key="complete-session-bottom", type="primary", icon=":material/task_alt:", 
                    #  on_click=update_learner_profile_with_feedback, kwargs={"feedback_data": "", "goal": goal, "session_information": session_info},
                     use_container_width=True, disabled=complete_button_status or st.session_state["if_updating_learner_profile"]):
            st.session_state["if_updating_learner_profile"] = True
            st.session_state["current_page"][session_uid] = 0
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

        if st.session_state.get("if_updating_learner_profile"):
            update_result = update_learner_profile_with_feedback(goal, "", session_info)
            st.session_state["if_updating_learner_profile"] = False
            try:
                save_persistent_state()
            except Exception:
                pass
            if not update_result:
                st.toast("Failed to update learner profile. Please try again.")
                st.rerun()
            else:
                st.toast("Session completed.")
                goal["learning_path"][selected_sid]["if_learned"] = True
                st.session_state["selected_page"] = "Learning Path"
                try:
                    save_persistent_state()
                except Exception:
                    pass
                if get_current_session_uid() in st.session_state["session_learning_times"]:
                    curr_time = time.time()
                    st.session_state["session_learning_times"][get_current_session_uid()]["end_time"] = curr_time
                    
                save_persistent_state()
                st.switch_page("pages/learning_path.py")

    st.write(f"# {session_info['id']}")
    st.write(f"# {session_info['title']}")

    with st.container(border=True):
        st.info(session_info["abstract"])
        associated_skills = session_info["associated_skills"]
        st.write("**Associated Skills:**")
        for i, skill_name in enumerate(associated_skills):
            st.write(f"- {skill_name}")

def render_content_preparation(goal, selected_variant="default", cache_key=None):
    selected_sid = st.session_state["selected_session_id"]
    learning_session = goal["learning_path"][selected_sid]
    session_uid = get_current_session_uid()
    variant_profile = build_learning_approach_variant_profile(goal["learner_profile"], selected_variant)
    effective_cache_key = cache_key or session_uid
    if use_mock_data:
        st.warning("Using mock data for knowledge document.")
        file_path = DATA_EXAMPLE_DIR / "knowledge_document.json"
        learning_content = load_knowledge_point_content(file_path)
        learning_content["selected_variant"] = selected_variant
        st.session_state["document_caches"][effective_cache_key] = learning_content
        try:
            save_persistent_state()
        except Exception:
            pass
        return learning_content

    if selected_variant != "default":
        with st.spinner(f"Generating {selected_variant}-oriented content variant..."):
            response = tailor_learning_content(
                goal["learner_profile"],
                goal["learning_path"],
                learning_session,
                variant_types=[selected_variant],
                use_search=False,
                allow_parallel=True,
                with_quiz=True,
                llm_type="gpt4o",
            )
        if isinstance(response, dict) and response.get("_status_code"):
            st.error(get_response_error_detail(response, "Failed to generate variant content."))
            return None
        if response and response.get("tailored_content_variants", {}).get(selected_variant):
            learning_content = response["tailored_content_variants"][selected_variant]
            learning_content["quizzes"] = merge_review_questions_into_quiz(learning_session, learning_content.get("quizzes", {}))
            learning_content["selected_variant"] = selected_variant
            st.session_state["document_caches"][effective_cache_key] = learning_content
            try:
                save_persistent_state()
            except Exception:
                pass
            return learning_content

    with st.spinner("Stage 1/4 - Exploring knowledge Points..."):
        knowledge_points = explore_knowledge_points(
            variant_profile,
            goal["learning_path"],
            learning_session,
            llm_type="gpt4o"
        )
    if isinstance(knowledge_points, dict) and knowledge_points.get("_status_code"):
        st.error(get_response_error_detail(knowledge_points, "Failed to explore knowledge points."))
        return
    if knowledge_points is None:
        st.error("Failed to explore knowledge points.")
        return
    else:
        st.success("Stage 1/4 🔍 Knowledge points explored successfully.")
        with st.expander("View Explored Knowledge Points", expanded=False):
            for kp in knowledge_points:
                st.write(f"- {kp['name']} (`{kp['type']}`)")
    with st.spinner("Stage 2/4 - Drafting knowledge points..."):
        knowledge_drafts = draft_knowledge_points(
            variant_profile,
            goal["learning_path"],
            learning_session,
            knowledge_points,
            use_search=use_search,
            allow_parallel=True,
            llm_type="gpt4o"
        )
    if isinstance(knowledge_drafts, dict) and knowledge_drafts.get("_status_code"):
        st.error(get_response_error_detail(knowledge_drafts, "Failed to draft knowledge points."))
        return
    if knowledge_drafts is None:
        st.error("Failed to draft knowledge points.")
        return
    st.success("Stage 2/4 📝 Knowledge points drafted successfully.")
    with st.spinner("Stage 3/4 - Integrating knowledge document..."):
        document_structure = integrate_learning_document(
            variant_profile,
            goal["learning_path"],
            learning_session,
            knowledge_points,
            knowledge_drafts,
            llm_type="gpt4o",
            output_markdown=False
        )
        if isinstance(document_structure, dict) and document_structure.get("_status_code"):
            st.error(get_response_error_detail(document_structure, "Failed to integrate learning document."))
            return
        if document_structure is None:
            st.error("Failed to integrate learning document.")
            return
        learning_document = prepare_markdown_document(document_structure, knowledge_points, knowledge_drafts)
    if learning_document is None:
        st.error("Failed to integrate knowledge document.")
        return
    st.success("Stage 3/4 📚 Knowledge document integrated successfully.")
    learning_content = {"document": learning_document}
    with st.spinner("Stage 4/4 - Generating document quizzes..."):
        quizzes = generate_document_quizzes(
            variant_profile,
            learning_document,
            single_choice_count=3,
            multiple_choice_count=1,
            true_false_count=1,
            short_answer_count=1,
            llm_type="gpt4o"
        )
    if isinstance(quizzes, dict) and quizzes.get("_status_code"):
        st.error(get_response_error_detail(quizzes, "Failed to generate document quizzes."))
        return
    learning_content["quizzes"] = quizzes
    learning_content["quizzes"] = merge_review_questions_into_quiz(learning_session, learning_content["quizzes"])
    learning_content["selected_variant"] = selected_variant
    st.success("Stage 4/4 complete. Document quizzes are ready.")
    st.session_state["document_caches"][effective_cache_key] = learning_content
    try:
        save_persistent_state()
    except Exception:
        pass
    return learning_content

def render_document_content_by_section(document):
    selected_gid = resolve_selected_goal_id() or 0
    session_id = st.session_state["selected_session_id"]
    if "current_page" not in st.session_state or not isinstance(st.session_state["current_page"], dict):
        st.session_state["current_page"] = {}

    matches = list(re.finditer(r'(?m)^##\s+.+$', document))
    section_documents = []
    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(document)
        chunk = document[start_idx:end_idx].strip()
        if chunk:
            section_documents.append(chunk)
    if not section_documents and document.strip():
        section_documents = [document.strip()]

    page_key = f"{selected_gid}-{session_id}"
    current_page = st.session_state['current_page'].get(page_key, 0)
    if section_documents:
        current_page = max(0, min(current_page, len(section_documents) - 1))
    else:
        current_page = 0

    prev_page_key = f"{page_key}__prev"
    prev_page = st.session_state.get(prev_page_key, None)
    if prev_page is None or prev_page != current_page:
        st.session_state[prev_page_key] = current_page
        try:
            save_persistent_state()
        except Exception:
            pass
    if section_documents:
        st.markdown(section_documents[current_page])
    else:
        st.info("No sectioned content was generated for this document.")

    st.sidebar.header("Document Structure")
    curr_l2 = 0
    curr_l3 = 0
    page_idx_counter = -1
    for m in re.finditer(r'^(#+)\s*(.+)$', document, re.MULTILINE):
        level_marks, title_txt = m.group(1), m.group(2).strip()
        level_len = len(level_marks)
        if level_len == 1:
            continue
        if level_len == 2:
            page_idx_counter += 1
            curr_l2 += 1
            curr_l3 = 0
            if st.sidebar.button(f"{curr_l2}. {title_txt}", key=f"toc_l2_{page_idx_counter}", type="primary" if page_idx_counter == current_page else "secondary"):
                st.session_state.setdefault("current_page", {})[page_key] = page_idx_counter
                st.rerun()
            st.sidebar.write("")

        elif level_len == 3 and page_idx_counter >= 0:
            curr_l3 += 1
            st.sidebar.caption(f"{curr_l2}.{curr_l3}. {title_txt}")

    col_prev, col_center, col_next= st.columns([1, 4, 1])
    if current_page > 0:
        if col_prev.button("Previous Page", icon=":material/arrow_back:", use_container_width=True, key="prev-section-page"):
            new_page = current_page - 1
            st.session_state["current_page"][page_key] = new_page
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
    if current_page < len(section_documents) - 1:
        if col_next.button("Next Page", icon=":material/arrow_forward:", use_container_width=True, key="next-section-page"):
            new_page = current_page + 1
            st.session_state["current_page"][page_key] = new_page
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

    st.divider()

    if current_page == len(section_documents) - 1:
        st.session_state["if_render_qizzes"] = True
    else:
        st.session_state["if_render_qizzes"] = False

    

def render_document_content_by_document(document):
    st.session_state["if_render_qizzes"] = True

    titles = re.findall(r'^(#+)\s*(.*)', document, re.MULTILINE)

    sections = []
    for level, title in titles:
        section = {'level': len(level), 'title': title}
        sections.append(section)

    sidebar_content = ""
    curr_level_1_idx = 0
    curr_level_2_idx = 0
    curr_level_3_idx = 0
    for i, section in enumerate(sections):
        anchor = re.sub(r'[^\w\s]', '-', section["title"].lower()).replace(" ", "-")
        if section["level"] == 1:
            continue
        if section["level"] == 2:
            curr_level_2_idx += 1
            curr_level_3_idx = 0
            sidebar_content += f"[**{curr_level_2_idx}. {section['title']}**](#{anchor})\n"
        elif section["level"] == 3:
            curr_level_3_idx += 1
            sidebar_content += f"> [{curr_level_2_idx}.{curr_level_3_idx}. {section['title']}](#{anchor})\n\n"

    st.sidebar.header("Document Structure")
    st.sidebar.markdown(sidebar_content)

    st.markdown(document)


def ensure_quiz_attempt_entry():
    session_uid = get_current_session_uid()
    if "quiz_attempts" not in st.session_state:
        st.session_state["quiz_attempts"] = {}
    if session_uid not in st.session_state["quiz_attempts"]:
        st.session_state["quiz_attempts"][session_uid] = {}
    return st.session_state["quiz_attempts"][session_uid]


def record_quiz_result(question_key, is_correct, question_type=None, question_payload=None, learner_answer=None):
    entry = ensure_quiz_attempt_entry()
    entry[question_key] = {
        "is_correct": bool(is_correct),
        "question_type": question_type or "",
        "question_payload": copy.deepcopy(question_payload) if isinstance(question_payload, dict) else question_payload,
        "learner_answer": learner_answer,
    }
    try:
        save_persistent_state()
    except Exception:
        pass


def _normalize_attempt_record(record):
    if isinstance(record, dict):
        return {
            "is_correct": bool(record.get("is_correct", False)),
            "question_type": str(record.get("question_type", "")).strip(),
            "question_payload": record.get("question_payload"),
            "learner_answer": record.get("learner_answer"),
        }
    return {
        "is_correct": bool(record),
        "question_type": "",
        "question_payload": None,
        "learner_answer": None,
    }


def collect_wrong_question_records():
    session_uid = get_current_session_uid()
    answers = st.session_state.get("quiz_attempts", {}).get(session_uid, {})
    wrong_records = []
    for record in answers.values():
        normalized = _normalize_attempt_record(record)
        if normalized["is_correct"]:
            continue
        question_payload = normalized.get("question_payload")
        if not isinstance(question_payload, dict):
            continue
        wrong_records.append(
            {
                "question_type": normalized.get("question_type", ""),
                "question_payload": copy.deepcopy(question_payload),
                "learner_answer": normalized.get("learner_answer"),
            }
        )
    return wrong_records


def build_quiz_performance_payload():
    session_uid = get_current_session_uid()
    answers = st.session_state.get("quiz_attempts", {}).get(session_uid, {})
    total_count = len(answers)
    correct_count = sum(1 for result in answers.values() if _normalize_attempt_record(result)["is_correct"])
    overall_score = round((correct_count / total_count) * 100, 2) if total_count > 0 else 0.0
    mastery_threshold = 80.0
    return {
        "correct_count": correct_count,
        "total_count": total_count,
        "overall_score": overall_score,
        "mastery_threshold": mastery_threshold,
        "mastery_achieved": total_count > 0 and overall_score >= mastery_threshold,
    }


def build_session_behavior_payload():
    session_uid = get_current_session_uid()
    timing = st.session_state.get("session_learning_times", {}).get(session_uid, {})
    start_time = timing.get("start_time")
    end_time = timing.get("end_time", time.time())
    session_duration_seconds = 0.0
    if start_time is not None:
        session_duration_seconds = max(float(end_time) - float(start_time), 0.0)

    tutor_messages = [
        {
            "role": msg.get("role", ""),
            "content": msg.get("content", ""),
            "timestamp": msg.get("timestamp"),
        }
        for msg in st.session_state.get("tutor_messages", [])
        if isinstance(msg, dict) and msg.get("session_uid") == session_uid
    ]
    tutor_question_count = sum(1 for msg in tutor_messages if msg.get("role") == "user")
    quiz_performance = build_quiz_performance_payload()

    return {
        "session_uid": session_uid,
        "session_duration_seconds": round(session_duration_seconds, 2),
        "activity_participation": {
            "quiz_attempted_count": quiz_performance.get("total_count", 0),
            "tutor_question_count": tutor_question_count,
            "tutor_message_count": len(tutor_messages),
            "quiz_rendered": bool(st.session_state.get("if_render_qizzes", False)),
        },
        "quiz_performance": quiz_performance,
        "tutor_qa_history": tutor_messages[-20:],
    }


def merge_review_questions_into_quiz(session_info, generated_quizzes):
    if not isinstance(generated_quizzes, dict):
        return generated_quizzes

    review_questions = list(session_info.get("previous_wrong_questions", []) or [])
    if not review_questions:
        quiz_history = list(session_info.get("quiz_history", []) or [])
        if quiz_history:
            review_questions = list(quiz_history[-1].get("wrong_questions", []) or [])
    if not review_questions:
        return generated_quizzes

    merged = copy.deepcopy(generated_quizzes)
    type_key_map = {
        "single_choice": "single_choice_questions",
        "multiple_choice": "multiple_choice_questions",
        "true_false": "true_false_questions",
        "short_answer": "short_answer_questions",
        "single_choice_questions": "single_choice_questions",
        "multiple_choice_questions": "multiple_choice_questions",
        "true_false_questions": "true_false_questions",
        "short_answer_questions": "short_answer_questions",
    }

    def _question_signature(question_item):
        if not isinstance(question_item, dict):
            return ""
        return re.sub(r"\s+", " ", str(question_item.get("question", "")).strip().lower())

    for raw_type, target_key in type_key_map.items():
        merged.setdefault(target_key, [])

    for review_item in review_questions:
        raw_type = str(review_item.get("question_type", "")).strip()
        target_key = type_key_map.get(raw_type)
        question_payload = review_item.get("question_payload")
        if not target_key or not isinstance(question_payload, dict):
            continue
        existing_signatures = {_question_signature(item) for item in merged.get(target_key, [])}
        signature = _question_signature(question_payload)
        if signature and signature not in existing_signatures:
            merged[target_key] = [copy.deepcopy(question_payload)] + list(merged.get(target_key, []))

    return merged


def apply_mastery_gap_remediation_to_learning_path(goal, session_index, wrong_questions=None):
    learning_path = goal.get("learning_path", [])
    if not (0 <= session_index < len(learning_path)):
        return

    session = learning_path[session_index]
    session["needs_reinforcement"] = True
    weak_skills = [
        item.get("name", "")
        for item in session.get("desired_outcome_when_completed", [])
        if isinstance(item, dict)
    ]
    remediation_actions = [
        "insert supplementary explanations",
        "add targeted reinforcement exercises",
        "review prerequisite knowledge",
        "reduce difficulty progression in the next sessions",
        "provide extra cases and guided practice",
    ]
    session["remediation_actions"] = remediation_actions

    remediation_session_id = f"{session.get('id', f'Session {session_index + 1}')} - Reinforcement"
    existing_ids = {str(item.get("id", "")) for item in learning_path}
    if remediation_session_id not in existing_ids:
        remediation_session = {
            "id": remediation_session_id,
            "title": f"{session.get('title', 'Session')} Reinforcement",
            "abstract": (
                "This reinforcement session is automatically inserted because the previous chapter quiz "
                "did not reach the mastery threshold. It adds supplementary explanations, prerequisite "
                "review, guided examples, and targeted practice before the learner moves on."
            ),
            "if_learned": False,
            "associated_skills": list(session.get("associated_skills", []) or []),
            "desired_outcome_when_completed": copy.deepcopy(session.get("desired_outcome_when_completed", []) or []),
            "is_remediation": True,
            "source_session_id": session.get("id", ""),
            "reinforcement_targets": weak_skills,
            "remediation_actions": remediation_actions,
            "previous_wrong_questions": copy.deepcopy(wrong_questions or []),
        }
        learning_path.insert(session_index + 1, remediation_session)
    else:
        for item in learning_path:
            if str(item.get("id", "")) == remediation_session_id:
                item["previous_wrong_questions"] = copy.deepcopy(wrong_questions or [])
                item["reinforcement_targets"] = weak_skills
                item["remediation_actions"] = remediation_actions
                break

    adjusted = 0
    for future_session in learning_path[session_index + 1:]:
        if future_session.get("is_remediation"):
            continue
        if future_session.get("if_learned"):
            continue
        future_session["difficulty_adjustment"] = "easier"
        future_session["guided_practice_required"] = True
        future_session["prerequisite_review_skills"] = weak_skills
        abstract = str(future_session.get("abstract", "")).strip()
        remediation_note = " Includes prerequisite review, guided practice, and additional examples because the previous session did not reach mastery."
        if remediation_note.strip() not in abstract:
            future_session["abstract"] = (abstract + remediation_note).strip()
        adjusted += 1
        if adjusted >= 2:
            break


def build_structured_learner_interactions(feedback_data):
    return {
        "content_feedback": feedback_data,
        "session_behavior": build_session_behavior_payload(),
    }


def _latest_mastery_evidence_by_skill(mastery_evidence):
    latest = {}
    for item in mastery_evidence or []:
        if not isinstance(item, dict):
            continue
        skill_name = str(item.get("skill_name", "")).strip().lower()
        if not skill_name:
            continue
        latest[skill_name] = item
    return latest


def sync_remediation_status_after_profile_update(goal, session_index):
    learning_path = goal.get("learning_path", [])
    if not (0 <= session_index < len(learning_path)):
        return

    current_session = learning_path[session_index]
    mastery_evidence = goal.get("learner_profile", {}).get("cognitive_status", {}).get("mastery_evidence", [])
    latest_by_skill = _latest_mastery_evidence_by_skill(mastery_evidence)
    desired_skill_names = {
        str(item.get("name", "")).strip().lower()
        for item in current_session.get("desired_outcome_when_completed", [])
        if isinstance(item, dict)
    }
    related_evidence = [latest_by_skill[name] for name in desired_skill_names if name in latest_by_skill]
    if not related_evidence:
        return

    mastery_achieved = all(item.get("mastery_achieved", False) for item in related_evidence)
    current_session["needs_reinforcement"] = not mastery_achieved

    if current_session.get("is_remediation") and mastery_achieved:
        source_session_id = str(current_session.get("source_session_id", "")).strip()
        for session in learning_path:
            if str(session.get("id", "")).strip() == source_session_id:
                session["needs_reinforcement"] = False
                session["previous_wrong_questions"] = []
                session["reinforcement_targets"] = []
                session["difficulty_adjustment"] = ""
                session["guided_practice_required"] = False
                session["prerequisite_review_skills"] = []
                break

    if mastery_achieved:
        current_session["previous_wrong_questions"] = []


def render_quiz_mastery_result(goal):
    session_info = goal["learning_path"][st.session_state["selected_session_id"]]
    session_uid = get_current_session_uid()
    local_quiz_result = st.session_state.get("quiz_attempts", {}).get(session_uid, {})
    mastery_evidence = goal.get("learner_profile", {}).get("cognitive_status", {}).get("mastery_evidence", [])
    related_skills = {str(item.get("name", "")).strip().lower() for item in session_info.get("desired_outcome_when_completed", [])}
    latest_by_skill = _latest_mastery_evidence_by_skill(mastery_evidence)
    related_evidence = [latest_by_skill[name] for name in related_skills if name in latest_by_skill]

    if not local_quiz_result and not related_evidence:
        return

    st.subheader("Chapter Quiz Result")
    if local_quiz_result:
        performance = build_quiz_performance_payload()
        if performance["total_count"] > 0:
            st.info(
                f"Score: {performance['correct_count']}/{performance['total_count']} "
                f"({performance['overall_score']}%). Mastery threshold: {performance['mastery_threshold']}%."
            )
            if performance["mastery_achieved"]:
                st.success("Mastery result: threshold reached. The system can treat this chapter as sufficiently mastered.")
            else:
                st.warning("Mastery result: threshold not reached yet. The system should reinforce weak knowledge points.")
        if not session_info.get("if_learned", False):
            st.caption("This is the local quiz result for the current attempt. The learner profile will sync after you complete the session.")

    if related_evidence and session_info.get("if_learned", False):
        st.subheader("Profile-Synced Knowledge Mastery Result")
        for evidence in related_evidence[-5:]:
            skill_name = evidence.get("skill_name", "Unknown skill")
            score = evidence.get("overall_score", 0)
            threshold = evidence.get("mastery_threshold", 80)
            mastery_achieved = evidence.get("mastery_achieved", False)
            mastery_gap = evidence.get("mastery_gap", 0)
            recommended_action = evidence.get("recommended_action", "")
            st.write(f"**{skill_name}**")
            st.write(
                f"Score {score}% / Threshold {threshold}% / "
                f"{'Mastered for this chapter' if mastery_achieved else f'Not yet mastered, gap {mastery_gap}%'}"
            )
            st.caption(f"Recommended action: {recommended_action}")


def render_attempt_feedback(question_key, explanation, *, correct_message="Correct!", incorrect_message="Incorrect."):
    attempt_record = ensure_quiz_attempt_entry().get(question_key)
    normalized = _normalize_attempt_record(attempt_record) if attempt_record is not None else None
    feedback_box = st.container()
    with feedback_box:
        if normalized is None:
            st.write("")
            return
        if normalized["is_correct"]:
            st.success(correct_message)
        else:
            st.error(incorrect_message)
        if explanation:
            st.caption(f"Explanation: {explanation}")


def render_questions(quiz_data):
    st.subheader("💡 Test Your Knowledge")
    for i, q in enumerate(quiz_data['single_choice_questions']):
        question_key = f"single_{i}"
        st.write(f"**{i+1}. {q['question']}**")
        selected_option = st.radio("Options", q['options'], key=question_key, index=None, label_visibility="hidden")
        if selected_option is not None:
            correct_option_idx = q['correct_option']
            correct_option = q['options'][correct_option_idx]
            is_correct = selected_option == correct_option
            record_quiz_result(question_key, is_correct, "single_choice", q, selected_option)
        render_attempt_feedback(question_key, q.get('explanation', ''), correct_message="Correct!", incorrect_message="Incorrect.")

    for i, q in enumerate(quiz_data['multiple_choice_questions']):
        question_key = f"multi_{i}"
        st.write(f"**{len(quiz_data['single_choice_questions']) + i + 1}. {q['question']}**")
        
        selected_options = []
        for j, option in enumerate(q['options']):
            if st.checkbox(option, key=f"multi_{i}_option_{j}"):
                selected_options.append(option)

        if st.button("Submit", key=f"multi_submit_{i}"):
            correct_options = set(q['options'][idx] for idx in q['correct_options'])
            is_correct = set(selected_options) == set(correct_options)
            record_quiz_result(question_key, is_correct, "multiple_choice", q, list(selected_options))
        render_attempt_feedback(question_key, q.get('explanation', ''), correct_message="Correct!", incorrect_message="Some options are incorrect.")

    for i, q in enumerate(quiz_data['true_false_questions']):
        question_key = f"tf_{i}"
        st.write(f"**{len(quiz_data['single_choice_questions']) + len(quiz_data['multiple_choice_questions']) + i + 1}. {q['question']}**")
        selected_answer = st.radio("True or False?", ["True", "False"], key=question_key, label_visibility="hidden", index=None)
        correct_answer = "True" if q['correct_answer'] else "False"
        if selected_answer:
            is_correct = selected_answer == correct_answer
            record_quiz_result(question_key, is_correct, "true_false", q, selected_answer)
        render_attempt_feedback(question_key, q.get('explanation', ''), correct_message="Correct!", incorrect_message="Incorrect.")

    for i, q in enumerate(quiz_data['short_answer_questions']):
        question_key = f"short_{i}"
        st.write(f"**{len(quiz_data['single_choice_questions']) + len(quiz_data['multiple_choice_questions']) + len(quiz_data['true_false_questions']) + i + 1}. {q['question']}**")
        user_answer = st.text_input("Your Answer", key=question_key, label_visibility="hidden")
        if user_answer:
            is_correct = user_answer.strip().lower() == q['expected_answer'].strip().lower()
            record_quiz_result(question_key, is_correct, "short_answer", q, user_answer)
        render_attempt_feedback(question_key, q.get('explanation', ''), correct_message="Correct!", incorrect_message="Incorrect.")

def render_content_feedback_form(goal):
    st.header("🌟 Value Your Feedback!") 
    with st.form("feedback_form"):
        st.info("Your feedback helps us improve the learning experience.\nPlease take a moment to share your thoughts.")

        col1, col2 = st.columns([1, 3])
        col1.write("Clarity of Content")
        clarity = col2.feedback("stars", key="clarity")

        col1, col2 = st.columns([1, 3])
        col1.write("Relevance to Goals")
        relevance = col2.feedback("stars", key="relevance")

        col1, col2 = st.columns([1, 3])
        col1.write("Depth of Content")
        depth = col2.feedback("stars", key="depth")

        col1, col2 = st.columns([1, 3])
        col1.write("Engagement Level")
        engagement = col2.feedback("faces", key="engagement")

        additional_comments = st.text_area("Additional Comments", max_chars=500)
        feedback_data = {
            "clarity": clarity,
            "relevance": relevance,
            "depth": depth,
            "engagement": engagement,
            "additional_comments": additional_comments
        }
        submitted = st.form_submit_button("Submit Feedback", on_click=update_learner_profile_with_feedback, kwargs={"feedback_data": feedback_data, "goal": goal})
        if submitted:
            st.success("Thank you for your feedback!")

def update_learner_profile_with_feedback(goal, feedback_data, session_information=""):
    st.toast("Updating your profile...")
    learner_interactions = build_structured_learner_interactions(feedback_data)
    if session_information != "":
        session_information = copy.deepcopy(session_information)
        session_information["if_learned"] = True
        session_information["selected_variant"] = get_selected_learning_approach_variant(goal, render_selector=False)
        session_information["quiz_performance"] = build_quiz_performance_payload()
        session_information["session_behavior"] = build_session_behavior_payload()
        selected_sid = st.session_state["selected_session_id"]
        goal["learning_path"][selected_sid]["quiz_performance"] = session_information["quiz_performance"]
        wrong_questions = collect_wrong_question_records()
        quiz_history = list(goal["learning_path"][selected_sid].get("quiz_history", []) or [])
        quiz_history.append(
            {
                "timestamp": time.time(),
                "quiz_performance": copy.deepcopy(session_information["quiz_performance"]),
                "wrong_questions": copy.deepcopy(wrong_questions),
            }
        )
        goal["learning_path"][selected_sid]["quiz_history"] = quiz_history[-5:]
        goal["learning_path"][selected_sid]["previous_wrong_questions"] = copy.deepcopy(wrong_questions)
    new_learner_profile = update_learner_profile(goal["learner_profile"], learner_interactions, session_information=session_information)
    if new_learner_profile is None:
        st.error("Failed to update learner profile. Please try again.")
        return False
    else:
        goal["learner_profile"] = new_learner_profile
        st.session_state["learner_profile"] = new_learner_profile
        if (
            session_information != ""
            and not session_information["quiz_performance"].get("mastery_achieved", False)
        ):
            apply_mastery_gap_remediation_to_learning_path(
                goal,
                st.session_state["selected_session_id"],
                wrong_questions=goal["learning_path"][st.session_state["selected_session_id"]].get("previous_wrong_questions", []),
            )
            session_uid = get_current_session_uid()
            stale_keys = [
                key for key in list(st.session_state.get("document_caches", {}).keys())
                if str(key).startswith(session_uid)
            ]
            for key in stale_keys:
                st.session_state["document_caches"].pop(key, None)
        if session_information != "":
            sync_remediation_status_after_profile_update(goal, st.session_state["selected_session_id"])
            try:
                goal_id = goal.get("id")
                overall_progress = int(new_learner_profile.get("cognitive_status", {}).get("overall_progress", 0))
                if goal_id is not None:
                    learned_history = st.session_state.setdefault("learned_skills_history", {})
                    history = learned_history.setdefault(goal_id, [])
                    if not history or history[-1] != overall_progress:
                        history.append(overall_progress)
            except Exception:
                pass
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("Profile updated.")
        return True

def load_knowledge_point_content(file_path):
    try:
        resolved_path = Path(file_path)
        knowledge_document = json.loads(resolved_path.read_text(encoding="utf-8"))
        return knowledge_document
    except FileNotFoundError:
        st.error("Knowledge document not found.")
        return None

render_learning_content()

