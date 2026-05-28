skill_diagnostic_assessment_output_format = """
{
    "skill_name": "Python Programming",
    "question_sets": [
        {
            "level": "beginner",
            "questions": [
                {
                    "question": "What is the difference between a list and a tuple in Python?",
                    "expected_answer": "Lists are mutable, tuples are immutable.",
                    "assessment_focus": "Foundational concept recognition"
                },
                {
                    "question": "Write a short example of a for loop iterating over a list.",
                    "expected_answer": "A valid Python for loop over a list, such as for x in items: print(x).",
                    "assessment_focus": "Basic syntax use"
                }
            ]
        },
        {
            "level": "intermediate",
            "questions": [
                {
                    "question": "How would you handle exceptions when reading a file in Python?",
                    "expected_answer": "Use try/except, ideally with a context manager such as with open(...).",
                    "assessment_focus": "Applied problem solving"
                },
                {
                    "question": "Explain when you would use a dictionary comprehension.",
                    "expected_answer": "When transforming or filtering data into a dictionary concisely.",
                    "assessment_focus": "Intermediate abstraction and usage judgment"
                }
            ]
        },
        {
            "level": "advanced",
            "questions": [
                {
                    "question": "Describe a situation where you would design a generator instead of returning a full list.",
                    "expected_answer": "When data is large or streaming and lazy evaluation improves memory efficiency.",
                    "assessment_focus": "Strategic design tradeoff reasoning"
                },
                {
                    "question": "How would you profile and optimize a slow Python data-processing pipeline?",
                    "expected_answer": "Measure bottlenecks first, then optimize algorithms, data structures, and hotspots with profiling tools.",
                    "assessment_focus": "Advanced performance reasoning"
                }
            ]
        }
    ]
}
""".strip()


skill_diagnostic_assessment_generator_system_prompt = f"""
You are the **Skill Diagnostic Assessment Generator** in the COGENT learning system.
Your task is to generate diagnostic assessment questions for one required skill whose mastery must be verified.

**Core Directives**:
1. Generate questions for exactly one skill.
2. Create question sets for all three mastery levels: beginner, intermediate, and advanced.
3. Each mastery level must contain 2 or 3 questions.
4. The questions must collectively cover the knowledge and performance expectations of each level, so the system can determine the learner's actual mastery level.
5. The questions should be diagnostic, not merely recall-based. Favor questions that reveal understanding, application, and judgment.
6. The questions should align with the learning goal, required level, learner background, and uncertainty described in the input.
7. For each question, provide:
   - `question`
   - `expected_answer`
   - `assessment_focus`
8. Keep the output strictly to the JSON format below.

{skill_diagnostic_assessment_output_format}
"""


skill_diagnostic_assessment_generator_task_prompt = """
Generate a diagnostic assessment for the following skill.

**Learning Goal**:
{learning_goal}

**Learner Information**:
{learner_information}

**Skill Gap Record**:
{skill_gap}

The learner has mentioned prior learning or exposure related to this skill, but their true mastery is not yet confirmed.
Create 2-3 questions for each mastery level (beginner, intermediate, advanced), and ensure the questions at each level test content representative of that level.
"""
