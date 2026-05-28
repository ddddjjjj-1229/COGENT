import streamlit as st

from utils.request_api import (
    generate_learning_approach_assessment,
    identify_skill_gap,
    submit_diagnostic_assessment,
)
from utils.state import save_persistent_state


APPROACH_ORDER = ["deep", "surface", "achieving"]


def all_skill_diagnostics_completed(goal):
    for skill in goal.get("skill_gaps", []):
        if isinstance(skill, dict) and skill.get("requires_diagnostic_assessment", False):
            return False
    return True


def build_initial_learning_approach_state_from_answers(assessment, answers):
    scores = {name: 0 for name in APPROACH_ORDER}
    total = 0
    for question in assessment.get("questions", []):
        question_id = question.get("question", "")
        selected_label = answers.get(question_id)
        if not selected_label:
            continue
        total += 1
        for option in question.get("options", []):
            if option.get("label") == selected_label:
                scores[str(option.get("maps_to", ""))] += 1
                break
    if total == 0:
        return {}

    distribution = {k: round(v / total, 3) for k, v in scores.items()}
    ranked = sorted(distribution.items(), key=lambda item: item[1], reverse=True)
    top_type, top_score = ranked[0]
    second_type, second_score = ranked[1]
    margin = top_score - second_score
    confidence = "high" if margin >= 0.25 else "medium" if margin >= 0.10 else "low"
    candidate_types = [top_type]
    if margin < 0.10:
        candidate_types.append(second_type)
    return {
        "dominant_type": top_type,
        "distribution": distribution,
        "confidence": confidence,
        "evidence_summary": f"Initial learning-approach assessment currently favors {top_type}, based on the learner's pre-study scenario choices.",
        "candidate_types_for_next_session": candidate_types,
        "latest_hypothesis_evaluations": [],
        "history": [
            {
                "chapter_id": "initial_assessment",
                "dominant_type": top_type,
                "confidence": confidence,
            }
        ],
    }


def render_initial_learning_approach_assessment(goal):
    llm_type = st.session_state.get("llm_type", "gpt4o")
    learning_goal = goal.get("learning_goal", "")
    learner_information = st.session_state.get("learner_information", "")

    assessment = goal.get("learning_approach_assessment") or {}
    if not assessment:
        with st.spinner("Generating initial learning-approach assessment..."):
            assessment = generate_learning_approach_assessment(learning_goal, learner_information, llm_type)
        if assessment:
            goal["learning_approach_assessment"] = assessment
            try:
                save_persistent_state()
            except Exception:
                pass

    if not assessment:
        st.error("Failed to generate the initial learning-approach assessment.")
        return False

    st.subheader("Initial Learning Approach Assessment")
    st.info("This initial pre-test should be completed before scheduling the learning path.")

    answers = goal.get("learning_approach_assessment_answers", {})
    for idx, question in enumerate(assessment.get("questions", []), start=1):
        st.write(f"**{idx}. {question.get('question', '')}**")
        options = question.get("options", [])
        option_labels = [f"{option.get('label', '')}. {option.get('text', '')}" for option in options]
        option_by_label = {f"{option.get('label', '')}. {option.get('text', '')}": option.get("label", "") for option in options}
        radio_key = f"learning_approach_assessment::{idx}"
        current_value = None
        saved_label = answers.get(question.get("question", ""))
        for item in option_labels:
            if option_by_label[item] == saved_label:
                current_value = item
                break
        selected = st.radio(
            f"Choose one option for question {idx}",
            options=option_labels,
            index=option_labels.index(current_value) if current_value in option_labels else None,
            key=radio_key,
            label_visibility="collapsed",
        )
        if selected:
            answers[question.get("question", "")] = option_by_label[selected]
    goal["learning_approach_assessment_answers"] = answers

    if st.button("Submit Initial Learning Approach Assessment", key="submit_initial_learning_approach_assessment", type="primary"):
        if len(answers) < len(assessment.get("questions", [])):
            st.warning("Please answer all learning-approach assessment questions before continuing.")
        else:
            result = build_initial_learning_approach_state_from_answers(assessment, answers)
            goal["initial_learning_approach_state"] = result
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()

    result = goal.get("initial_learning_approach_state", {})
    if result:
        st.success(f"Initial dominant learning approach: {result.get('dominant_type', 'unknown')}")
        st.caption(result.get("evidence_summary", ""))
        return True
    return False


def render_skill_verification_summary(goal):
    skill_gaps = goal.get("skill_gaps", [])
    initial_possible_skills = [
        skill for skill in skill_gaps
        if isinstance(skill, dict)
        and (
            skill.get("mentioned_in_learner_information", False)
            or skill.get("inferred_from_learner_context", False)
            or skill.get("current_level", "unlearned") != "unlearned"
        )
    ]
    remaining_gaps = [
        skill for skill in skill_gaps
        if isinstance(skill, dict) and skill.get("is_gap", False)
    ]

    st.subheader("Skill Verification Summary")
    if initial_possible_skills:
        st.write("**Initial Possible Skills Relevant to the Goal:**")
        for skill in initial_possible_skills:
            source = "claimed" if skill.get("mentioned_in_learner_information", False) else "inferred"
            st.write(
                f"- {skill.get('name', '')}: "
                f"required={skill.get('required_level', '')}, "
                f"actual={skill.get('current_level', '')}, "
                f"source={source}"
            )
            evidence = skill.get("learner_context_evidence") or skill.get("reason", "")
            if evidence:
                st.caption(f"Basis: {evidence}")
    else:
        st.info("No goal-relevant skills were identified as claimed or context-inferred prior skills.")

    st.write("**Confirmed Missing Skills After Verification:**")
    if remaining_gaps:
        for skill in remaining_gaps:
            st.write(
                f"- {skill.get('name', '')}: "
                f"required={skill.get('required_level', '')}, "
                f"actual={skill.get('current_level', '')}"
            )
    else:
        st.success("No remaining skill gaps are currently confirmed.")

    confirmed = goal.get("skill_verification_confirmed", False)
    if not confirmed:
        if st.button("Confirm Verified Skill Status", key="confirm_verified_skill_status", type="primary"):
            goal["skill_verification_confirmed"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
        return False

    st.success("Verified skill status confirmed.")
    return True

def render_identifying_skill_gap(goal):
    with st.spinner('Identifying Skill Gap ...'):
        learning_goal = goal["learning_goal"]
        learner_information = st.session_state["learner_information"]
        llm_type = st.session_state["llm_type"]
        skill_gaps = identify_skill_gap(learning_goal, learner_information, llm_type)
    if not skill_gaps:
        st.error(st.session_state.get("last_skill_gap_error", "Capability mapping failed."))
        st.info("Configure an LLM API key in backend/.env, restart the backend, then retry this step.")
        return None
    goal["skill_gaps"] = skill_gaps
    goal["skill_verification_confirmed"] = False
    goal["learning_approach_assessment"] = {}
    goal["learning_approach_assessment_answers"] = {}
    goal["initial_learning_approach_state"] = {}
    save_persistent_state()
    st.rerun()
    st.toast("Skill gaps identified.")
    return skill_gaps


def render_identified_skill_gap(goal, method_name="cogent"):
    """
    Render skill gaps in a card-style with prev/next switching.
    """
    levels = ["unlearned", "beginner", "intermediate", "advanced"]
    # Render all skill cards on a single page (no pagination)
    skill_gaps = goal.get("skill_gaps", [])
    total = len(skill_gaps)
    if total == 0:
        st.info("No skills identified yet.")
        return

    for skill_id, skill_info in enumerate(skill_gaps):
        if isinstance(skill_info, dict):
            skill_name = skill_info.get("name", skill_id)  # 如果是字典，取name或key
        else:
            skill_name = skill_id  # 如果skill_info只是个字符串，那skill_id本身就是技能名
        required_level = skill_info.get("required_level", levels[0])
        current_level = skill_info.get("current_level", levels[0])

        background_color = "#ffe6e6" if skill_info.get("is_gap") else "#e6ffe6"
        text_color = "#ff4d4d" if skill_info.get("is_gap") else "#33cc33"
        requires_assessment = skill_info.get("requires_diagnostic_assessment", False)
        mentioned_before = skill_info.get("mentioned_in_learner_information", False)
        inferred_from_context = skill_info.get("inferred_from_learner_context", False)
        effective_inferred_from_context = inferred_from_context or (
            not mentioned_before and current_level != levels[0]
        )
        diagnostic_assessment = skill_info.get("diagnostic_assessment") or {}
        assessment_result = skill_info.get("diagnostic_assessment_result") or {}

        with st.container(border=True):
            # Card header
            st.markdown(
                f"""
                <div style="background-color: {background_color}; color: {text_color}; padding: 10px 16px; border-radius: 8px; margin-bottom: 12px; display: flex; align-items: center; min-height: 44px;">
                    <p style="font-weight: 700; margin: 0; flex: 1;">{skill_id+1:2d}. {skill_name}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Required level selector
            new_required_level = st.pills(
                "**Required Level**",
                options=levels,
                selection_mode="single",
                default=required_level,
                disabled=False,
                key=f"required_{skill_name}_{method_name}",
            )
            if new_required_level != required_level:
                goal["skill_gaps"][skill_id]["required_level"] = new_required_level
                goal["skill_verification_confirmed"] = False
                if levels.index(new_required_level) > levels.index(goal["skill_gaps"][skill_id].get("current_level", levels[0])):
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                save_persistent_state()
                st.rerun()

            # Current level selector
            new_current_level = st.pills(
                "**Current Level**",
                options=levels,
                selection_mode="single",
                default=current_level,
                disabled=False,
                key=f"current_{skill_name}__{method_name}",
            )
            if new_current_level != current_level:
                goal["skill_gaps"][skill_id]["current_level"] = new_current_level
                goal["skill_verification_confirmed"] = False
                if levels.index(new_current_level) < levels.index(goal["skill_gaps"][skill_id].get("required_level", levels[0])):
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                save_persistent_state()
                st.rerun()

            # Details
            with st.expander("More Analysis Details"):
                if levels.index(goal["skill_gaps"][skill_id].get("current_level", levels[0])) < levels.index(goal["skill_gaps"][skill_id].get("required_level", levels[0])):
                    st.warning("Current level is lower than the required level!")
                    goal["skill_gaps"][skill_id]["is_gap"] = True
                else:
                    st.success("Current level is equal to or higher than the required")
                    goal["skill_gaps"][skill_id]["is_gap"] = False
                st.write(f"**Reason**: {skill_info.get('reason', '')}")
                st.write(f"**Confidence Level**: {skill_info.get('level_confidence', '')}")
                st.write(f"**Mentioned in learner information**: {'Yes' if mentioned_before else 'No'}")
                st.write(f"**Inferred from learner context**: {'Yes' if effective_inferred_from_context else 'No'}")
                evidence = skill_info.get("learner_context_evidence") or skill_info.get("reason", "")
                if evidence:
                    st.write(f"**Source evidence**: {evidence}")
                if requires_assessment:
                    st.warning(skill_info.get("assessment_reason", "This skill should be verified with a diagnostic assessment."))
                elif effective_inferred_from_context and not assessment_result:
                    st.warning("This looks like an old inferred-skill result without diagnostic questions. Re-run skill gap identification to verify it.")
                else:
                    st.write("**Diagnostic assessment needed**: No")

            if requires_assessment:
                st.markdown("**Skill Verification Test**")
                st.info("This required skill is either claimed by the learner or inferred from their background, so the system must verify actual mastery before confirming the final skill gap.")
                question_sets = diagnostic_assessment.get("question_sets", [])
                if not question_sets:
                    st.error("Diagnostic questions were expected for this skill, but none are currently available.")
                answers_payload = []
                for question_set in question_sets:
                    level = str(question_set.get("level", "")).capitalize()
                    st.markdown(f"**{level} Level Questions**")
                    for idx, question in enumerate(question_set.get("questions", []), start=1):
                        st.write(f"{idx}. {question.get('question', '')}")
                        st.caption(f"Assessment focus: {question.get('assessment_focus', '')}")
                        answer_key = f"diagnostic_answer_{method_name}_{skill_name}_{question_set.get('level', '')}_{idx}"
                        learner_answer = st.text_area(
                            f"Answer {idx}",
                            key=answer_key,
                            placeholder="Write the learner's answer here...",
                        )
                        answers_payload.append(
                            {
                                "level": question_set.get("level", ""),
                                "question": question.get("question", ""),
                                "expected_answer": question.get("expected_answer", ""),
                                "learner_answer": learner_answer,
                            }
                        )
                submit_key = f"submit_diagnostic_{method_name}_{skill_name}"
                if st.button("Submit Diagnostic Assessment", key=submit_key, type="primary"):
                    if any(not str(item.get("learner_answer", "")).strip() for item in answers_payload):
                        st.warning("Please answer all diagnostic questions before submitting.")
                    else:
                        with st.spinner("Evaluating diagnostic assessment..."):
                            response = submit_diagnostic_assessment(
                                goal.get("learning_goal", ""),
                                goal.get("skill_gaps", []),
                                {
                                    "skill_name": skill_name,
                                    "answers": answers_payload,
                                },
                                learner_profile=goal.get("learner_profile", {}),
                                learner_information=st.session_state.get("learner_information", ""),
                                llm_type=st.session_state.get("llm_type", "gpt4o"),
                            )
                        if response:
                            goal["skill_gaps"] = response.get("skill_gaps", goal.get("skill_gaps", []))
                            goal["skill_verification_confirmed"] = False
                            updated_profile = response.get("learner_profile")
                            if updated_profile:
                                goal["learner_profile"] = updated_profile
                            try:
                                save_persistent_state()
                            except Exception:
                                pass
                            st.toast("Diagnostic assessment submitted and profile updated.")
                            st.rerun()
                        else:
                            st.error("Failed to submit the diagnostic assessment.")
            if assessment_result:
                with st.expander("Latest Diagnostic Result"):
                    st.success(f"Evaluated current level: {assessment_result.get('recommended_current_level', current_level)}")
                    st.write(assessment_result.get("overall_summary", ""))
                    for level_eval in assessment_result.get("level_evaluations", []):
                        st.write(
                            f"{str(level_eval.get('level', '')).capitalize()}: "
                            f"{level_eval.get('score', 0)} / 100, "
                            f"{'demonstrated' if level_eval.get('demonstrated') else 'not demonstrated'}"
                        )
                        st.caption(level_eval.get("rationale", ""))
            save_persistent_state()
            # Gap toggle
            old_gap_status = skill_info.get("is_gap", False)
            gap_status = st.toggle(
                "Mark as Gap",
                value=skill_info.get("is_gap", False),
                key=f"gap_{skill_name}_{method_name}",
                disabled=not skill_info.get("is_gap", False),
            )
            if gap_status != old_gap_status:
                goal["skill_gaps"][skill_id]["is_gap"] = gap_status
                goal["skill_verification_confirmed"] = False
                if not goal["skill_gaps"][skill_id]["is_gap"]:
                    goal["skill_gaps"][skill_id]["current_level"] = goal["skill_gaps"][skill_id].get("required_level", goal["skill_gaps"][skill_id].get("current_level"))
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
