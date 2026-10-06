from typing import Any
from agent.agent import Agent
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
from dataclasses import dataclass
from pydantic import BaseModel, Field


class SubagentParams(BaseModel):
    goal: str = Field(
        ..., description="子代理要完成的具体任务或目标"
    )


@dataclass
class SubagentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600


class SubagentTool(Tool):
    def __init__(self, config: Config, definition: SubagentDefinition):
        super().__init__(config)
        self.definition = definition

    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"subagent_{self.definition.description}"

    schema = SubagentParams

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return True

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = SubagentParams(**invocation.params)

        if not params.goal:
            return ToolResult.error_result("未为子代理指定目标")

        config_dict = self.config.to_dict()

        try:
            async with Agent() as agent:
        except Exception as e:
            ...
