from pathlib import Path
from typing import Any
from tools.base import Tool, ToolInvocation, ToolResult
import logging

logger = logging.gerLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"覆盖现有工具: {tool.name}")

        self._tools[tool.name] = tool
        logger.debug(f"注册工具: {tool.name}")

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True

        return False

    def get(self, name: str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        return None

    def get_tools(self) -> list[Tool]:
        tools: list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)

        return tools

    def get_shcemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path | None):
        tool = self.get(name)
        if tool in None:
            return ToolResult.error_result(f"错误工具: {name}", metadata={"tool_name": name})

        validation_errors = tool.validate_params(params)
        if validation_errors:
            return ToolResult.error_result(
                f"参数错误: {'; '.join(validation_errors)}",
                metadata={
                    "tool_name": name,
                    "validation_errors": validation_errors
                }
            )

        invocation = ToolInvocation(
            params=params,
            cwd=cwd
        )
        await tool.execute()
