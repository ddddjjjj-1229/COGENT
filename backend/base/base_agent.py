from typing import Any, Dict, Optional

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from utils.language import build_language_instruction
from utils.llm_output import preprocess_response
from langchain.agents.middleware.types import _InputAgentState

valid_agent_arg_list = [
    "middleware",
    "response_format",
    "state_schema",
    "context_schema",
    "checkpointer",
    "store",
    "interrupt_before",
    "interrupt_after",
    "debug",
    "name",
    "cache"
]


class BaseAgent:

    def __init__(
            self,
            model: BaseChatModel,
            system_prompt: Optional[str] = None,
            tools: Optional[list[Any]] = None,
            **kwargs
        ) -> None:
        """Initialize a base agent with JSON output and validation."""
        self._model = model
        self._system_prompt = system_prompt
        self._tools = tools
        self._agent_kwargs = {k: v for k, v in kwargs.items() if k in valid_agent_arg_list}
        self._agent = self._build_agent()
        self.exclude_think = kwargs.get("exclude_think", True)
        self.jsonalize_output = kwargs.get("jsonalize_output", True)

    def _build_agent(self):
        return create_agent(
            model=self._model,
            tools=self._tools,
            system_prompt=self._system_prompt,
            **self._agent_kwargs,
        )

    def set_prompts(self, system_prompt: Optional[str] = None, task_prompt: Optional[str] = None) -> None:
        """Set or update system/task prompts and rebuild the internal agent if needed."""
        if system_prompt is not None:
            self._system_prompt = system_prompt
        if task_prompt is not None:
            self._task_prompt = task_prompt
        self._agent = self._build_agent()

    def _build_prompt(self, variables: Dict[str, Any], task_prompt: Optional[str] = None) -> _InputAgentState:
        """Build chat messages for model call."""
        assert task_prompt is not None, "Either self._task_prompt or task_prompt must be provided."
        task_prompt = task_prompt
        formatted_task = task_prompt.format(**variables)  # type: ignore[union-attr]
        formatted_task = f"{formatted_task}\n{build_language_instruction(variables)}"
        prompt = {
            "messages": [
                {"role": "user", "content": formatted_task}
            ]
        }
        return prompt

    def invoke(self, input_dict: dict, task_prompt: Optional[str] = None) -> Any:
        """Invoke the agent with the given input text."""
        input_prompt = self._build_prompt(input_dict, task_prompt=task_prompt)
        raw_output = self._agent.invoke(input_prompt)
        output = preprocess_response(
            raw_output, only_text=True, exclude_think=self.exclude_think, json_output=self.jsonalize_output
        )
        return output

    def invoke_raw(self, input_dict: dict, task_prompt: Optional[str] = None) -> str:
        """Invoke the agent and always return plain text without JSON parsing."""
        input_prompt = self._build_prompt(input_dict, task_prompt=task_prompt)
        raw_output = self._agent.invoke(input_prompt)
        output = preprocess_response(
            raw_output,
            only_text=True,
            exclude_think=self.exclude_think,
            json_output=False,
        )
        return str(output)
