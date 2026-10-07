import asyncio
from typing import Any

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
        from agent.agent import Agent
        from agent.events import AgentEventType

        params = SubagentParams(**invocation.params)

        if not params.goal:
            return ToolResult.error_result("未为子代理指定目标")

        config_dict = self.config.to_dict()
        config_dict["max_turns"] = self.definition.max_turns

        if self.definition.allowed_tools:
            config_dict["allowed_tools"] = self.definition.allowed_tools

        subagent_config = Config(**config_dict)

        prompt = f"""你是一个专门的子代理，肩负着特定的任务。

        {self.definition.goal_prompt}

        你的任务：
        {params.goal}

        重要提示：
        - 仅专注于完成指定任务
        - 不要从事无关的行为
        - 一旦你完成任务或得出答案，请提供你的最终回复
        - 输出结果要简洁明了
        """

        tool_calls = []
        final_response = None
        error = None
        terminate_response = "goal"

        try:
            async with Agent(subagent_config) as agent:
                deadline = (
                    asyncio.get_event_loop().time() + self.definition.timeout_seconds
                )

                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time() > deadline:
                        terminate_response = "timeout"
                        final_response = "Sub-agent timed out"
                        break

                    if event.type == AgentEventType.TOOL_CALL_START:
                        tool_calls.append(event.data.get("name"))
                    elif event.type == AgentEventType.TEXT_COMPLETE:
                        final_response = event.data.get("content")
                    elif event.type == AgentEventType.AGENT_END:
                        if final_response is None:
                            final_response = event.data.get("response")
                    elif event.type == AgentEventType.AGENT_ERROR:
                        terminate_response = "error"
                        error = event.data.get("error", "Unknown")
                        final_response = f"子agent错误: {error}"
                        break
        except Exception as e:
            terminate_response = "error"
            error = str(e)
            final_response = f"子agent 失败: {e}"

        result = f"""子agent '{self.definition.name}' 完成. 
        终止: {terminate_response}
        调用工具: {', '.join(tool_calls) if tool_calls else 'None'}

        结果:
        {final_response or '无响应'}
        """

        if error:
            return ToolResult.error_result(result)

        return ToolResult.success_result(result)


CODEBASE_INVESTIGATOR = SubagentDefinition(
    name="codebase_investigator",
    description="调查代码库，以回答有关代码结构、模式和实现的问题",
    goal_prompt="""你是一名代码库调查专家。
你的工作是探索和理解代码，以回答问题。
使用read_file、grep、glob和list_dir进行调查。
请勿修改任何文件。""",
    allowed_tools=["read_file", "grep", "glob", "list_dir"],
)

CODE_REVIEWER = SubagentDefinition(
    name="code_reviewer",
    description="审查代码变更，并就质量、错误和改进提供反馈",
    goal_prompt="""你是一名代码审查专家。
你的工作是审查代码并提供建设性反馈。
查找漏洞、代码异味、安全问题以及改进机会。
使用read_file、list_dir和grep来检查代码。
请勿修改任何文件。""",
    allowed_tools=["read_file", "grep", "list_dir"],
    max_turns=10,
    timeout_seconds=300,
)


def get_default_subagent_definitions() -> list[SubagentDefinition]:
    return [
        CODEBASE_INVESTIGATOR,
        CODE_REVIEWER,
    ]
