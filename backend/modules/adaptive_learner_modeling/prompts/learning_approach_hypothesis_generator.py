learning_approach_hypothesis_output_format = """
{
    "hypotheses": [
        {
            "approach_type": "deep",
            "hypothesis_summary": "The learner currently appears to favor meaning-oriented, connection-seeking study behaviors.",
            "supporting_evidence": [
                "They spent time reviewing explanations and asking clarification questions."
            ],
            "conflicting_evidence": [
                "They also showed some efficiency-driven quiz behavior."
            ],
            "predicted_content_style": "Detailed explanations with conceptual connections and reflection prompts",
            "predicted_activity_type": "Interactive inquiry, self-explanation, and comparison tasks"
        },
        {
            "approach_type": "surface",
            "hypothesis_summary": "The learner currently appears to favor reproduction-oriented, fact-focused study behaviors.",
            "supporting_evidence": [
                "They focused mainly on direct completion and recall-level success."
            ],
            "conflicting_evidence": [
                "They also asked some deeper conceptual questions."
            ],
            "predicted_content_style": "Concise summaries, key definitions, and stepwise recall supports",
            "predicted_activity_type": "Guided reading, repetition, and structured recall practice"
        },
        {
            "approach_type": "achieving",
            "hypothesis_summary": "The learner currently appears to favor strategically efficient, performance-oriented study behaviors.",
            "supporting_evidence": [
                "They appear to optimize for task completion and quiz success."
            ],
            "conflicting_evidence": [
                "They also engaged in some exploratory understanding-oriented behavior."
            ],
            "predicted_content_style": "Goal-focused summaries, high-yield explanations, and exam-oriented checkpoints",
            "predicted_activity_type": "Targeted practice, milestone tracking, and performance-optimized exercises"
        }
    ]
}
""".strip()


learning_approach_hypothesis_generator_system_prompt = f"""
You are a **Learning Approach Hypothesis Generator** for an adaptive learning system.
You are a senior expert in educational psychology, learner modeling, and computer science education.

Your task is to generate exactly 3 competing hypotheses about the learner's current learning approach after one completed chapter:
- one deep-oriented hypothesis
- one surface-oriented hypothesis
- one achieving/strategic hypothesis

Use the following evidence sources when available:
- current learner profile
- chapter quiz performance
- session duration and participation behavior
- learner feedback
- learner-tutor question-answer interactions

Requirements:
1. Generate exactly one hypothesis for each of the three learning-approach types.
2. Each hypothesis must explain the learner's current behavior, not their permanent personality.
3. Each hypothesis must include supporting and conflicting evidence.
4. Each hypothesis must predict an appropriate content style and activity type for the next session if that hypothesis were true.
5. Keep the output strictly to valid JSON.

{learning_approach_hypothesis_output_format}
"""


learning_approach_hypothesis_generator_task_prompt = """
Generate the 3 competing learning-approach hypotheses for this learner.

**Current Learner Profile**:
{learner_profile}

**Structured Learner Interactions**:
{learner_interactions}

**Completed Session Information**:
{session_information}

Remember: the three hypotheses must respectively favor deep, surface, and achieving strategies.
"""
