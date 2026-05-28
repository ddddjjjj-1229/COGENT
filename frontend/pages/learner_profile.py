import streamlit as st
from utils.request_api import create_learner_profile, update_learner_profile
from components.skill_info import render_skill_info
from components.brand import render_brand_hero
from utils.learner_context import extract_attachment_context, merge_learner_information
from utils.state import initialize_session_state, save_persistent_state, get_selected_goal


def render_learner_profile():
    try:
        initialize_session_state()
    except Exception:
        pass
    if "goals" not in st.session_state or not st.session_state.get("goals"):
        st.warning("No active goal is loaded.")
        return
    goal = get_selected_goal()
    if not goal:
        st.warning("No valid active goal is selected.")
        return
    learner_profile = goal.get("learner_profile", {}) or {}
    learning_preferences = learner_profile.get("learning_preferences", {}) or {}
    approach_state = learning_preferences.get("learning_approach_state", {}) or {}

    render_brand_hero(
        page_label="Learner signals",
        title="COGENT keeps the profile visible so every teaching decision has context.",
        description="Review background, progress, preferences, and behavioral patterns that influence how the pathway is currently being shaped.",
        chips=[
            "learner context",
            "progress signal",
            "approach evidence",
            "behavior patterns",
        ],
        metrics=[
            {
                "value": learner_profile.get("cognitive_status", {}).get("overall_progress", 0),
                "label": "overall progress",
                "detail": "The current progress state stored in the learner profile.",
            },
            {
                "value": str(approach_state.get("dominant_type", "pending")).title(),
                "label": "dominant approach",
                "detail": "The strongest learning-approach pattern currently inferred.",
            },
            {
                "value": str(len(learner_profile.get("cognitive_status", {}).get("mastered_skills", []) or [])),
                "label": "mastered skills",
                "detail": "Skills already marked as achieved in the current profile.",
            },
        ],
        note="Use these profile signals as live teaching context for the active pathway.",
    )
    if not goal["learner_profile"]:
        with st.spinner('Identifying Skill Gap ...'):
            st.info("Please complete the onboarding process to view the learner profile.")
    else:
        try:
            render_learner_profile_info(goal)
        except Exception as e:
            st.error("An error occurred while rendering the learner profile.")
            # re generate the learner profile
            with st.spinner("Re-prepare your profile ..."):
                learner_profile = create_learner_profile(
                    goal["learning_goal"],
                    goal.get("learner_information") or st.session_state.get("learner_information", ""),
                    goal["skill_gaps"],
                    st.session_state["llm_type"],
                )
            goal["learner_profile"] = learner_profile
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

def render_learner_profile_info(goal):
    st.markdown("""
        <style>
        .section {
            background-color: #f8f9fa;
            padding: 15px;
            margin: 10px 0;
            border-radius: 8px;
        }
        .progress-indicator {
            color: #28a745;
            font-weight: bold;
        }
        .skill-in-progress {
            color: #ffc107;
        }
        .skill-required {
            color: #dc3545;
        }
        </style>
    """, unsafe_allow_html=True)
    learner_profile = goal["learner_profile"]
    with st.container(border=True):
        # Learner Information
        st.markdown("#### Learner information")
        st.markdown(f"<div class='section'>{learner_profile['learner_information']}</div>", unsafe_allow_html=True)

        # Learning Goal
        st.markdown("#### Learning goal")
        st.markdown(f"<div class='section'>{learner_profile['learning_goal']}</div>", unsafe_allow_html=True)

    with st.container(border=True):
        render_cognitive_status(goal)
    with st.container(border=True):
        render_learning_preferences(goal)
    with st.container(border=True):
        render_behavioral_patterns(goal)

    render_additional_info_form(goal)


def render_cognitive_status(goal):
    learner_profile = goal["learner_profile"]
    # Cognitive Status
    st.markdown("#### Cognitive status")
    st.write("**Overall Progress:**")
    overall_progress = learner_profile.get("cognitive_status", {}).get("overall_progress", 0)
    st.progress(overall_progress)
    st.markdown(f"<p class='progress-indicator'>{overall_progress}% completed</p>", unsafe_allow_html=True)
    render_skill_info(learner_profile)

def render_learning_preferences(goal):
    learner_profile = goal["learner_profile"]
    st.markdown("#### Learning preferences")
    st.write(f"**Content Style:** {learner_profile['learning_preferences']['content_style']}")
    st.write(f"**Preferred Activity Type:** {learner_profile['learning_preferences']['activity_type']}")
    learning_approach_state = learner_profile["learning_preferences"].get("learning_approach_state")
    if learning_approach_state:
        st.write(f"**Dominant Learning Approach:** {learning_approach_state.get('dominant_type', 'unknown')}")
        st.write(f"**Confidence:** {learning_approach_state.get('confidence', 'unknown')}")
        distribution = learning_approach_state.get("distribution", {})
        if distribution:
            ranked = sorted(
                ((str(k), float(v)) for k, v in distribution.items() if str(k).strip()),
                key=lambda item: item[1],
                reverse=True,
            )
            st.write(
                f"**Approach Distribution:** "
                f"deep={distribution.get('deep', 0)}, "
                f"surface={distribution.get('surface', 0)}, "
                f"achieving={distribution.get('achieving', 0)}"
            )
            if len(ranked) >= 2:
                top_score = ranked[0][1]
                second_score = ranked[1][1]
                third_score = ranked[2][1] if len(ranked) > 2 else 0.0
                gap = top_score - second_score
                if gap < 0.15:
                    if gap < 0.10 and (top_score - third_score) < 0.20 and len(ranked) >= 3:
                        candidate_types = [item[0] for item in ranked[:3]]
                    else:
                        candidate_types = [ranked[0][0], ranked[1][0]]
                    st.warning(f"Preference is currently ambiguous. Next session may offer multiple content variants: {', '.join(candidate_types)}")
        st.caption(learning_approach_state.get("evidence_summary", ""))
        evaluations = learning_approach_state.get("latest_hypothesis_evaluations", [])
        if evaluations:
            with st.expander("Latest Hypothesis Evaluations", expanded=False):
                for item in evaluations:
                    approach_type = item.get("approach_type", "unknown")
                    weighted_score = item.get("weighted_score", 0)
                    st.write(f"**{approach_type}**")
                    st.write(f"Weighted Score: {weighted_score}")
                    metric_scores = item.get("metric_scores", {})
                    adaptive_weights = item.get("adaptive_weights", {})
                    st.write(
                        "Metrics: "
                        f"C_history={metric_scores.get('C_history', 0)}, "
                        f"C_behavior_fit={metric_scores.get('C_behavior_fit', 0)}, "
                        f"C_transition_plausibility={metric_scores.get('C_transition_plausibility', 0)}, "
                        f"C_context_adjusted_fit={metric_scores.get('C_context_adjusted_fit', 0)}"
                    )
                    st.write(
                        "Weights: "
                        f"C_history={adaptive_weights.get('C_history', 0)}, "
                        f"C_behavior_fit={adaptive_weights.get('C_behavior_fit', 0)}, "
                        f"C_transition_plausibility={adaptive_weights.get('C_transition_plausibility', 0)}, "
                        f"C_context_adjusted_fit={adaptive_weights.get('C_context_adjusted_fit', 0)}"
                    )
                    st.caption(item.get("rationale", ""))
        history = learning_approach_state.get("history", [])
        if history:
            with st.expander("Learning Approach History", expanded=False):
                for item in reversed(history[-10:]):
                    st.write(
                        f"- {item.get('chapter_id', 'Unknown chapter')}: "
                        f"{item.get('dominant_type', 'unknown')} "
                        f"(confidence: {item.get('confidence', 'unknown')})"
                    )
    st.write(f"**Additional Notes:**")
    st.info(learner_profile['learning_preferences']['additional_notes'])

def render_behavioral_patterns(goal):
    learner_profile = goal["learner_profile"]
    st.markdown("#### Behavioral patterns")
    st.write(f"**System Usage Frequency:**")
    st.info(learner_profile['behavioral_patterns']['system_usage_frequency'])
    st.write(f"**Session Duration and Engagement:**")
    st.info(learner_profile['behavioral_patterns']['session_duration_engagement'])
    st.write(f"**Motivational Triggers:**")
    st.info(learner_profile['behavioral_patterns']['motivational_triggers'])
    st.write(f"**Additional Notes:**")
    st.info(learner_profile['behavioral_patterns']['additional_notes'])


def render_additional_info_form(goal):
    with st.form(key="additional_info_form"):
        st.markdown("#### Value Your Feedback")
        st.info("Help us improve your learning experience by providing your feedback below.")
        st.write("How much do you agree with the current profile?")
        agreement_star = st.feedback("stars", key="agreement_star")
        st.write("Do you have any suggestions or corrections?")
        suggestions = st.text_area("Provide your suggestions here.", label_visibility="collapsed")
        st.write("Do you have any additional information to add?")
        additional_info = st.text_area("Provide any additional information or feedback here.", label_visibility="collapsed")
        uploaded_files = st.file_uploader(
            "Optional attachments",
            type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md"],
            accept_multiple_files=True,
            help="PDF text will be merged automatically. Image attachments are recorded as supplemental context.",
        )
        attachment_information, attachment_summaries = extract_attachment_context(uploaded_files)
        st.session_state["additional_info"] = {
            "agreement_star": agreement_star,
            "suggestions": suggestions,
            "additional_info": merge_learner_information(additional_info, attachment_information),
            "attachment_summaries": attachment_summaries,
        }
        try:
            save_persistent_state()
        except Exception:
            pass
        submit_button = st.form_submit_button("Update Profile", on_click=update_learner_profile_with_additional_info, 
                                              kwargs={"goal": goal, "additional_info": additional_info, }, type="primary")
        
def update_learner_profile_with_additional_info(goal, additional_info):
    additional_info = st.session_state["additional_info"]
    new_learner_profile = update_learner_profile(goal["learner_profile"], additional_info)
    if new_learner_profile is not None:
        goal["learner_profile"] = new_learner_profile
        if additional_info.get("attachment_summaries"):
            st.toast("Attachments added.")
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("Profile updated.")
    else:
        st.toast("Profile update failed. Please try again.")


render_learner_profile()
