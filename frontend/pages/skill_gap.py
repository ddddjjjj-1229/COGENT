import streamlit as st

from components.brand import render_brand_hero
from components.gap_identification import (
    all_skill_diagnostics_completed,
    render_identified_skill_gap,
    render_identifying_skill_gap,
    render_initial_learning_approach_assessment,
    render_skill_verification_summary,
)
from utils.request_api import create_learner_profile
from utils.state import add_new_goal, save_persistent_state


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


def render_skill_gap():
    if "to_add_goal" not in st.session_state:
        st.info("The session has expired. Please restart from onboarding.")
        st.switch_page("pages/onboarding.py")
        return

    goal = st.session_state["to_add_goal"]
    if not goal.get("learning_goal") or not (goal.get("learner_information") or st.session_state.get("learner_information")):
        st.switch_page("pages/onboarding.py")
        return

    _, center, _ = st.columns([1, 5, 1])
    with center:
        render_brand_hero(
            page_label="Capability mapping",
            title="COGENT verifies what is missing before it plans what comes next.",
            description="Review inferred skill gaps, complete the required diagnostics, and confirm the initial learning-approach signal before the pathway is scheduled.",
            chips=[
                "gap inference",
                "diagnostic checks",
                "skill verification",
                "approach baseline",
            ],
            metrics=[
                {
                    "value": "Gap review",
                    "label": "visible reasoning",
                    "detail": "The capability map stays visible instead of being hidden behind the schedule.",
                },
                {
                    "value": "Diagnostics",
                    "label": "evidence gate",
                    "detail": "Required checks keep the learner profile grounded in observable responses.",
                },
                {
                    "value": "Approach baseline",
                    "label": "planning context",
                    "detail": "Scheduling starts only after the first preference signal is in place.",
                },
            ],
            note="Scheduling starts only after the required capability and preference signals are in place.",
        )

        if not goal.get("skill_gaps"):
            render_identifying_skill_gap(goal)
            return

        goal["skill_gaps"] = normalize_skill_gaps(goal["skill_gaps"])
        num_skills = len(goal["skill_gaps"])
        num_gaps = sum(
            1 for skill in goal["skill_gaps"]
            if isinstance(skill, dict) and skill.get("is_gap")
        )
        st.info(f"There are {num_skills} skills in total, with {num_gaps} skill gaps identified.")

        render_identified_skill_gap(goal)
        diagnostics_ready = all_skill_diagnostics_completed(goal)
        skill_verification_ready = False
        if diagnostics_ready:
            st.divider()
            skill_verification_ready = render_skill_verification_summary(goal)
        else:
            st.warning("Please finish the required skill diagnostic assessments before moving to skill confirmation.")

        initial_learning_approach_ready = False
        if skill_verification_ready:
            st.divider()
            initial_learning_approach_ready = render_initial_learning_approach_assessment(goal)

        if_ready = (
            len(goal["skill_gaps"]) > 0
            and diagnostics_ready
            and skill_verification_ready
            and initial_learning_approach_ready
        )
        if diagnostics_ready and not skill_verification_ready:
            st.warning("Please confirm the verified skill status before moving to the learning-approach assessment.")
        if skill_verification_ready and not initial_learning_approach_ready:
            st.warning("Please complete the initial learning-approach assessment before scheduling the learning path.")

        _, continue_button_col = st.columns([1, 0.27])
        with continue_button_col:
            if st.button("Schedule pathway", type="primary", disabled=not if_ready):
                if not goal.get("learner_profile"):
                    with st.spinner("Creating your profile ..."):
                        learner_profile = create_learner_profile(
                            goal["learning_goal"],
                            goal.get("learner_information") or st.session_state["learner_information"],
                            goal["skill_gaps"],
                            initial_learning_approach_state=goal.get("initial_learning_approach_state", {}),
                        )
                        if learner_profile:
                            goal["learner_profile"] = learner_profile

                new_id = add_new_goal(**goal)
                st.session_state["selected_goal_id"] = new_id
                st.session_state["if_complete_onboarding"] = True
                save_persistent_state()
                st.switch_page("pages/learning_path.py")


render_skill_gap()
