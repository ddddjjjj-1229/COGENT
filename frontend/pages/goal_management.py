import streamlit as st
from html import escape

from components.brand import render_brand_hero
from components.gap_identification import (
    all_skill_diagnostics_completed,
    render_identified_skill_gap,
    render_identifying_skill_gap,
    render_initial_learning_approach_assessment,
    render_skill_verification_summary,
)
from components.goal_refinement import render_goal_refinement
from components.skill_info import render_skill_info
from utils.learner_context import extract_attachment_context, merge_learner_information
from utils.request_api import create_learner_profile
from utils.state import (
    add_new_goal,
    change_selected_goal_id,
    index_goal_by_id,
    reset_to_add_goal,
    save_persistent_state,
)


def ensure_goal_state():
    st.session_state.setdefault(
        "to_add_goal",
        {
            "learning_goal": "",
            "learner_information": "",
            "skill_requirements": {},
            "skill_gaps": [],
            "learner_profile": None,
            "learning_approach_assessment": {},
            "initial_learning_approach_state": {},
            "skill_verification_confirmed": False,
        },
    )
    st.session_state.setdefault("goals", [])
    st.session_state.setdefault("if_refining_learning_goal", False)
    st.session_state.setdefault("if_show_skill_gap_results_in_dialog", False)


def normalize_skill_gaps(raw_data):
    if isinstance(raw_data, dict) and "skill_gaps" in raw_data:
        raw_data = raw_data["skill_gaps"]

    normalized = []
    if isinstance(raw_data, list):
        for item in raw_data:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"name": str(item), "is_gap": True})
    elif isinstance(raw_data, dict):
        for name, value in raw_data.items():
            if isinstance(value, dict):
                normalized.append({"name": name, **value})
            else:
                normalized.append({"name": name, "is_gap": True, "current_level": str(value)})
    return normalized


def render_goal_management():
    ensure_goal_state()
    goals = [goal for goal in st.session_state.get("goals", []) if not goal.get("is_deleted")]
    active_goal_id = st.session_state.get("selected_goal_id")
    active_goal = next((goal for goal in goals if goal.get("id") == active_goal_id), None)

    render_brand_hero(
        page_label="Goal workspace",
        title="Use COGENT goals as a living studio for parallel learning tracks.",
        description="Shape a new objective, keep one goal active, and review existing tracks through progress, preference signals, and mastery evidence instead of treating goals as plain text entries.",
        chips=[
            "goal refinement",
            "active track switching",
            "evidence-aware planning",
            "profile continuity",
        ],
        metrics=[
            {
                "value": str(len(goals)),
                "label": "stored tracks",
                "detail": "Reusable goals that can be reactivated without losing their adaptive context.",
            },
            {
                "value": active_goal.get("learning_goal", "No active goal") if active_goal else "No active goal",
                "label": "current focus",
                "detail": "The learning path, session studio, and analytics pages follow this goal.",
            },
        ],
        note="Keep active tracks, stored goals, and planning context in one place.",
    )

    render_goal_workspace()
    st.divider()
    render_existing_goals(goals)


def render_goal_workspace():
    left_col, right_col = st.columns([1.42, 0.88], gap="large")
    with left_col:
        render_add_new_goal()
    with right_col:
        render_goal_process_panel()


def render_add_new_goal():
    to_add_goal = st.session_state["to_add_goal"]
    with st.container(border=True):
        st.markdown(
            """
            <div class="cogent-form-lead">
                <p class="cogent-panel-label">Shape the next track</p>
                <h3>Start from an objective worth optimizing</h3>
                <p>Use refinement first if the request is broad. Then create the track and move it through capability mapping, preference baselining, and pathway scheduling.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        new_learning_goal = st.text_area(
            "Enter your new goal",
            to_add_goal["learning_goal"],
            key="new_learning_goal",
            placeholder="Example: master advanced data mining methods for research-driven model development",
            height=160,
        )
        to_add_goal["learning_goal"] = new_learning_goal

        existing_context = st.session_state.get("learner_information", "") or ""
        if existing_context:
            st.markdown(
                f"""
                <div class="cogent-goal-summary" style="margin-bottom:0.85rem;">
                    Existing learner context will be reused for this goal. Add only the new details that should be merged in.
                </div>
                """,
                unsafe_allow_html=True,
            )

        supplemental_info = st.text_area(
            "Optional: add more learner context for this goal",
            value=st.session_state.get("new_goal_learner_information_text", ""),
            key="new_goal_learner_information_text",
            height=130,
            placeholder="Example: now focusing on fast practical execution, already familiar with SQL, recently worked on recommendation models",
        )
        uploaded_files = st.file_uploader(
            "Optional attachments for this goal",
            type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md"],
            accept_multiple_files=True,
            key="new_goal_attachment_uploader",
            help="PDF text will be merged automatically. Image attachments are recorded as supplemental context.",
        )
        if uploaded_files:
            st.caption("Attachments added to this goal:")
            for uploaded_file in uploaded_files:
                st.write(f"- {uploaded_file.name}")

        refine_col, clear_col, hint_col, add_col = st.columns([1.15, 0.7, 2.3, 1.05])
        render_goal_refinement(to_add_goal, refine_col, hint_col)

        with clear_col:
            if st.button("Clear", key="clear_goal"):
                reset_to_add_goal()
                st.session_state.pop("new_goal_learner_information_text", None)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()

        with add_col:
            if st.button("Create track", type="primary", icon=":material/add:", use_container_width=True):
                if new_learning_goal:
                    attachment_information, attachment_summaries = extract_attachment_context(uploaded_files)
                    merged_information = merge_learner_information(
                        st.session_state.get("learner_information", ""),
                        supplemental_info,
                        attachment_information,
                    )
                    st.session_state["learner_information"] = merged_information
                    to_add_goal["learner_information"] = merged_information
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    if attachment_summaries:
                        st.toast("Attachments added to learner context.")
                    render_skill_gap_dialog()
                else:
                    hint_col.warning("Please enter a goal before creating the track.")

    if st.session_state["if_show_skill_gap_results_in_dialog"]:
        render_skill_gap_dialog()


def render_goal_process_panel():
    st.markdown(
        """
        <section class="cogent-process-card">
            <p class="cogent-panel-label">Planning sequence</p>
            <h3>Planning is gated by evidence, not by a single click</h3>
            <div class="cogent-process-step-list">
                <div class="cogent-process-step">
                    <span class="cogent-process-index">01</span>
                    <div>
                        <h4>Refine the objective</h4>
                        <p>Broad requests can be tightened before the planning pipeline starts.</p>
                    </div>
                </div>
                <div class="cogent-process-step">
                    <span class="cogent-process-index">02</span>
                    <div>
                        <h4>Verify capability gaps</h4>
                        <p>Skill evidence stays visible so the learner sees what the path is reacting to.</p>
                    </div>
                </div>
                <div class="cogent-process-step">
                    <span class="cogent-process-index">03</span>
                    <div>
                        <h4>Lock the first approach signal</h4>
                        <p>The initial learning-approach baseline becomes part of the planning context.</p>
                    </div>
                </div>
                <div class="cogent-process-step">
                    <span class="cogent-process-index">04</span>
                    <div>
                        <h4>Route reinforcement later</h4>
                        <p>Quiz evidence can insert remediation back into the pathway when mastery lags.</p>
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_existing_goals(goals):
    st.subheader("Existing tracks")
    if not goals:
        st.info("No saved tracks yet. Create one above to begin.")
        return

    for goal_index, goal in enumerate(goals):
        render_goal_card(goal_index, goal)
        if goal_index < len(goals) - 1:
            st.markdown("<div class='cogent-mini-divider'></div>", unsafe_allow_html=True)


def render_goal_card(goal_index, goal):
    learner_profile = goal.get("learner_profile") if isinstance(goal, dict) else {}
    learner_profile = learner_profile if isinstance(learner_profile, dict) else {}
    cognitive_status = learner_profile.get("cognitive_status", {}) if isinstance(learner_profile, dict) else {}
    learning_preferences = learner_profile.get("learning_preferences", {}) if isinstance(learner_profile, dict) else {}
    approach_state = learning_preferences.get("learning_approach_state", {}) if isinstance(learning_preferences, dict) else {}

    overall_progress = int(cognitive_status.get("overall_progress", 0) or 0)
    mastered_skills = cognitive_status.get("mastered_skills", []) or []
    in_progress_skills = cognitive_status.get("in_progress_skills", []) or []
    current_focus = str(approach_state.get("dominant_type", "pending")).title()
    confidence = str(approach_state.get("confidence", "pending")).title()
    total_sessions = len(goal.get("learning_path", []) or [])
    completed_sessions = sum(1 for session in goal.get("learning_path", []) or [] if session.get("if_learned"))
    is_active = st.session_state.get("selected_goal_id") == goal.get("id")

    status_class = "cogent-goal-status--active" if is_active else "cogent-goal-status--idle"
    status_text = "Active" if is_active else "Stored"
    goal_title = str(goal.get("learning_goal", "Untitled goal")).strip() or "Untitled goal"

    with st.container(border=True):
        st.markdown(
            f"""
            <section class="cogent-goal-summary-card">
                <div class="cogent-goal-head">
                    <div>
                        <p class="cogent-goal-label">Track {goal_index + 1:02d}</p>
                        <h3>{escape(goal_title)}</h3>
                    </div>
                    <span class="cogent-goal-status {status_class}">{status_text}</span>
                </div>
                <div class="cogent-goal-summary">
                    This track keeps its progress, preference signal, and mastery evidence together.
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )

        st.progress(overall_progress / 100 if overall_progress else 0)
        st.caption(f"{overall_progress}% progress | {completed_sessions}/{total_sessions or 0} sessions completed")

        metric_cols = st.columns(4)
        metric_cols[0].metric("Mastered", len(mastered_skills))
        metric_cols[1].metric("In progress", len(in_progress_skills))
        metric_cols[2].metric("Approach", current_focus)
        metric_cols[3].metric("Confidence", confidence)

        tag_values = [
            f"{total_sessions or 0} planned sessions",
            f"{len(goal.get('skill_gaps', []) or [])} mapped gaps",
        ]
        if approach_state:
            tag_values.append(f"{current_focus} preference signal")
        st.markdown(
            "<div class='cogent-tag-row'>"
            + "".join(f"<span class='cogent-tag'>{escape(str(tag))}</span>" for tag in tag_values)
            + "</div>",
            unsafe_allow_html=True,
        )

        action_cols = st.columns([1.25, 1, 1, 1.1])
        with action_cols[0]:
            if not is_active:
                if st.button("Use this track", key=f"set_{goal['id']}", type="secondary", use_container_width=True):
                    st.session_state["selected_goal_id"] = goal["id"]
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    change_selected_goal_id(goal["id"])
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.rerun()
            else:
                st.markdown(
                    "<div class='cogent-tag' style='margin-top:0.32rem;'>Active goal</div>",
                    unsafe_allow_html=True,
                )

        with action_cols[1]:
            if st.button("Edit goal", key=f"edit_toggle_{goal['id']}", use_container_width=True):
                st.session_state[f"editing_goal_{goal['id']}"] = not st.session_state.get(f"editing_goal_{goal['id']}", False)
                st.rerun()

        with action_cols[2]:
            if st.button("Delete", key=f"delete_{goal['id']}", type="secondary", use_container_width=True):
                goal_index_in_state = index_goal_by_id(goal["id"])
                st.session_state.goals[goal_index_in_state]["is_deleted"] = True
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()

        with action_cols[3]:
            if goal.get("learning_path"):
                st.markdown(
                    f"<div class='cogent-tag' style='justify-content:center; margin-top:0.32rem;'>{completed_sessions}/{total_sessions} sessions complete</div>",
                    unsafe_allow_html=True,
                )

        if st.session_state.get(f"editing_goal_{goal['id']}", False):
            edited_goal = st.text_area(
                "Update goal wording",
                value=goal_title,
                key=f"edited_goal_text_{goal['id']}",
                height=120,
            )
            save_cols = st.columns([1, 1, 4])
            with save_cols[0]:
                if st.button("Save", key=f"save_{goal['id']}", type="primary", use_container_width=True):
                    goal["learning_goal"] = edited_goal
                    try:
                        save_persistent_state()
                    except Exception:
                        pass
                    st.session_state[f"editing_goal_{goal['id']}"] = False
                    st.rerun()
            with save_cols[1]:
                if st.button("Cancel", key=f"cancel_edit_{goal['id']}", use_container_width=True):
                    st.session_state[f"editing_goal_{goal['id']}"] = False
                    st.rerun()

        with st.expander("Skill coverage and profile signals", expanded=False):
            render_skill_info(goal.get("learner_profile"))


@st.dialog("Capability map", width="large")
def render_skill_gap_dialog():
    to_add_goal = st.session_state["to_add_goal"]
    st.write("Review and confirm the mapped capability gaps before creating the new track.")

    skill_gaps_list = normalize_skill_gaps(to_add_goal.get("skill_gaps", []))
    to_add_goal["skill_gaps"] = skill_gaps_list
    num_skills = len(skill_gaps_list)
    num_gaps = sum(1 for skill in skill_gaps_list if isinstance(skill, dict) and skill.get("is_gap", False))
    st.info(f"There are {num_skills} skills in total, with {num_gaps} skill gaps identified.")

    if not skill_gaps_list:
        st.session_state["if_show_skill_gap_results_in_dialog"] = True
        try:
            save_persistent_state()
        except Exception:
            pass
        render_identifying_skill_gap(to_add_goal)
        return

    st.session_state["if_show_skill_gap_results_in_dialog"] = False
    try:
        save_persistent_state()
    except Exception:
        pass

    render_identified_skill_gap(to_add_goal)
    diagnostics_ready = all_skill_diagnostics_completed(to_add_goal)
    skill_verification_ready = False
    if diagnostics_ready:
        st.divider()
        skill_verification_ready = render_skill_verification_summary(to_add_goal)
    else:
        st.warning("Please finish the required skill diagnostic assessments before moving to skill confirmation.")

    initial_learning_approach_ready = False
    if skill_verification_ready:
        st.divider()
        initial_learning_approach_ready = render_initial_learning_approach_assessment(to_add_goal)

    schedule_ready = (
        len(skill_gaps_list) > 0
        and diagnostics_ready
        and skill_verification_ready
        and initial_learning_approach_ready
    )
    if diagnostics_ready and not skill_verification_ready:
        st.warning("Please confirm the verified skill status before moving to the learning-approach assessment.")
    if skill_verification_ready and not initial_learning_approach_ready:
        st.warning("Please complete the initial learning-approach assessment before scheduling the learning path.")

    if st.button("Schedule pathway", type="primary", disabled=not schedule_ready):
        if skill_gaps_list and not to_add_goal.get("learner_profile"):
            with st.spinner("Creating your profile ..."):
                learner_profile = create_learner_profile(
                    to_add_goal["learning_goal"],
                    to_add_goal.get("learner_information") or st.session_state.get("learner_information", ""),
                    skill_gaps_list,
                    initial_learning_approach_state=to_add_goal.get("initial_learning_approach_state", {}),
                )
                if learner_profile is None:
                    st.rerun()
                to_add_goal["learner_profile"] = learner_profile
                st.toast("Profile created.")

        valid_keys = [
            "learning_goal",
            "learner_information",
            "skill_requirements",
            "skill_gaps",
            "learner_profile",
            "learning_approach_assessment",
            "initial_learning_approach_state",
            "learning_approach_assessment_answers",
            "skill_verification_confirmed",
        ]
        clean_goal_data = {key: to_add_goal[key] for key in valid_keys if key in to_add_goal}
        new_goal_id = add_new_goal(**clean_goal_data)

        st.session_state["selected_goal_id"] = new_goal_id
        st.session_state["if_complete_onboarding"] = True
        st.session_state["selected_page"] = "Learning Path"
        st.session_state.pop("new_goal_learner_information_text", None)
        try:
            save_persistent_state()
        except Exception:
            pass
        st.switch_page("pages/learning_path.py")


render_goal_management()
