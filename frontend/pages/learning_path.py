import math
import streamlit as st
from components.skill_info import render_skill_info
from components.brand import render_brand_hero, render_info_panel
from utils.request_api import schedule_learning_path, reschedule_learning_path
from utils.state import initialize_session_state, save_persistent_state, get_selected_goal, normalize_goal_record


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


def get_session_mastery_status(goal, session):
    desired_outcomes = session.get("desired_outcome_when_completed", [])
    mastery_evidence = goal.get("learner_profile", {}).get("cognitive_status", {}).get("mastery_evidence", [])
    desired_skill_names = {str(item.get("name", "")).strip().lower() for item in desired_outcomes}
    latest_by_skill = _latest_mastery_evidence_by_skill(mastery_evidence)
    related_evidence = [latest_by_skill[name] for name in desired_skill_names if name in latest_by_skill]
    if not related_evidence:
        return None, []
    if all(item.get("mastery_achieved", False) for item in related_evidence):
        return "mastered", related_evidence
    return "needs_reinforcement", related_evidence


def build_mastery_gap_feedback(goal):
    feedback_items = []
    for session in goal.get("learning_path", []) or []:
        status, related_evidence = get_session_mastery_status(goal, session)
        if status != "needs_reinforcement":
            continue
        feedback_items.append(
            {
                "session_id": session.get("id", ""),
                "session_title": session.get("title", ""),
                "recommended_action": "add reinforcement or remediation before advancing too quickly",
                "weak_skills": [
                    {
                        "skill_name": item.get("skill_name", ""),
                        "overall_score": item.get("overall_score", 0),
                        "mastery_threshold": item.get("mastery_threshold", 80),
                        "mastery_gap": item.get("mastery_gap", 0),
                    }
                    for item in related_evidence
                ],
            }
        )
    summary = "No mastery gaps detected from completed session quizzes."
    if feedback_items:
        summary = "Some completed sessions contain quiz evidence showing certain skills still need reinforcement."
    return {
        "summary": summary,
        "mastery_gap_feedback": feedback_items,
    }

def render_learning_path():
    try:
        initialize_session_state()
    except Exception:
        pass
    if not st.session_state.get("if_complete_onboarding"):
        st.switch_page("pages/onboarding.py")

    if "goals" not in st.session_state or not st.session_state.get("goals"):
        st.switch_page("pages/onboarding.py")
        return
    goal = get_selected_goal()
    if not goal:
        st.switch_page("pages/onboarding.py")
        return
    normalize_goal_record(goal)
    save_persistent_state()
    if not goal.get("learning_goal") or not (goal.get("learner_information") or st.session_state.get("learner_information")):
        st.switch_page("pages/onboarding.py")
    else:
        if not (goal.get("skill_gaps") or []):
            st.switch_page("pages/skill_gap.py")

    learner_profile = goal.get("learner_profile", {}) or {}
    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    learning_preferences = learner_profile.get("learning_preferences", {}) or {}
    approach_state = learning_preferences.get("learning_approach_state", {}) or {}
    learning_path = goal.get("learning_path") or []
    learned_sessions = sum(1 for session in learning_path if session.get("if_learned"))
    total_sessions = len(learning_path)
    mastery_gap_feedback = build_mastery_gap_feedback(goal)
    render_brand_hero(
        page_label="Adaptive pathway",
        title="The COGENT path stays aligned with evidence from each session.",
        description="Schedule, inspect, and resume sessions. Mastery evidence and learning-approach signals can reshape what comes next instead of leaving the plan static.",
        chips=[
            "session sequencing",
            "mastery evidence",
            "reinforcement routing",
            "preference-aware delivery",
        ],
        metrics=[
            {
                "value": f"{learned_sessions}/{total_sessions}" if total_sessions else "0/0",
                "label": "completed sessions",
                "detail": "Progress across the active pathway.",
            },
            {
                "value": str(len(cognitive_status.get("mastered_skills", []) or [])),
                "label": "mastered skills",
                "detail": "Skills already confirmed in the current profile.",
            },
            {
                "value": str(approach_state.get("dominant_type", "pending")).title(),
                "label": "current approach signal",
                "detail": "The strongest learning-approach pattern currently inferred.",
            },
            {
                "value": str(len(mastery_gap_feedback.get("mastery_gap_feedback", []))),
                "label": "reinforcement alerts",
                "detail": "Completed sessions still showing weak mastery evidence.",
            },
        ],
        note="Session sequencing, preference signals, and reinforcement cues stay visible throughout the pathway.",
    )

    st.markdown("""
        <style>
        .card-header {
            color: #1f1d18;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 1.05rem;
        }
        </style>
    """, unsafe_allow_html=True)
    if not learning_path:
        with st.spinner('Scheduling Learning Path ...'):
            scheduled_path = schedule_learning_path(goal.get("learner_profile") or {}, session_count=8)
            if not scheduled_path:
                st.error(st.session_state.get("last_learning_path_error", "Learning path scheduling failed."))
                return
            goal["learning_path"] = scheduled_path
            save_persistent_state()
            st.toast("Learning path scheduled.")
            st.rerun()
    else:
        render_overall_information(goal)
        render_learning_sessions(goal)


def render_overall_information(goal):
    learning_path = goal.get("learning_path") or []
    with st.container(border=True):
        render_info_panel(
            label="Active objective",
            title=goal["learning_goal"],
            body="This goal is driving the current sequence of sessions. Update it later from Goals if the objective changes.",
        )
        learned_sessions = sum(1 for s in learning_path if s.get("if_learned"))
        total_sessions = len(learning_path)
        mastered_skills = goal.get("learner_profile", {}).get("cognitive_status", {}).get("mastered_skills", [])
        in_progress_skills = goal.get("learner_profile", {}).get("cognitive_status", {}).get("in_progress_skills", [])
        if total_sessions == 0:
            st.warning("No learning sessions found.")
            progress = 0
        else:
            progress = int((learned_sessions / total_sessions) * 100)
        metric_cols = st.columns(3)
        metric_cols[0].metric("Completed sessions", f"{learned_sessions}/{total_sessions}")
        metric_cols[1].metric("Mastered skills", len(mastered_skills))
        metric_cols[2].metric("In progress", len(in_progress_skills))
        st.write("#### Progress")
        with st.container():
            st.progress(progress)
            st.write(f"{learned_sessions}/{total_sessions} sessions completed ({progress}%)")

            if learned_sessions == total_sessions:
                st.success("All sessions in the current pathway are complete.")
                st.balloons()
            else:
                st.info("The pathway is still active. Progress and quiz evidence will continue to shape what comes next.")
        with st.expander("View skill details", expanded=False):
            render_skill_info(goal["learner_profile"])

def render_learning_sessions(goal):
    st.write("#### Session queue")
    learning_path = goal.get("learning_path") or []
    total_sessions = len(learning_path)
    with st.expander("Adjust pathway", expanded=False):
        st.info("Change the expected number of sessions and let COGENT rebuild the path around the latest evidence.")
        mastery_gap_feedback = build_mastery_gap_feedback(goal)
        if mastery_gap_feedback.get("mastery_gap_feedback"):
            st.warning("The system detected some completed sessions whose quiz mastery evidence suggests reinforcement is still needed.")
            for item in mastery_gap_feedback["mastery_gap_feedback"]:
                weak_skill_names = ", ".join(skill.get("skill_name", "") for skill in item.get("weak_skills", []))
                st.write(f"- {item.get('session_title', item.get('session_id', 'Session'))}: {weak_skill_names}")
        max_session_value = max(10, int(total_sessions))
        expected_session_count = st.number_input(
            "Expected sessions",
            min_value=0,
            max_value=max_session_value,
            value=min(int(total_sessions), max_session_value),
        )
        st.session_state["expected_session_count"] = expected_session_count
        try:
            save_persistent_state()
        except Exception:
            pass
        if st.button("Reschedule pathway", type="primary"):
            st.session_state["if_rescheduling_learning_path"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
        if st.session_state.get("if_rescheduling_learning_path"):
            with st.spinner('Re-scheduling Learning Path ...'):
                updated_path = reschedule_learning_path(
                    learning_path,
                    goal.get("learner_profile") or {},
                    expected_session_count,
                    other_feedback=mastery_gap_feedback,
                )
                if not updated_path:
                    st.session_state["if_rescheduling_learning_path"] = False
                    st.error(st.session_state.get("last_learning_path_error", "Learning path rescheduling failed."))
                    return
                goal["learning_path"] = updated_path
                st.session_state["if_rescheduling_learning_path"] = False
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.toast("Learning path updated.")
                st.rerun()
    save_persistent_state()
    columns_spec = 2
    learning_path = goal.get("learning_path") or []
    num_columns = math.ceil(len(learning_path) / columns_spec)
    if num_columns == 0:
        st.info("No sessions are available for this goal yet.")
        return
    columns_list = [st.columns(columns_spec, gap="large") for _ in range(num_columns)]
    for sid, session in enumerate(learning_path):
        session_column = columns_list[sid // columns_spec]
        with session_column[sid % columns_spec]:
            with st.container(border=True):
                text_color = "#5ecc6b" if session["if_learned"] else "#fc7474"
                mastery_status, related_evidence = get_session_mastery_status(goal, session)

                st.markdown(f"<div class='card'><div class='card-header' style='color: {text_color};'>{sid+1}: {session['title']}</div>", unsafe_allow_html=True)
                if session.get("is_remediation"):
                    st.caption("Reinforcement session automatically inserted after weak quiz mastery.")
                if mastery_status == "needs_reinforcement":
                    st.caption("Needs reinforcement based on chapter quiz mastery evidence.")
                elif mastery_status == "mastered":
                    st.caption("Mastery evidence available for this session.")

                with st.expander("View Session Details", expanded=False):
                    st.info(session["abstract"])
                    if session.get("difficulty_adjustment"):
                        st.write(f"**Difficulty Adjustment:** {session.get('difficulty_adjustment')}")
                    if session.get("reinforcement_targets"):
                        st.write("**Reinforcement Targets:**")
                        for skill_name in session.get("reinforcement_targets", []):
                            st.write(f"- {skill_name}")
                    if session.get("remediation_actions"):
                        st.write("**Remediation Actions:**")
                        for action in session.get("remediation_actions", []):
                            st.write(f"- {action}")
                    st.write("**Associated Skills & Desired Proficiency:**")
                    for skill_outcome in session["desired_outcome_when_completed"]:
                        st.write(f"- {skill_outcome['name']} (`{skill_outcome['level']}`)")
                    quiz_performance = session.get("quiz_performance", {})
                    if quiz_performance and int(quiz_performance.get("total_count", 0)) > 0:
                        st.write("**Latest Chapter Quiz Result:**")
                        st.write(
                            f"- Score: {quiz_performance.get('correct_count', 0)}/"
                            f"{quiz_performance.get('total_count', 0)} "
                            f"({quiz_performance.get('overall_score', 0)}%)"
                        )
                        st.write(
                            f"- Mastery threshold: {quiz_performance.get('mastery_threshold', 80)}% | "
                            f"{'Reached' if quiz_performance.get('mastery_achieved', False) else 'Not reached'}"
                        )
                    if mastery_status == "needs_reinforcement":
                        st.warning("This session has quiz evidence showing some related knowledge is not yet fully mastered.")
                        for item in related_evidence:
                            st.write(
                                f"- {item.get('skill_name', 'Unknown skill')}: "
                                f"{item.get('overall_score', 0)}% / threshold {item.get('mastery_threshold', 80)}%"
                            )
                    elif mastery_status == "mastered":
                        st.success("Quiz evidence suggests the targeted knowledge in this session has reached the mastery threshold.")

                col1, col2 = st.columns([5, 3])
                with col1:
                    if_learned_key = f"if_learned_{session['id']}"
                    old_if_learned = session["if_learned"]
                    session_status_hint = "In progress" if not session["if_learned"] else "Completed"
                    session_if_learned = st.toggle(session_status_hint, value=session["if_learned"], key=if_learned_key, disabled=True)
                    goal["learning_path"][sid]["if_learned"] = session_if_learned
                    save_persistent_state()
                    if session_if_learned != old_if_learned:
                        st.rerun()

                with col2:
                    if not session["if_learned"]:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Open session", key=start_key, use_container_width=True, type="primary", icon=":material/local_library:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Session Studio"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")
                    else:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Review session", key=start_key, use_container_width=True, type="secondary", icon=":material/done_outline:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Session Studio"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")


render_learning_path()
