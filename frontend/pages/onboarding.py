import streamlit as st

from components.goal_refinement import render_goal_refinement
from utils.learner_context import extract_attachment_context, merge_learner_information
from utils.state import save_persistent_state
from components.topbar import render_topbar
from components.brand import render_brand_hero, render_feature_grid


def on_refine_click():
    st.session_state["if_refining_learning_goal"] = True
    try:
        save_persistent_state()
    except Exception:
        pass


def _init_onboarding_state():
    """Ensure required session_state keys exist to avoid KeyErrors."""
    st.session_state.setdefault("onboarding_card_index", 0)  # 0: goal, 1: info
    st.session_state.setdefault("if_refining_learning_goal", False)
    st.session_state.setdefault("learner_identity", st.session_state.get("learner_occupation", ""))
    st.session_state.setdefault("learner_occupation", "")
    st.session_state.setdefault("learner_information_text", "")
    st.session_state.setdefault("learner_information", "")
    st.session_state.setdefault(
        "to_add_goal",
        {
            "learning_goal": "",
            "learner_information": st.session_state.get("learner_information", ""),
            "skill_gaps": [],
            "learner_profile": {},
            "learning_approach_assessment": {},
            "initial_learning_approach_state": {},
            "skill_verification_confirmed": False,
            "learning_path": [],
            "is_completed": False,
            "is_deleted": False,
        },
    )
    try:
        save_persistent_state()
    except Exception:
        pass


def _inject_card_css():
    """Inject lightweight CSS to make sections look like cards and style nav buttons."""
    st.markdown(
        """
        <style>
        .gm-card { 
            background: #ffffff; 
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 14px; 
            box-shadow: 0 8px 24px rgba(0,0,0,0.06);
            padding: 24px 22px; 
        }
        .gm-side { position: sticky; top: 160px; }
        .gm-side .gm-side-btn {
            border: 1px solid rgba(0,0,0,0.12);
            background: #ffffff;
            color: #111827;
            padding: 6px 10px; 
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_onboard():
    _init_onboarding_state()
    _inject_card_css()
    left, center, right = st.columns([1, 5, 1])
    goal = st.session_state["to_add_goal"]
    if "refined_learning_goal" not in st.session_state:
        st.session_state["refined_learning_goal"] = goal["learning_goal"]
        try:
            save_persistent_state()
        except Exception:
            pass
    with center:
        render_topbar()
        render_brand_hero(
            page_label="Start the adaptive workflow",
            title="COGENT turns a rough learning request into an evidence-based teaching plan.",
            description="Define the goal, add learner context, and let the system refine intent before it verifies capability gaps and schedules the first pathway.",
            chips=[
                "goal refinement",
                "capability verification",
                "preference tracing",
                "mastery-aware pathing",
            ],
            metrics=[
                {
                    "value": "Before scheduling",
                    "label": "capability check",
                    "detail": "The plan waits for learner context, skill evidence, and the initial approach signal.",
                },
                {
                    "value": "During study",
                    "label": "adaptive variants",
                    "detail": "Later sessions can align content with the learner's current approach.",
                },
                {
                    "value": "After quiz evidence",
                    "label": "reinforcement loop",
                    "detail": "Weak mastery can push targeted remediation back into the path.",
                },
            ],
            note="COGENT links planning, diagnosis, and remediation in one continuous loop.",
        )
        render_feature_grid(
            title="What COGENT surfaces immediately",
            description="These signals define how the planning flow reacts before the pathway is generated.",
            items=[
                {
                    "eyebrow": "01",
                    "title": "Refine the objective first",
                    "body": "Broad requests can be tightened into a concrete learning outcome before the schedule is generated.",
                },
                {
                    "eyebrow": "02",
                    "title": "Verify capability gaps",
                    "body": "Skill evidence stays visible so learners understand what the path is reacting to.",
                },
                {
                    "eyebrow": "03",
                    "title": "Track preference signals",
                    "body": "Initial approach evidence becomes part of the planning context instead of a detached survey.",
                },
                {
                    "eyebrow": "04",
                    "title": "Close the mastery loop",
                    "body": "Session outcomes can insert reinforcement rather than silently allowing weak spots to drift forward.",
                },
            ],
        )
        render_cards_with_nav(goal)
        

def render_goal(goal):
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.caption("Step 1 of 2")
        st.subheader("Define the learning objective")
        st.info("Describe the outcome you want COGENT to optimize for. You can refine the goal before moving to capability mapping.")
        learning_goal = st.text_area(
            "Enter your learning goal",
            value=goal["learning_goal"],
            label_visibility="visible",
            disabled=st.session_state["if_refining_learning_goal"],
            placeholder="Example: build a working foundation in data mining for research projects",
        )
        goal["learning_goal"] = learning_goal
        button_col, hint_col, next_col = st.columns([3, 10, 3])
        render_goal_refinement(goal, button_col, hint_col)
        save_persistent_state()
        with hint_col:
            if st.session_state["if_refining_learning_goal"]:
                st.write("**Refining goal...**")
        with next_col:
            if st.button("Continue", key="gm_nav_next", use_container_width=True, disabled=(idx == 1), type="primary"):
                st.session_state["onboarding_card_index"] = min(1, idx + 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
        



def render_information(goal):
    idx = st.session_state.get("onboarding_card_index", 0)
    with st.container(border=True):
        st.caption("Step 2 of 2")
        st.subheader("Add learner context")
        st.info("Share enough context for COGENT to map the right gaps and schedule a realistic first path.")

        learner_identity = st.text_input(
            "Fill in your identity information",
            value=st.session_state.get("learner_identity", ""),
            placeholder="Example: undergraduate student in education technology; beginner in data mining; preparing for a research project",
            help="You can describe your role, background, study stage, major, current level, or learning situation.",
        )
        st.session_state["learner_identity"] = learner_identity
        # Keep the old key populated so previously written helpers and saved data remain compatible.
        st.session_state["learner_occupation"] = learner_identity
        try:
            save_persistent_state()
        except Exception:
            pass

        info_col, attachment_col = st.columns([1.2, 0.8], gap="large")
        with info_col:
            learner_information_text = st.text_area(
                "Describe prior experience, preferences, constraints, or anything else the system should know",
                value=st.session_state["learner_information_text"],
                label_visibility="visible",
                height=180,
                placeholder="Example: comfortable with research papers, prefers concise explanations, wants hands-on practice on weekdays",
            )
            st.session_state["learner_information_text"] = learner_information_text
            try:
                save_persistent_state()
            except Exception:
                pass
        with attachment_col:
            uploaded_files = st.file_uploader(
                "Optional attachments",
                type=["pdf", "png", "jpg", "jpeg", "webp", "txt", "md"],
                accept_multiple_files=True,
                help="PDF text will be merged automatically. Image attachments are recorded as supplemental context.",
            )
            if uploaded_files:
                st.caption("Attachments added:")
                for uploaded_file in uploaded_files:
                    st.write(f"- {uploaded_file.name}")
        # st.divider()
        arrow_left, space_col, continue_button_col = st.columns([3, 10, 3])
        save_persistent_state()
        with arrow_left:
            if st.button("Back", key="gm_nav_prev", use_container_width=True, disabled=(idx == 0)):
                st.session_state["onboarding_card_index"] = max(0, idx - 1)
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
        with continue_button_col:
            render_continue_button(goal, uploaded_files)

def render_continue_button(goal, uploaded_files):
    if st.button("Build capability map", type="primary"):
        learner_identity = st.session_state.get("learner_identity", "").strip()
        if not goal["learning_goal"] or not learner_identity:
            st.warning("Please provide both a learning goal and your identity information before continuing.")
        else:
            base_information = merge_learner_information(
                "",
                f"Identity information:\n{learner_identity}",
                st.session_state.get("learner_information_text", ""),
            )
            attachment_information, attachment_summaries = extract_attachment_context(uploaded_files)
            merged_information = merge_learner_information(base_information, attachment_information)
            st.session_state["learner_information"] = merged_information
            goal["learner_information"] = merged_information
            if attachment_summaries:
                st.toast("Attachments added to learner context.")
            st.session_state["selected_page"] = "Capability Map"
            try:
                save_persistent_state()
            except Exception:
                pass
            st.switch_page("pages/skill_gap.py")


def render_cards_with_nav(goal):
    """Show either the Goal or Information section as a card with left/center/right nav buttons."""
    idx = st.session_state.get("onboarding_card_index", 0)

    if idx == 0:
        render_goal(goal)
    else:
        render_information(goal)

render_onboard()
