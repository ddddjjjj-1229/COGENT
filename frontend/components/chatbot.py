import streamlit as st
from streamlit_float import *
from utils.request_api import chat_with_tutor
from utils.state import get_current_session_uid, save_persistent_state, get_selected_goal
import time


@st.dialog("Tutor")
def ask_autor_chatbot():
    instruction = "Use the tutor for help with the current goal, session, or skill gap."
    # messages.chat_message("user").write(prompt)
    st.info(instruction)
    
    goal = get_selected_goal()
    if goal is None:
        goal = st.session_state["to_add_goal"]
    learner_profile = goal["learner_profile"]

    messages = st.container(height=300)
    if prompt := st.chat_input("Ask me anything"):
        current_session_uid = get_current_session_uid()
        messages.chat_message("user").write(prompt)
        st.session_state["tutor_messages"].append(
            {
                "role": "user",
                "content": prompt,
                "session_uid": current_session_uid,
                "goal_id": st.session_state.get("selected_goal_id", 0),
                "timestamp": time.time(),
            }
        )
        try:
            save_persistent_state()
        except Exception:
            pass
        current_session_messages = [
            msg for msg in st.session_state["tutor_messages"]
            if isinstance(msg, dict) and msg.get("session_uid") == current_session_uid
        ]
        response = chat_with_tutor(
            current_session_messages[-20:],
            learner_profile,
            st.session_state["llm_type"])
        messages.chat_message("assistant").write(response)
        st.session_state["tutor_messages"].append(
            {
                "role": "assistant",
                "content": response,
                "session_uid": current_session_uid,
                "goal_id": st.session_state.get("selected_goal_id", 0),
                "timestamp": time.time(),
            }
        )
        try:
            save_persistent_state()
        except Exception:
            pass
        # messages.chat_message("assistant").write(f"Echo: {prompt}")

def click_chatbot_func():
    ask_autor_chatbot()


def render_chatbot():
    float_init()

    button_container = st.container()
    with button_container:
        if_open_chatbot = st.button("Tutor", type="primary", key="chatbot", icon=":material/forum:", on_click=click_chatbot_func)
        if if_open_chatbot:
            st.session_state.show_chatbot = True

    button_css = float_css_helper(width="5.4rem", right="1.25rem", bottom="1.4rem", transition=0)
    button_container.float(button_css)
