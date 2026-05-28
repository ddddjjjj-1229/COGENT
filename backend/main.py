import ast
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from base.llm_factory import LLMFactory
from base.search_rag import SearchRagManager
from utils.preprocess import extract_text_from_pdf
from fastapi.responses import JSONResponse
from modules.skill_gap_identification import *
from modules.adaptive_learner_modeling import *
from modules.personalized_resource_delivery import *
from modules.ai_chatbot_tutor import chat_with_tutor_with_llm
from api_schemas import *
from config import load_config

import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env", override=True, encoding="utf-8-sig")

app_config = load_config(config_name="main")
search_rag_manager = None

AVAILABLE_LLM_MODELS = [
    {"model_provider": "deepseek", "model_name": "deepseek-chat"},
    {"model_provider": "deepseek", "model_name": "deepseek-v4-flash"},
    {"model_provider": "qwen", "model_name": "qwen-plus"},
    {"model_provider": "qwen", "model_name": "qwen-max"},
]


def _has_env_value(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _provider_is_configured(model_provider: str) -> bool:
    provider = (model_provider or "").lower()
    if provider == "deepseek":
        return _has_env_value("DEEPSEEK_API_KEY")
    if provider in {"qwen", "dashscope"}:
        return _has_env_value("DASHSCOPE_API_KEY") or _has_env_value("QWEN_API_KEY")
    return True


def _provider_setup_hint(model_provider: str) -> str:
    provider = (model_provider or "").lower()
    if provider == "deepseek":
        return "DeepSeek is selected, but DEEPSEEK_API_KEY is not set in backend/.env."
    if provider in {"qwen", "dashscope"}:
        return "Qwen is selected, but DASHSCOPE_API_KEY or QWEN_API_KEY is not set in backend/.env."
    return f"{model_provider} is selected, but its required API key is not configured."


def get_search_rag_manager():
    global search_rag_manager
    if search_rag_manager is None:
        search_rag_manager = SearchRagManager.from_config(app_config)
    return search_rag_manager

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_llm(model_provider: str | None = None, model_name: str | None = None, **kwargs):
    model_provider = (model_provider or "deepseek").lower()
    if not _provider_is_configured(model_provider):
        raise HTTPException(status_code=400, detail=_provider_setup_hint(model_provider))
    if model_provider in {"qwen", "dashscope"}:
        model_name = model_name or "qwen-plus"
        qwen_api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        qwen_base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        return LLMFactory.create(
            model=model_name,
            model_provider="openai",
            base_url=qwen_base_url,
            api_key=qwen_api_key,
            **kwargs,
        )
    model_name = model_name or "deepseek-chat"
    return LLMFactory.create(model=model_name, model_provider=model_provider, **kwargs)

UPLOAD_DIR = BACKEND_DIR / "data" / "cv"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/list-llm-models")
async def list_llm_models():
    try:
        models = []
        missing_models = []
        configured = None
        if _provider_is_configured(app_config.llm.provider):
            configured = {
                "model_name": app_config.llm.model_name,
                "model_provider": app_config.llm.provider,
                "model_status": "available",
            }
            models.append(configured)
        for item in AVAILABLE_LLM_MODELS:
            entry = dict(item)
            if _provider_is_configured(entry["model_provider"]):
                entry["model_status"] = "available"
                if entry not in models:
                    models.append(entry)
            else:
                entry["model_status"] = "missing_key"
                entry["setup_hint"] = _provider_setup_hint(entry["model_provider"])
                missing_models.append(entry)
        if not models:
            models = missing_models
        return {
            "models": models,
            "setup_required": not any(item.get("model_status") == "available" for item in models),
            "setup_hint": "No LLM API key is configured. Add DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, or QWEN_API_KEY to backend/.env, then restart the backend.",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})
        response = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=get_search_rag_manager(),
            use_search=True,
        )
        return {"response": response}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/refine-learning-goal")
async def refine_learning_goal(request: LearningGoalRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        refined_learning_goal = refine_learning_goal_with_llm(llm, request.learning_goal, request.learner_information)
        return refined_learning_goal
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/generate-learning-approach-assessment")
async def generate_learning_approach_assessment(request: LearningApproachAssessmentRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        assessment = generate_learning_approach_assessment_with_llm(
            llm,
            request.learning_goal,
            request.learner_information,
        )
        return {"learning_approach_assessment": assessment}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/update-learning-approach-state")
async def update_learning_approach_state(request: LearningApproachStateUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    session_information = request.session_information
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learner_interactions, str) and learner_interactions.strip():
            try:
                learner_interactions = ast.literal_eval(learner_interactions)
            except Exception:
                learner_interactions = {"raw": learner_interactions}
        if isinstance(session_information, str) and session_information.strip():
            session_information = ast.literal_eval(session_information)

        updated_profile = update_learning_approach_state_with_llm(
            llm,
            learner_profile,
            learner_interactions,
            session_information,
        )
        return {
            "learner_profile": updated_profile,
            "learning_approach_state": updated_profile.get("learning_preferences", {}).get("learning_approach_state"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/identify-skill-gap-with-info")
async def identify_skill_gap_with_info(request: SkillGapIdentificationRequest):
    print("\n" + "="*30)
    print("--- STEP 1: REQUEST RECEIVED ---")
    
    # 提前获取参数，防止后面报错
    model_provider = request.model_provider
    model_name = request.model_name
    learning_goal = request.learning_goal
    learner_information = request.learner_information
    skill_requirements = request.skill_requirements

    try:
        # 1. 检查环境变量
        import os
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            print("!!! WARNING: SERPER_API_KEY IS MISSING !!!")

        # 2. 初始化 LLM
        print(f"--- STEP 2: INITIALIZING LLM ({model_provider}) ---")
        llm = get_llm(model_provider, model_name)
        
        # 3. 处理技能需求数据格式
        print("--- STEP 3: PREPARING DATA ---")
        if isinstance(skill_requirements, str) and skill_requirements.strip():
            try:
                skill_requirements = ast.literal_eval(skill_requirements)
            except:
                pass 
        if not isinstance(skill_requirements, dict):
            skill_requirements = None

        # 4. 调用核心逻辑（这里是最容易崩的地方）
        print("--- STEP 4: CALLING AI LOGIC (NETWORKING...) ---")
        # 注意：这里可能需要加 await，取决于 identify_skill_gap_with_llm 是否是异步函数
        # 如果这个函数定义时带 async，就用 await；否则去掉 await
        skill_gaps, skill_requirements_res = identify_skill_gap_with_llm(
            llm, learning_goal, learner_information, skill_requirements
        )
        # --- 找到下面这一段并替换 ---
        print("--- STEP 5: SUCCESS ---")
        
        # 打印一下结果，方便我们在黑色窗口调试
        results = {
            "skill_gaps": skill_gaps,
            "skill_requirements": skill_requirements_res
        }
        print(f"DEBUG: Returning Data Keys -> {list(results.keys())}")
        
        return results # 这样返回，前端才能通过 goal["skill_gaps"] 找到数据


    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        print("\n" + "X"*50)
        print(f"!!! CRITICAL ERROR CAUGHT !!!")
        print(f"ERROR TYPE: {type(e).__name__}")
        print(f"ERROR MSG: {str(e)}")
        import traceback
        traceback.print_exc()  # 这一行会将真正的死穴打印在黑窗口里
        print("X"*50 + "\n")
        # 显式抛出异常给前端，防止前端报 KeyError
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/identify-skill-gap")
async def identify_skill_gap(goal: str = Form(...), cv: UploadFile = File(...), model_provider: str = Form("deepseek"), model_name: str = Form("deepseek-chat")):
    llm = get_llm(model_provider, model_name)
    mapper = SkillRequirementMapper(llm)
    skill_gap_identifier = SkillGapIdentifier(llm)
    try:
        safe_filename = Path(cv.filename or "uploaded_cv.pdf").name
        file_location = UPLOAD_DIR / safe_filename
        with open(file_location, "wb") as file_object:
            file_object.write(await cv.read())
        cv_text = extract_text_from_pdf(str(file_location))
        skill_requirements = mapper.map_goal_to_skill({
            "learning_goal": goal
        })
        skill_gaps = skill_gap_identifier.identify_skill_gap({
            "learning_goal": goal,
            "skill_requirements": skill_requirements,
            "learner_information": cv_text
        })
        results = {**skill_gaps, **skill_requirements}
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/create-learner-profile-with-info")
async def create_learner_profile_with_info(request: LearnerProfileInitializationWithInfoRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_information = request.learner_information
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    initial_learning_approach_state = request.initial_learning_approach_state
    try:
        if isinstance(learner_information, str):
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, learner_information, skill_gaps
        )
        if isinstance(initial_learning_approach_state, str) and initial_learning_approach_state.strip():
            initial_learning_approach_state = ast.literal_eval(initial_learning_approach_state)
        if isinstance(initial_learning_approach_state, dict) and initial_learning_approach_state:
            learner_profile = apply_learning_approach_state_snapshot_to_profile(
                learner_profile,
                initial_learning_approach_state,
            )
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit-diagnostic-assessment")
async def submit_diagnostic_assessment(request: DiagnosticAssessmentSubmissionRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    diagnostic_submission = request.diagnostic_submission
    learner_profile = request.learner_profile
    learner_information = request.learner_information
    try:
        if isinstance(skill_gaps, str) and skill_gaps.strip():
            skill_gaps = ast.literal_eval(skill_gaps)
        if isinstance(diagnostic_submission, str) and diagnostic_submission.strip():
            diagnostic_submission = ast.literal_eval(diagnostic_submission)
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        else:
            learner_profile = {}
        if isinstance(learner_information, str) and learner_information.strip():
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        else:
            learner_information = {}

        assessment_result = evaluate_and_apply_diagnostic_assessment_with_llm(
            llm,
            learning_goal,
            skill_gaps,
            diagnostic_submission,
        )
        updated_skill_gaps = assessment_result["skill_gaps"]

        updated_learner_profile = None
        if isinstance(learner_profile, dict) and learner_profile:
            learner_profile = normalize_learner_profile_levels(learner_profile)
            updated_learner_profile = sync_learner_profile_with_skill_gaps(
                learner_profile,
                updated_skill_gaps,
            )
            updated_learner_profile = normalize_learner_profile_levels(updated_learner_profile)
        elif isinstance(learner_information, dict) and learner_information:
            updated_learner_profile = initialize_learner_profile_with_llm(
                llm,
                learning_goal,
                learner_information,
                updated_skill_gaps,
            )
            updated_learner_profile = normalize_learner_profile_levels(updated_learner_profile)

        return {
            "evaluation": assessment_result.get("evaluation"),
            "skill_gaps": updated_skill_gaps,
            "learner_profile": updated_learner_profile,
        }
    except Exception as e:
        print("submit_diagnostic_assessment failed")
        print(f"learning_goal={learning_goal}")
        print(f"diagnostic_submission={diagnostic_submission}")
        print(f"error={type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-learner-profile")
async def create_learner_profile(request: LearnerProfileInitializationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    file_location = UPLOAD_DIR / Path(request.cv_path).name
    learner_information = extract_text_from_pdf(str(file_location))
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    try:
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, {"raw": learner_information}, skill_gaps
        )
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-learner-profile")
async def update_learner_profile(request: LearnerProfileUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    learner_information = request.learner_information
    session_information = request.session_information
    try:
        for name in ("learner_profile", "learner_interactions", "learner_information", "session_information"):
            val = locals()[name]
            if isinstance(val, str) and val.strip():
                try:
                    locals()[name] = ast.literal_eval(val)
                except Exception:
                    if name != "session_information":
                        locals()[name] = {"raw": val}
        learner_profile = update_learner_profile_with_llm(
            llm,
            locals()["learner_profile"],
            locals()["learner_interactions"],
            locals()["learner_information"],
            locals()["session_information"],
        )
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/schedule-learning-path")
async def schedule_learning_path(request: LearningPathSchedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_count = request.session_count
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        learning_path = schedule_learning_path_with_llm(llm, learner_profile, session_count)
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reschedule-learning-path")
async def reschedule_learning_path(request: LearningPathReschedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    session_count = request.session_count
    other_feedback = request.other_feedback
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(other_feedback, str) and other_feedback.strip():
            try:
                other_feedback = ast.literal_eval(other_feedback)
            except Exception:
                pass
        learning_path = reschedule_learning_path_with_llm(
            llm, learning_path, learner_profile, session_count, other_feedback
        )
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/explore-knowledge-points")
async def explore_knowledge_points(request: KnowledgePointExplorationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    if isinstance(learner_profile, str) and learner_profile.strip():
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learning_path, str) and learning_path.strip():
        learning_path = ast.literal_eval(learning_path)
    if isinstance(learning_session, str) and learning_session.strip():
        learning_session = ast.literal_eval(learning_session)
    try:
        knowledge_points = explore_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session)
        return knowledge_points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-point")
async def draft_knowledge_point(request: KnowledgePointDraftingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_point = request.knowledge_point
    use_search = request.use_search
    try:
        knowledge_draft = draft_knowledge_point_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_point, use_search)
        return {"knowledge_draft": knowledge_draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-points")
async def draft_knowledge_points(request: KnowledgePointsDraftingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    try:
        knowledge_drafts = draft_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, allow_parallel, use_search)
        return {"knowledge_drafts": knowledge_drafts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/integrate-learning-document")
async def integrate_learning_document(request: LearningDocumentIntegrationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_drafts = request.knowledge_drafts
    output_markdown = request.output_markdown
    try:
        learning_document = integrate_learning_document_with_llm(llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts, output_markdown)
        return {"learning_document": learning_document}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-document-quizzes")
async def generate_document_quizzes(request: KnowledgeQuizGenerationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_document = request.learning_document
    single_choice_count = request.single_choice_count
    multiple_choice_count = request.multiple_choice_count
    true_false_count = request.true_false_count
    short_answer_count = request.short_answer_count
    try:
        document_quiz = generate_document_quizzes_with_llm(llm, learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count)
        return {"document_quiz": document_quiz}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tailor-knowledge-content")
@app.post("/tailor-learning-content")
async def tailor_knowledge_content(request: TailoredContentGenerationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_path = request.learning_path
    learner_profile = request.learner_profile
    learning_session = request.learning_session
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    variant_types = request.variant_types
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(learning_session, str) and learning_session.strip():
            learning_session = ast.literal_eval(learning_session)
        if isinstance(variant_types, str) and variant_types.strip():
            try:
                variant_types = ast.literal_eval(variant_types)
            except Exception:
                variant_types = [variant_types]
        # Variant content generation should stay responsive and deterministic.
        # Disable retrieval augmentation here to avoid embedding/model-device failures.
        if isinstance(variant_types, list) and variant_types:
            use_search = False
        if isinstance(variant_types, list) and variant_types:
            tailored_variants = create_learning_content_variants_with_llm(
                llm,
                learner_profile,
                learning_path,
                learning_session,
                variant_types,
                allow_parallel=allow_parallel,
                with_quiz=with_quiz,
                use_search=use_search,
            )
            return {"tailored_content_variants": tailored_variants}
        tailored_content = create_learning_content_with_llm(
            llm, learner_profile, learning_path, learning_session, allow_parallel=allow_parallel, with_quiz=with_quiz, use_search=use_search
        )
        return {"tailored_content": tailored_content}
    except Exception as e:
        if request.model_provider == "deepseek" and "Insufficient Balance" in str(e) and request.model_name != "deepseek-v4-flash":
            try:
                fallback_llm = get_llm("deepseek", "deepseek-v4-flash")
                if isinstance(variant_types, list) and variant_types:
                    tailored_variants = create_learning_content_variants_with_llm(
                        fallback_llm,
                        learner_profile,
                        learning_path,
                        learning_session,
                        variant_types,
                        allow_parallel=allow_parallel,
                        with_quiz=with_quiz,
                        use_search=use_search,
                    )
                    return {"tailored_content_variants": tailored_variants}
                tailored_content = create_learning_content_with_llm(
                    fallback_llm,
                    learner_profile,
                    learning_path,
                    learning_session,
                    allow_parallel=allow_parallel,
                    with_quiz=with_quiz,
                    use_search=use_search,
                )
                return {"tailored_content": tailored_content}
            except Exception as fallback_error:
                e = fallback_error
        print("tailor_knowledge_content failed")
        print(f"variant_types={variant_types}")
        print(f"learning_session={learning_session}")
        print(f"error={type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    server_cfg = app_config.get("server", {})
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = int(app_config.get("server", {}).get("port", 5018))
    log_level = str(app_config.get("log_level", "debug")).lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level)

