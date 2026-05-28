from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field, field_validator


class RequiredLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class CurrentLevel(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class LearningApproachType(str, Enum):
    deep = "deep"
    surface = "surface"
    achieving = "achieving"


class MasteredSkill(BaseModel):
    name: str
    proficiency_level: RequiredLevel


class InProgressSkill(BaseModel):
    name: str
    required_proficiency_level: RequiredLevel
    current_proficiency_level: CurrentLevel


class CognitiveStatus(BaseModel):
    overall_progress: int = Field(..., ge=0, le=100)
    mastered_skills: List[MasteredSkill] = Field(default_factory=list)
    in_progress_skills: List[InProgressSkill] = Field(default_factory=list)
    mastery_evidence: List[dict] = Field(default_factory=list)


class LearningPreferences(BaseModel):
    content_style: str
    activity_type: str
    additional_notes: str | None = None
    learning_approach_state: LearningApproachState | None = None


class BehavioralPatterns(BaseModel):
    system_usage_frequency: str
    session_duration_engagement: str
    motivational_triggers: str | None = None
    additional_notes: str | None = None


class LearningApproachOption(BaseModel):
    label: str
    text: str
    maps_to: LearningApproachType


class LearningApproachQuestion(BaseModel):
    question: str
    scenario_focus: str
    options: List[LearningApproachOption]

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: List[LearningApproachOption]):
        if len(v) != 3:
            raise ValueError("Each learning approach question must contain exactly 3 options.")
        expected = {"deep", "surface", "achieving"}
        actual = {item.maps_to.value for item in v}
        if actual != expected:
            raise ValueError("Each question must contain one option for deep, surface, and achieving strategies.")
        return v


class LearningApproachAssessment(BaseModel):
    assessment_purpose: str
    questions: List[LearningApproachQuestion]

    @field_validator("questions")
    @classmethod
    def validate_question_count(cls, v: List[LearningApproachQuestion]):
        if not (6 <= len(v) <= 12):
            raise ValueError("Learning approach assessment must contain between 6 and 12 questions.")
        return v


class LearningApproachHypothesis(BaseModel):
    approach_type: LearningApproachType
    hypothesis_summary: str
    supporting_evidence: List[str] = Field(default_factory=list)
    conflicting_evidence: List[str] = Field(default_factory=list)
    predicted_content_style: str
    predicted_activity_type: str


class LearningApproachHypothesisSet(BaseModel):
    hypotheses: List[LearningApproachHypothesis]

    @field_validator("hypotheses")
    @classmethod
    def validate_hypothesis_set(cls, v: List[LearningApproachHypothesis]):
        if len(v) != 3:
            raise ValueError("Exactly 3 learning-approach hypotheses are required.")
        expected = {"deep", "surface", "achieving"}
        actual = {item.approach_type.value for item in v}
        if actual != expected:
            raise ValueError("Hypothesis set must contain deep, surface, and achieving hypotheses.")
        return v


class LearningApproachMetricScores(BaseModel):
    C_history: int = Field(..., ge=0, le=100)
    C_behavior_fit: int = Field(..., ge=0, le=100)
    C_transition_plausibility: int = Field(..., ge=0, le=100)
    C_context_adjusted_fit: int = Field(..., ge=0, le=100)


class LearningApproachAdaptiveWeights(BaseModel):
    C_history: float = Field(..., ge=0, le=1)
    C_behavior_fit: float = Field(..., ge=0, le=1)
    C_transition_plausibility: float = Field(..., ge=0, le=1)
    C_context_adjusted_fit: float = Field(..., ge=0, le=1)

    @field_validator("C_context_adjusted_fit")
    @classmethod
    def validate_total_weight(cls, v: float, info):
        data = info.data
        total = (
            float(data.get("C_history", 0))
            + float(data.get("C_behavior_fit", 0))
            + float(data.get("C_transition_plausibility", 0))
            + float(v)
        )
        if abs(total - 1.0) > 0.05:
            raise ValueError("Adaptive weights should sum approximately to 1.")
        return v


class LearningApproachHypothesisEvaluation(BaseModel):
    approach_type: LearningApproachType
    metric_scores: LearningApproachMetricScores
    adaptive_weights: LearningApproachAdaptiveWeights
    weighted_score: float = Field(..., ge=0, le=100)
    rationale: str


class LearningApproachState(BaseModel):
    dominant_type: LearningApproachType
    distribution: Dict[str, float]
    confidence: str
    evidence_summary: str
    candidate_types_for_next_session: List[LearningApproachType] = Field(default_factory=list)
    latest_hypothesis_evaluations: List[LearningApproachHypothesisEvaluation] = Field(default_factory=list)
    history: List[Dict[str, object]] = Field(default_factory=list)


class LearnerProfile(BaseModel):
    learner_information: str
    learning_goal: str
    cognitive_status: CognitiveStatus
    learning_preferences: LearningPreferences
    behavioral_patterns: BehavioralPatterns

    @field_validator("learning_goal")
    @classmethod
    def ensure_nonempty_goal(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("learning_goal must be non-empty")
        return v
