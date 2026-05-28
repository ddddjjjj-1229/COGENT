import streamlit as st
import time
from pathlib import Path
from utils.state import initialize_session_state, save_persistent_state, _get_data_store_path, get_selected_goal, sync_selected_goal_context
from components.brand import render_sidebar_brand_card
initialize_session_state()


st.session_state.setdefault("_autosave_enabled", True)
try:
    save_persistent_state()
except Exception:
    pass

from components.chatbot import render_chatbot

APP_DIR = Path(__file__).resolve().parent
ASSET_DIR = APP_DIR / "assets"
PAGE_ICON_PATH = ASSET_DIR / "cogent_icon.svg"
BRAND_LOGO_PATH = ASSET_DIR / "cogent_logo.svg"
CSS_PATH = ASSET_DIR / "css" / "main.css"

st.set_page_config(page_title="COGENT", page_icon=str(PAGE_ICON_PATH), layout="wide")
st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
if BRAND_LOGO_PATH.exists() and PAGE_ICON_PATH.exists():
    st.logo(str(BRAND_LOGO_PATH), icon_image=str(PAGE_ICON_PATH))

try:
    if st.session_state.get("if_complete_onboarding", False) and not st.session_state.get("_navigated_lp_once", False):
        st.session_state["_navigated_lp_once"] = True
        try:
            st.switch_page("pages/learning_path.py")
        except Exception:
            pass
except Exception:
    pass

@st.dialog("Confirm Reset")
def show_reset_dialog():
    st.warning("Clear the local history for this workspace?")
    st.divider()
    col_confirm, _space, col_cancel = st.columns([1, 2, 0.7])
    with col_confirm:
        if st.button("Confirm", type="primary"):
            from pathlib import Path
            from datetime import datetime
            import shutil
            try:
                st.session_state["_autosave_enabled"] = False
            except Exception:
                pass
            try:
                data_path = _get_data_store_path()
            except Exception:
                data_path = Path(__file__).resolve().parent / "user_data" / "data_store.json"
            try:
                data_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            if data_path.exists():
                try:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    backup_path = data_path.parent / f"data_storage-{ts}.json"
                    shutil.copy2(str(data_path), str(backup_path))
                except Exception:
                    pass
                try:
                    data_path.unlink()
                except Exception:
                    pass
            try:
                st.session_state.clear()
            except Exception:
                pass
            try:
                # After clearing state, navigate to onboarding page explicitly
                try:
                    st.switch_page("pages/onboarding.py")
                except Exception:
                    st.rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass
    with col_cancel:
        if st.button("Cancel"):
            # simply rerun to close the dialog without changes
            try:
                st.rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass

if st.session_state["show_chatbot"]:
    render_chatbot()

if st.session_state["if_complete_onboarding"]:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=False, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=True, url_path="learning_path")
else:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=True, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=False, url_path="learning_path")
skill_gaps = st.Page("pages/skill_gap.py", title="Capability Map", icon=":material/insights:", default=False, url_path="skill_gap")
knowledge_document = st.Page("pages/knowledge_document.py", title="Session Studio", icon=":material/menu_book:", default=False, url_path="knowledge_document")
learner_profile = st.Page("pages/learner_profile.py", title="My Profile", icon=":material/person:", default=False, url_path="learner_profile")
goal_management = st.Page("pages/goal_management.py", title="Goals", icon=":material/flag:", default=False, url_path="goal_management")
dashboard = st.Page("pages/dashboard.py", title="Progress Signals", icon=":material/browse:", default=False, url_path="dashboard")

# Learning Analytics Dashboard
if not st.session_state["if_complete_onboarding"]:
    nav_position = "sidebar"
    pg = st.navigation({"COGENT": [onboarding, skill_gaps, learning_path]}, position="hidden", expanded=True)
else:
    nav_position = "sidebar"
    pg = st.navigation({"COGENT": [goal_management, learning_path, knowledge_document, learner_profile, dashboard]}, position=nav_position, expanded=True)
    with st.sidebar:
        render_sidebar_brand_card()
        _left, _center, _right = st.columns([2, 2, 2])
        with _center:
            if st.button("Reset", help="Clear local history (keeps timestamped backups)"):
                show_reset_dialog()
    goal = get_selected_goal()
    if goal:
        goal['start_time'] = time.time()
        try:
            save_persistent_state()
        except Exception:
            pass
        learner_profile = goal.get("learner_profile", {}) if isinstance(goal, dict) else {}
        cognitive_status = learner_profile.get("cognitive_status", {}) if isinstance(learner_profile, dict) else {}
        in_progress_skills = cognitive_status.get("in_progress_skills", []) if isinstance(cognitive_status, dict) else []
        mastered_skills = cognitive_status.get("mastered_skills", []) if isinstance(cognitive_status, dict) else []
        unlearned_skill = len(in_progress_skills)
        learned_skill = len(mastered_skills)
        all_skill = learned_skill + unlearned_skill

        if goal['id'] not in st.session_state['learned_skills_history']:
            st.session_state['learned_skills_history'][goal['id']] = []
            try:
                save_persistent_state()
            except Exception:
                pass

        if all_skill != 0:
            mastery_rate = learned_skill / all_skill if all_skill != 0 else 0
            if st.session_state['learned_skills_history'][goal['id']] == []:
                st.session_state['learned_skills_history'][goal['id']].append(mastery_rate)
                try:
                    save_persistent_state()
                except Exception:
                    pass
        if(time.time()-goal['start_time']>600):
            goal['start_time'] = time.time()
            try:
                save_persistent_state()
            except Exception:
                pass
            st.session_state['learned_skills_history'][goal['id']].append(mastery_rate)
            try:
                save_persistent_state()
            except Exception:
                pass

        if len(st.session_state['learned_skills_history'][goal['id']]) > 10:
            st.session_state['learned_skills_history'][goal['id']].pop(0)
            try:
                save_persistent_state()
            except Exception:
                pass

        try:
            save_persistent_state()
        except Exception:
            pass

try:
    if st.session_state.get("_autosave_enabled", True):
        save_persistent_state()
except Exception:
    pass

if len(st.session_state["goals"]) != 0:
    sync_selected_goal_context()
    try:
        save_persistent_state()
    except Exception:
        pass

pg.run()
