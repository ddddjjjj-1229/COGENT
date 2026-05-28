from html import escape

import streamlit as st


def cogent_mark_svg(class_name="cogent-brand-mark"):
    return f"""
    <svg class="{class_name}" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
            <radialGradient id="brand-icon-bg" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(43 35) rotate(50) scale(105)">
                <stop stop-color="#314B4E"/>
                <stop offset="0.62" stop-color="#181510"/>
                <stop offset="1" stop-color="#12100D"/>
            </radialGradient>
            <linearGradient id="brand-icon-signal" x1="30" y1="91" x2="93" y2="26" gradientUnits="userSpaceOnUse">
                <stop stop-color="#A7C8CF"/>
                <stop offset="0.5" stop-color="#F3D28B"/>
                <stop offset="1" stop-color="#F7F1E6"/>
            </linearGradient>
        </defs>
        <rect x="6" y="6" width="116" height="116" rx="28" fill="url(#brand-icon-bg)"/>
        <rect x="6.5" y="6.5" width="115" height="115" rx="27.5" stroke="#3D382E"/>
        <path d="M92 40C82.8 28.4 66.8 23.6 52.2 27.4C33.8 32.3 22.7 50.8 27.6 69.2C32.5 88 51.7 99.2 70.4 94C81.2 91 89.6 83.7 93.8 74" stroke="url(#brand-icon-signal)" stroke-width="10" stroke-linecap="round"/>
        <path d="M41 74C49.6 63.2 59.9 55.1 72.6 48.7C79.5 45.2 87 43 94.8 41.5" stroke="#F3D28B" stroke-width="4.5" stroke-linecap="round"/>
        <path d="M72.6 48.7L101 25.4" stroke="#A7C8CF" stroke-width="4" stroke-linecap="round"/>
        <circle cx="41" cy="74" r="5.6" fill="#F7F1E6"/>
        <circle cx="72.6" cy="48.7" r="4.5" fill="#F3D28B"/>
        <circle cx="101" cy="25.4" r="5.4" fill="#A7C8CF"/>
        <circle cx="57.5" cy="64" r="15.4" fill="#181510" stroke="#F7F1E6" stroke-width="3.4"/>
        <circle cx="57.5" cy="64" r="4.2" fill="#F3D28B"/>
    </svg>
    """


def render_brand_hero(
    page_label,
    title,
    description,
    chips=None,
    metrics=None,
    panel_title="System signals",
    note=None,
):
    chips = chips or []
    metrics = metrics or []

    chips_html = "".join(
        f"<span class='cogent-chip'>{escape(str(chip))}</span>" for chip in chips if str(chip).strip()
    )
    metrics_html = "".join(
        (
            "<div class='cogent-signal-item'>"
            f"<div class='cogent-signal-value'>{escape(str(item.get('value', '')))}</div>"
            f"<div class='cogent-signal-label'>{escape(str(item.get('label', '')))}</div>"
            f"<div class='cogent-signal-detail'>{escape(str(item.get('detail', '')))}</div>"
            "</div>"
        )
        for item in metrics
        if isinstance(item, dict)
    )

    note_html = (
        f"<p class='cogent-panel-note'>{escape(str(note))}</p>"
        if note and str(note).strip()
        else ""
    )
    panel_html = (
        "<aside class='cogent-signal-panel'>"
        f"<p class='cogent-panel-label'>{escape(str(panel_title))}</p>"
        f"<div class='cogent-signal-list'>{metrics_html}</div>"
        f"{note_html}"
        "</aside>"
        if metrics_html
        else ""
    )

    st.markdown(
        f"""
        <section class="cogent-hero">
            <div class="cogent-hero-head">
                <p class="cogent-kicker">{escape(str(page_label))}</p>
                <div class="cogent-wordmark">{cogent_mark_svg()}<span>COGENT</span></div>
            </div>
            <div class="cogent-hero-grid">
                <div class="cogent-hero-copy">
                    <h1>{escape(str(title))}</h1>
                    <p>{escape(str(description))}</p>
                    <div class="cogent-chip-row">{chips_html}</div>
                </div>
                {panel_html}
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_feature_grid(title, description, items):
    cards_html = "".join(
        (
            "<article class='cogent-feature-card'>"
            f"<p class='cogent-feature-eyebrow'>{escape(str(item.get('eyebrow', '')))}</p>"
            f"<h3>{escape(str(item.get('title', '')))}</h3>"
            f"<p>{escape(str(item.get('body', '')))}</p>"
            "</article>"
        )
        for item in items
        if isinstance(item, dict)
    )

    st.markdown(
        f"""
        <section class="cogent-feature-section">
            <div class="cogent-section-head">
                <p class="cogent-kicker">COGENT signatures</p>
                <h2>{escape(str(title))}</h2>
                <p>{escape(str(description))}</p>
            </div>
            <div class="cogent-feature-grid">{cards_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_info_panel(label, title, body):
    st.markdown(
        f"""
        <section class="cogent-info-panel">
            <p class="cogent-panel-label">{escape(str(label))}</p>
            <h3>{escape(str(title))}</h3>
            <p>{escape(str(body))}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand_card():
    st.markdown(
        f"""
        <section class="cogent-sidebar-card">
            <div class="cogent-sidebar-brand-lockup">
                {cogent_mark_svg("cogent-brand-mark cogent-brand-mark--sidebar")}
                <div>
                    <p class="cogent-kicker">Learning system</p>
                    <h2>COGENT</h2>
                </div>
            </div>
            <p>Goal refinement, capability verification, preference tracing, and mastery-aware remediation in one workflow.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
