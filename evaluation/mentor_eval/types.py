from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class JobRecord:
    id: str
    title: str
    description: str
    required_skills: List[str] = field(default_factory=list)
    prerequisite_skills: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)

    @property
    def category(self) -> str:
        return self.source.get("_category", "General")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResumeRecord:
    id: str
    text: str
    claimed_skills: List[str] = field(default_factory=list)
    actual_skills: List[str] = field(default_factory=list)
    foundation_skills: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearnerCase:
    case_id: str
    job: JobRecord
    resume: ResumeRecord
    category: str
    learning_goal: str
    # `presented_info` is what the learner tells the system.
    presented_info: str
    # `true_knowledge` is the learner's actual knowledge/state.
    true_knowledge: Dict[str, Any]
    # Backwards-compatible fields
    learner_information: str
    ground_truth: Dict[str, Any]
    behavior_trace: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["job"] = self.job.to_dict()
        data["resume"] = self.resume.to_dict()
        return data
