# COGENT Backend

The COGENT backend is a FastAPI service that coordinates the system's LLM agents for goal refinement, skill diagnosis, learner modeling, path scheduling, learning content generation, quizzes, and tutoring.

## Setup

From the repository root:

```cmd
py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Create a local environment file:

```cmd
copy backend\.env.example backend\.env
```

Then add your model provider key to `backend\.env`, for example:

```text
DEEPSEEK_API_KEY=your-key
# or
DASHSCOPE_API_KEY=your-qwen-key
# optional alias also supported:
QWEN_API_KEY=your-qwen-key
```

## Run

Use the COGENT backend launcher from the repository root:

```cmd
scripts\start_cogent_backend.cmd
```

The backend runs on:

```text
http://127.0.0.1:5018/
```

## Model Options

The backend advertises these local model choices to the frontend:

```text
deepseek/deepseek-chat
deepseek/deepseek-v4-flash
qwen/qwen-plus
qwen/qwen-max
```

For Qwen, set either `DASHSCOPE_API_KEY` or `QWEN_API_KEY`. The backend uses DashScope's OpenAI-compatible endpoint by default:

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

## Main Modules

- `main.py`: FastAPI application and endpoint wiring.
- `api_schemas.py`: request models shared by the API endpoints.
- `modules/skill_gap_identification/`: goal refinement, skill mapping, gap identification, and diagnostic assessment.
- `modules/adaptive_learner_modeling/`: learner profile initialization, updates, and learning preference inference.
- `modules/personalized_resource_delivery/`: path scheduling, knowledge exploration, document generation, and quizzes.
- `modules/ai_chatbot_tutor/`: tutor chat behavior.
- `utils/language.py`: response-language adaptation for learner-facing generated content.

## Configuration

Primary config files:

```text
backend/config/main.yaml
backend/config/default.yaml
```

Default local service settings:

```text
host: 127.0.0.1
port: 5018
```

The retrieval vector store is written under `backend/data/` or `data/vectorstore/` depending on runtime context. These directories are local runtime artifacts and are ignored by Git.

## API Check

Once the backend is running, model availability can be checked at:

```text
http://127.0.0.1:5018/list-llm-models
```

## Notes For GitHub

Do not commit `backend/.env`, vector stores, logs, or local runtime data. Use `backend/.env.example` to document required environment variables.
