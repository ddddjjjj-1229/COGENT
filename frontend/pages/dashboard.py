from collections import defaultdict
from html import escape
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from components.brand import render_brand_hero
from utils.state import get_selected_goal


APPROACH_ORDER = ["deep", "achieving", "surface"]
APPROACH_LABELS = {"deep": "Deep", "achieving": "Achieving", "surface": "Surface"}
APPROACH_COLORS = {"deep": "#274e47", "achieving": "#b89f6a", "surface": "#8d6254"}
CONFIDENCE_MAP = {"high": 0.92, "medium": 0.68, "low": 0.44}
LEVEL_MAP = defaultdict(lambda: 0, {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3})


def _chart_layout():
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1f1d18", family="Aptos, Segoe UI, sans-serif"),
        margin=dict(l=24, r=24, t=42, b=24),
    )


def _current_goal():
    return get_selected_goal()


def _approach_distribution(goal):
    learner_profile = goal.get("learner_profile", {}) or {}
    current_state = (learner_profile.get("learning_preferences", {}) or {}).get("learning_approach_state", {}) or {}
    initial_state = goal.get("initial_learning_approach_state", {}) or {}
    current_distribution = current_state.get("distribution", {}) or {}
    initial_distribution = initial_state.get("distribution", {}) or {}
    rows = []
    for approach in APPROACH_ORDER:
        rows.append(
            {
                "approach": APPROACH_LABELS[approach],
                "approach_key": approach,
                "initial": float(initial_distribution.get(approach, 0) or 0),
                "current": float(current_distribution.get(approach, 0) or 0),
            }
        )
    return pd.DataFrame(rows)


def _approach_history_frame(goal):
    learner_profile = goal.get("learner_profile", {}) or {}
    current_state = (learner_profile.get("learning_preferences", {}) or {}).get("learning_approach_state", {}) or {}
    history = list(current_state.get("history", []) or [])
    if not history:
        initial_state = goal.get("initial_learning_approach_state", {}) or {}
        history = list(initial_state.get("history", []) or [])
    rows = []
    for idx, item in enumerate(history):
        dominant_type = str(item.get("dominant_type", "unknown")).strip().lower()
        rows.append(
            {
                "step": idx + 1,
                "stage": str(item.get("chapter_id", f"Step {idx + 1}")),
                "dominant_type": APPROACH_LABELS.get(dominant_type, dominant_type.title() or "Unknown"),
                "dominant_key": dominant_type,
                "confidence": str(item.get("confidence", "medium")).strip().lower(),
                "confidence_score": CONFIDENCE_MAP.get(str(item.get("confidence", "medium")).strip().lower(), 0.55),
                "y": {"surface": 0, "achieving": 1, "deep": 2}.get(dominant_type, 1),
            }
        )
    return pd.DataFrame(rows)


def _mastery_frame(goal):
    learner_profile = goal.get("learner_profile", {}) or {}
    mastery_evidence = (learner_profile.get("cognitive_status", {}) or {}).get("mastery_evidence", []) or []
    rows = []
    for item in mastery_evidence:
        score = float(item.get("overall_score", 0) or 0)
        threshold = float(item.get("mastery_threshold", 80) or 80)
        rows.append(
            {
                "skill": str(item.get("skill_name", "Unknown skill")),
                "score": score,
                "threshold": threshold,
                "gap": score - threshold,
                "status": "Reached" if item.get("mastery_achieved", False) else "Needs reinforcement",
            }
        )
    if not rows:
        return pd.DataFrame(columns=["skill", "score", "threshold", "gap", "status"])
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["status", "gap", "score"], ascending=[True, True, False])
    return frame.tail(8)


def _session_effort_frame(goal):
    session_data = {"Session": [], "Minutes": []}
    for session in goal.get("learning_path", []) or []:
        session_id = session.get("id", "Session")
        session_data["Session"].append(session_id)
        if session.get("if_learned"):
            selected_gid = st.session_state["selected_goal_id"]
            match = re.search(r"\d+", str(session_id))
            selected_sid = int(match.group(0)) - 1 if match else 0
            times = st.session_state.get("session_learning_times", {}).get(f"{selected_gid}-{selected_sid}", {})
            if times.get("end_time") is not None and times.get("start_time") is not None:
                minutes = (times["end_time"] - times["start_time"]) / 60
            else:
                minutes = 0
            session_data["Minutes"].append(minutes)
        else:
            session_data["Minutes"].append(0)
    frame = pd.DataFrame(session_data)
    if not frame.empty:
        frame["Cumulative"] = frame["Minutes"].cumsum()
    return frame


def _normalized_mastery_history(goal):
    history = st.session_state.setdefault("learned_skills_history", {}).setdefault(goal["id"], [])
    if not history:
        return pd.DataFrame(columns=["Checkpoint", "Value"])
    values = [float(value or 0) for value in history]
    if values and max(values) <= 1:
        values = [value * 100 for value in values]
    return pd.DataFrame(
        {
            "Checkpoint": [f"T{i + 1}" for i in range(len(values))],
            "Value": values,
        }
    )


def render_dashboard():
    goal = _current_goal()
    if not goal:
        st.warning("No active goal is loaded.")
        return
    learner_profile = goal.get("learner_profile", {}) or {}
    if not learner_profile:
        st.warning("Please wait for the learning path to be scheduled to view the dashboard.")
        return

    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    learning_preferences = learner_profile.get("learning_preferences", {}) or {}
    approach_state = learning_preferences.get("learning_approach_state", {}) or {}
    learned_sessions = sum(1 for session in goal.get("learning_path", []) if session.get("if_learned"))
    total_sessions = len(goal.get("learning_path", []))
    render_brand_hero(
        page_label="Progress signals",
        title="COGENT analytics keep progress, preference drift, and mastery evidence in one view.",
        description="Track pathway progress, preference drift, mastery thresholds, and intervention outcomes in one place.",
        chips=[
            "preference drift",
            "mastery evidence",
            "intervention outcomes",
            "session effort",
        ],
        metrics=[
            {
                "value": f"{learned_sessions}/{total_sessions}" if total_sessions else "0/0",
                "label": "sessions complete",
                "detail": "How much of the current pathway has already been completed.",
            },
            {
                "value": f"{float(cognitive_status.get('overall_progress', 0) or 0):.1f}%",
                "label": "overall progress",
                "detail": "Current progress recorded in the learner profile.",
            },
            {
                "value": str(approach_state.get("dominant_type", "pending")).title(),
                "label": "current approach",
                "detail": "The strongest learning-approach signal at this point in the pathway.",
            },
            {
                "value": str(len((cognitive_status.get("mastery_evidence", []) or []))),
                "label": "evidence points",
                "detail": "Recent mastery records available for adaptive decisions.",
            },
        ],
        note="These signals keep pathway progress, preference drift, and mastery evidence in the same decision surface.",
    )

    top_left, top_right = st.columns([1.08, 0.92], gap="large")
    with top_left:
        with st.container(border=True):
            render_learning_progress(goal)
    with top_right:
        with st.container(border=True):
            render_adaptive_outcomes(goal)

    middle_left, middle_right = st.columns([1.06, 0.94], gap="large")
    with middle_left:
        with st.container(border=True):
            render_learning_preference_shift(goal)
    with middle_right:
        with st.container(border=True):
            render_learning_approach_timeline(goal)

    lower_left, lower_right = st.columns([1.02, 0.98], gap="large")
    with lower_left:
        with st.container(border=True):
            render_skill_radar_chart(goal)
    with lower_right:
        with st.container(border=True):
            render_mastery_gap_chart(goal)

    bottom_left, bottom_right = st.columns([1.02, 0.98], gap="large")
    with bottom_left:
        with st.container(border=True):
            render_session_learning_timeseries(goal)
    with bottom_right:
        with st.container(border=True):
            render_mastery_skills_timeseries(goal)


def render_learning_progress(goal):
    learner_profile = goal.get("learner_profile", {}) or {}
    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    remediation_sessions = sum(1 for session in goal.get("learning_path", []) or [] if session.get("is_remediation"))
    overall_progress = float(cognitive_status.get("overall_progress", 0) or 0)

    st.markdown("#### Progress overview")
    st.write("A fast read on pathway completion and how much remediation has already been inserted.")
    st.progress(overall_progress / 100 if overall_progress else 0)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Overall progress", f"{overall_progress:.1f}%")
    metric_cols[1].metric("Completed sessions", sum(1 for session in goal.get("learning_path", []) if session.get("if_learned")))
    metric_cols[2].metric("Remediation sessions", remediation_sessions)

    mastered = len((cognitive_status.get("mastered_skills", []) or []))
    in_progress = len((cognitive_status.get("in_progress_skills", []) or []))
    st.markdown(
        f"""
        <section class="cogent-distribution-card" style="margin-top:1rem;">
            <p class="cogent-panel-label">Improvement signals</p>
            <h3>What the evidence suggests</h3>
            <div class="cogent-signal-bullet-list">
                <div class="cogent-signal-bullet">
                    <span class="cogent-process-index">A</span>
                    <div>
                        <h4>{mastered} skills already marked as mastered</h4>
                        <p>Confirmed mastery stays separate from still-developing capability instead of being flattened into one score.</p>
                    </div>
                </div>
                <div class="cogent-signal-bullet">
                    <span class="cogent-process-index">B</span>
                    <div>
                        <h4>{in_progress} skills still actively developing</h4>
                        <p>The pathway can stay explicit about uncertainty while still moving the learner forward.</p>
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_adaptive_outcomes(goal):
    learner_profile = goal.get("learner_profile", {}) or {}
    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    learning_preferences = learner_profile.get("learning_preferences", {}) or {}
    approach_state = learning_preferences.get("learning_approach_state", {}) or {}
    candidate_types = list(approach_state.get("candidate_types_for_next_session", []) or [])
    mastery_frame = _mastery_frame(goal)
    mastery_alerts = int((mastery_frame["status"] == "Needs reinforcement").sum()) if not mastery_frame.empty else 0
    dominant_type = str(approach_state.get("dominant_type", "pending")).title()
    confidence = str(approach_state.get("confidence", "pending")).title()
    next_variants = ", ".join(candidate_types) if candidate_types else dominant_type

    st.markdown("#### Adaptive outcomes")
    st.write("A compact view of how learner evidence is shaping the pathway.")
    st.markdown(
        f"""
        <section class="cogent-process-card">
            <p class="cogent-panel-label">System impact</p>
            <h3>The current teaching stance is {escape(dominant_type)}</h3>
            <div class="cogent-process-step-list">
                <div class="cogent-process-step">
                    <span class="cogent-process-index">01</span>
                    <div>
                        <h4>Current approach confidence: {escape(confidence)}</h4>
                        <p>Uncertainty stays visible instead of being hidden behind a fixed profile.</p>
                    </div>
                </div>
                <div class="cogent-process-step">
                    <span class="cogent-process-index">02</span>
                    <div>
                        <h4>Next-session variants: {escape(next_variants)}</h4>
                        <p>Candidate variants can stay plural when the learner signal is still ambiguous.</p>
                    </div>
                </div>
                <div class="cogent-process-step">
                    <span class="cogent-process-index">03</span>
                    <div>
                        <h4>{mastery_alerts} active mastery alerts</h4>
                        <p>Weak quiz evidence can trigger reinforcement instead of being ignored between sessions.</p>
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_learning_preference_shift(goal):
    frame = _approach_distribution(goal)
    if frame.empty:
        st.info("Preference shift will appear after the learner has both an initial and current approach signal.")
        return

    st.markdown("#### Preference shift")
    st.write("Compare the initial learning-approach baseline against the latest state inferred from learner behavior.")
    melted = frame.melt(
        id_vars=["approach", "approach_key"],
        value_vars=["initial", "current"],
        var_name="state",
        value_name="value",
    )
    melted["value"] = melted["value"] * 100
    fig = px.bar(
        melted,
        x="approach",
        y="value",
        color="state",
        barmode="group",
        color_discrete_map={"initial": "#d8c4a0", "current": "#274e47"},
    )
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.1f}%<extra></extra>")
    fig.update_layout(
        yaxis_title="Share (%)",
        xaxis_title="Approach type",
        legend_title="State",
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_learning_approach_timeline(goal):
    frame = _approach_history_frame(goal)
    st.markdown("#### Preference timeline")
    st.write("Track how the learner's dominant approach shifts across the pathway.")
    if frame.empty:
        st.info("Preference timeline will appear after the system records at least one learning-approach state.")
        return

    fig = go.Figure()
    for approach in APPROACH_ORDER:
        subset = frame[frame["dominant_key"] == approach]
        if subset.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=subset["stage"],
                y=subset["y"],
                mode="lines+markers",
                name=APPROACH_LABELS[approach],
                line=dict(color=APPROACH_COLORS[approach], width=3, shape="spline"),
                marker=dict(size=12 + subset["confidence_score"] * 10, color=APPROACH_COLORS[approach], line=dict(color="#fffdfa", width=1.2)),
                customdata=subset[["confidence"]],
                hovertemplate="%{x}<br>" + APPROACH_LABELS[approach] + "<br>confidence: %{customdata[0]}<extra></extra>",
            )
        )
    fig.update_layout(
        yaxis=dict(
            tickmode="array",
            tickvals=[0, 1, 2],
            ticktext=["Surface", "Achieving", "Deep"],
            gridcolor="rgba(31, 29, 24, 0.08)",
            zeroline=False,
        ),
        xaxis=dict(showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_skill_radar_chart(goal):
    st.markdown("#### Capability lift")
    st.write("Compare current proficiency against the target level expected by the pathway.")
    learner_profile = goal.get("learner_profile", {}) or {}
    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    mastered_skills = cognitive_status.get("mastered_skills", []) or []
    in_progress_skills = cognitive_status.get("in_progress_skills", []) or []

    mastered_skills = [
        {
            "name": item["name"],
            "required_level": item["proficiency_level"],
            "current_level": item["proficiency_level"],
        }
        for item in mastered_skills
    ]
    in_progress_skills = [
        {
            "name": item["name"],
            "required_level": item["required_proficiency_level"],
            "current_level": item["current_proficiency_level"],
        }
        for item in in_progress_skills
    ]
    skills = mastered_skills + in_progress_skills
    if not skills:
        st.info("Capability lift will appear after the learner profile contains required or mastered skills.")
        return

    skill_names = [skill["name"] for skill in skills]
    current_levels = [LEVEL_MAP[skill["current_level"]] for skill in skills]
    required_levels = [LEVEL_MAP[skill["required_level"]] for skill in skills]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=current_levels,
            theta=skill_names,
            fill="toself",
            name="Current level",
            fillcolor="rgba(39, 78, 71, 0.18)",
            line=dict(color="rgba(39, 78, 71, 0.95)", width=2),
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=required_levels,
            theta=skill_names,
            fill="toself",
            name="Required level",
            fillcolor="rgba(184, 159, 106, 0.16)",
            line=dict(color="rgba(184, 159, 106, 0.95)", width=2),
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 3],
                tickvals=[0, 1, 2, 3],
                ticktext=["Unlearned", "Beginner", "Intermediate", "Advanced"],
                gridcolor="rgba(31, 29, 24, 0.10)",
                linecolor="rgba(31, 29, 24, 0.10)",
            ),
            angularaxis=dict(
                tickfont=dict(size=13),
                gridcolor="rgba(31, 29, 24, 0.08)",
                linecolor="rgba(31, 29, 24, 0.10)",
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_mastery_gap_chart(goal):
    frame = _mastery_frame(goal)
    st.markdown("#### Mastery threshold view")
    st.write("See which skills have crossed the mastery threshold and which still need reinforcement.")
    if frame.empty:
        st.info("Mastery threshold data will appear after the learner completes session quizzes.")
        return

    frame = frame.sort_values("gap")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=frame["score"],
            y=frame["skill"],
            orientation="h",
            name="Observed score",
            marker_color=[APPROACH_COLORS["deep"] if status == "Reached" else APPROACH_COLORS["surface"] for status in frame["status"]],
            hovertemplate="%{y}<br>score: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=frame["threshold"],
            y=frame["skill"],
            mode="markers",
            name="Threshold",
            marker=dict(color="#b89f6a", size=10, symbol="diamond"),
            hovertemplate="%{y}<br>threshold: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="Score (%)",
        yaxis_title="Skill",
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_session_learning_timeseries(goal):
    st.markdown("#### Session effort")
    st.write("Minutes spent in each session with a cumulative effort line to show how study time is building across the pathway.")
    frame = _session_effort_frame(goal)
    if frame.empty:
        st.info("Session effort will appear after the learner completes at least one timed session.")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=frame["Session"],
            y=frame["Minutes"],
            name="Session minutes",
            marker_color="#274e47",
            hovertemplate="%{x}<br>%{y:.1f} minutes<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["Session"],
            y=frame["Cumulative"],
            mode="lines+markers",
            name="Cumulative effort",
            line=dict(color="#b89f6a", width=3, shape="spline"),
            marker=dict(size=8),
            hovertemplate="%{x}<br>%{y:.1f} cumulative minutes<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title_text="Session minutes", secondary_y=False, gridcolor="rgba(31, 29, 24, 0.08)")
    fig.update_yaxes(title_text="Cumulative minutes", secondary_y=True, showgrid=False)
    fig.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_mastery_skills_timeseries(goal):
    st.markdown("#### Mastery history")
    st.write("A rolling view of how the learner's overall mastery signal changes over checkpoints.")
    frame = _normalized_mastery_history(goal)
    if frame.empty:
        st.info("Mastery history will appear after the app records at least one checkpoint.")
        return

    fig = px.area(
        frame,
        x="Checkpoint",
        y="Value",
        markers=True,
        color_discrete_sequence=["#b89f6a"],
    )
    fig.update_traces(
        line=dict(width=3, color="#8a6520"),
        marker=dict(size=8, color="#274e47", line=dict(color="#fffdfa", width=1)),
        fillcolor="rgba(184, 159, 106, 0.22)",
        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
    )
    fig.update_layout(
        yaxis_title="Mastery signal (%)",
        xaxis_title="Checkpoint",
        showlegend=False,
        **_chart_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)


render_dashboard()
