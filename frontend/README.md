# COGENT Frontend

The COGENT frontend is a Streamlit interface for goal-oriented adaptive learning. It guides learners through onboarding, goal management, skill verification, learning path scheduling, profile review, study sessions, quizzes, and progress signals.

## Setup

From the repository root:

```cmd
py -3 -m venv frontend\.venv
frontend\.venv\Scripts\python.exe -m pip install -r frontend\requirements.txt
```

The frontend expects the backend to be available at:

```text
http://127.0.0.1:5018/
```

You can change this in `frontend/config.py`.

## Run

Start only the frontend:

```cmd
scripts\start_cogent_frontend.cmd
```

Or start the full COGENT system:

```cmd
launch_cogent.cmd
```

The frontend runs on:

```text
http://127.0.0.1:8518/
```

## Project Structure

```text
frontend/
  main.py                 Streamlit entry point and navigation
  config.py               frontend backend URL and runtime toggles
  assets/                 COGENT icon, CSS, JavaScript, and mock JSON fixtures
  components/             reusable UI components
  pages/                  onboarding, goals, skill map, path, profile, sessions, dashboard
  utils/                  API calls, state persistence, formatting, PDF and learner context helpers
  user_data/              local learner state created at runtime
```

## Important Files

- `assets/css/main.css`: main COGENT visual system.
- `assets/cogent_icon.svg`: COGENT browser/page icon.
- `assets/cogent_logo.svg`: COGENT sidebar and brand lockup.
- `utils/state.py`: local state persistence and active-goal synchronization.
- `utils/request_api.py`: backend API requests.
- `utils/learner_context.py`: text and attachment context merging.
- `pages/goal_management.py`: multi-goal board and goal creation flow.
- `pages/learning_path.py`: active goal pathway and rescheduling.
- `pages/knowledge_document.py`: learning session reading, quizzes, and mastery feedback.

## Mock Mode

To run the UI against local fixture data instead of the backend, edit `frontend/config.py`:

```python
use_mock_data = True
```

Then start the frontend launcher.

## Local Data

Runtime learner state is stored under:

```text
frontend/user_data/
```

This directory is ignored by Git except for `.gitkeep`.

## Troubleshooting

- If the frontend cannot reach the backend, confirm `scripts\start_cogent_backend.cmd` is running and `frontend/config.py` points to `http://127.0.0.1:5018/`.
- If generated content appears in the wrong language, create or regenerate the goal/profile/path after entering learner information in the desired language.
- If Streamlit shows a `st.navigation` pages-directory warning, it is a framework warning and does not block local use.
