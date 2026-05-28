from enum import Enum
from typing import List

from pydantic import BaseModel, Field, RootModel, field_validator


class LevelRequired(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class LevelCurrent(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AssessmentLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class DiagnosticQuestion(BaseModel):
    question: str
    expected_answer: str
    assessment_focus: str = Field(..., description="What this question verifies.")


class DiagnosticQuestionSet(BaseModel):
    level: AssessmentLevel
    questions: List[DiagnosticQuestion]

    @field_validator("questions")
    @classmethod
    def validate_question_count(cls, v: List[DiagnosticQuestion]):
        if not (2 <= len(v) <= 3):
            raise ValueError("Each mastery level must contain between 2 and 3 diagnostic questions.")
        return v


class SkillDiagnosticAssessment(BaseModel):
    skill_name: str
    question_sets: List[DiagnosticQuestionSet]

    @field_validator("question_sets")
    @classmethod
    def validate_level_coverage(cls, v: List[DiagnosticQuestionSet]):
        expected = {"beginner", "intermediate", "advanced"}
        actual = {item.level.value for item in v}
        if actual != expected:
            raise ValueError("Diagnostic assessment must cover beginner, intermediate, and advanced levels.")
        return v


class DiagnosticAnswerItem(BaseModel):
    level: AssessmentLevel
    question: str
    expected_answer: str
    learner_answer: str


class SkillDiagnosticAssessmentSubmission(BaseModel):
    skill_name: str
    answers: List[DiagnosticAnswerItem]

    @field_validator("answers")
    @classmethod
    def ensure_answers_present(cls, v: List[DiagnosticAnswerItem]):
        if len(v) < 6:
            raise ValueError("Diagnostic submission must include the answered diagnostic questions.")
        return v


class LevelEvaluation(BaseModel):
    level: AssessmentLevel
    score: int = Field(..., ge=0, le=100)
    demonstrated: bool
    rationale: str


class DiagnosticAssessmentEvaluation(BaseModel):
    skill_name: str
    evaluated_level: LevelCurrent
    level_evaluations: List[LevelEvaluation]
    overall_summary: str
    recommended_current_level: LevelCurrent

    @field_validator("level_evaluations")
    @classmethod
    def validate_level_evaluations(cls, v: List[LevelEvaluation]):
        expected = {"beginner", "intermediate", "advanced"}
        actual = {item.level.value for item in v}
        if actual != expected:
            raise ValueError("Evaluation must cover beginner, intermediate, and advanced levels.")
        return v


class SkillRequirement(BaseModel):
    name: str = Field(..., description="Actionable, concise skill name.")
    required_level: LevelRequired


class SkillRequirements(BaseModel):
    skill_requirements: List[SkillRequirement]

    @field_validator("skill_requirements")
    @classmethod
    def validate_length_and_uniqueness(cls, v: List[SkillRequirement]):
        if not (1 <= len(v) <= 10):
            raise ValueError("Number of skill requirements must be within 1 to 10.")
        seen = set()
        for item in v:
            key = item.name.strip().lower()
            if key in seen:
                raise ValueError(f'Duplicate skill name detected: "{item.name}".')
            seen.add(key)
        return v


class SkillGap(BaseModel):
    name: str
    is_gap: bool
    required_level: LevelRequired
    current_level: LevelCurrent
    reason: str = Field(..., description="20 words or fewer concise rationale for current level.")
    level_confidence: Confidence
    mentioned_in_learner_information: bool = False
    inferred_from_learner_context: bool = False
    learner_context_evidence: str | None = None
    requires_diagnostic_assessment: bool = False
    assessment_reason: str | None = None
    diagnostic_assessment: SkillDiagnosticAssessment | None = None
    diagnostic_assessment_result: DiagnosticAssessmentEvaluation | None = None

    @field_validator("reason")
    @classmethod
    def limit_reason_words(cls, v: str) -> str:
        words = v.split()
        if len(words) > 20:
            raise ValueError("Reason must be 20 words or fewer.")
        return v

    @field_validator("assessment_reason")
    @classmethod
    def limit_assessment_reason_words(cls, v: str | None) -> str | None:
        if v is None:
            return v
        words = v.split()
        if len(words) > 25:
            raise ValueError("Assessment reason must be 25 words or fewer.")
        return v

    @field_validator("learner_context_evidence")
    @classmethod
    def limit_context_evidence_words(cls, v: str | None) -> str | None:
        if v is None:
            return v
        words = v.split()
        if len(words) > 25:
            raise ValueError("Learner context evidence must be 25 words or fewer.")
        return v

    @field_validator("is_gap")
    @classmethod
    def check_gap_consistency(cls, is_gap_value, info):
        data = info.data
        required = data.get("required_level")
        current = data.get("current_level")
        if required is None or current is None:
            return is_gap_value
        order = {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3}
        gap_should_be = order[current.value] < order[required.value]
        if is_gap_value != gap_should_be:
            raise ValueError(
                f'is_gap inconsistency: required="{required.value}", current="{current.value}" implies is_gap={gap_should_be}.'
            )
        return is_gap_value

    @field_validator("requires_diagnostic_assessment")
    @classmethod
    def ensure_assessment_flag_matches_mentions(cls, v: bool, info):
        mentioned = info.data.get("mentioned_in_learner_information")
        inferred = info.data.get("inferred_from_learner_context")
        if v and not (mentioned or inferred):
            raise ValueError(
                "requires_diagnostic_assessment can only be true when the skill is mentioned or inferred from learner context."
            )
        return v


class SkillGaps(BaseModel):
    skill_gaps: List[SkillGap]

    @field_validator("skill_gaps")
    @classmethod
    def limit_length_and_names(cls, v: List[SkillGap]):
        if not (1 <= len(v) <= 10):
            raise ValueError("Number of skill gaps must be within 1 to 10.")
        seen = set()
        for item in v:
            key = item.name.strip().lower()
            if key in seen:
                raise ValueError(f'Duplicate skill name detected: "{item.name}".')
            seen.add(key)
        return v


class SkillGapsRoot(RootModel):
    root: List[SkillGap]


class RefinedLearningGoal(BaseModel):
    refined_goal: str
