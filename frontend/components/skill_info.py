import math
import streamlit as st


def render_skill_info(learner_profile):
    # --- 1. 安全检查：确保 learner_profile 是有效的字典 ---
    if not learner_profile or not isinstance(learner_profile, dict):
        st.warning("Learner profile data is not available yet.")
        return

    # 使用 .get() 安全获取层级数据，如果不存在则返回默认值
    cognitive_status = learner_profile.get("cognitive_status", {})
    mastered_skills = cognitive_status.get("mastered_skills", [])
    in_progress_skills = cognitive_status.get("in_progress_skills", [])

    columns_spec = 2

    # --- 2. 渲染已掌握技能 (Mastered Skills) ---
    st.write("**Mastered Skills:**")
    if mastered_skills:
        # 计算行数，增加安全判断防止除以零
        num_rows_mastered = math.ceil(len(mastered_skills) / columns_spec)
        columns_list_mastered = [st.columns(spec=columns_spec) for _ in range(num_rows_mastered)]

        for idx, skill in enumerate(mastered_skills):
            mastered_cols = columns_list_mastered[idx // columns_spec]
            with mastered_cols[idx % columns_spec]:
                # 安全获取技能名称和等级
                name = skill.get('name', 'Unknown Skill')
                level = skill.get('proficiency_level', 'Unknown').capitalize()
                st.markdown(
                    f"<div style='background-color: #edf3ec; color: #2f5f34; padding: 12px; border-radius: 12px; margin-bottom: 10px; border: 1px solid rgba(31, 29, 24, 0.08)'>"
                    f"<strong>{name}</strong><br>{level}</div>",
                    unsafe_allow_html=True
                )
    else:
        st.info("No skills are mastered yet.")

    # --- 3. 渲染进行中的技能 (Skills In Progress) ---
    st.write("**Skills In Progress:**")
    if in_progress_skills:
        num_rows_progress = math.ceil(len(in_progress_skills) / columns_spec)
        columns_list_progress = [st.columns(spec=columns_spec) for _ in range(num_rows_progress)]

        for idx, skill in enumerate(in_progress_skills):
            # 使用 .get() 防止键缺失导致的报错
            skill_name = skill.get("name", "Unknown Skill")
            required_level = skill.get("required_proficiency_level", "N/A").capitalize()
            current_level = skill.get("current_proficiency_level", "N/A").capitalize()

            in_progress_cols = columns_list_progress[idx // columns_spec]
            with in_progress_cols[idx % columns_spec]:
                st.markdown(
                    f"""
                    <div style='background-color: #f7ece7; color: #7d4e44; padding: 15px; border-radius: 12px; margin-bottom: 10px; border: 1px solid rgba(31, 29, 24, 0.08);'>
                        <strong>{skill_name}</strong><br>
                        <span>Required: <strong>{required_level}</strong></span><br>
                        <span>Current: <strong>{current_level}</strong></span><br>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    else:
        st.write("No skills currently in progress.")
