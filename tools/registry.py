from pathlib import Path
from typing import Any
from tools.base import Tool, ToolInvocation, ToolResult
import logging

from tools.builtin import ReadFileTool, get_all_builtin_tools
# from tools.builtin.write_file import WriteFileTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心。

    负责管理 Agent 系统中所有可用工具的注册、注销、查找、Schema 统一导出以及调度执行。
    作为 LLM 与具象工具 (Tools) 之间的中介层 (Mediator)。
    """

    def __init__(self):
        """初始化工具注册中心，建立底层工具映射表。"""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个新的工具到注册中心。

        若存在同名工具，将覆盖旧工具并打印警告日志。

        Args:
            tool (Tool): 实现了 Tool 基类的工具实例。
        """
        if tool.name in self._tools:
            logger.warning(f"覆盖现有工具: {tool.name}")

        self._tools[tool.name] = tool
        logger.debug(f"注册工具: {tool.name}")

    def unregister(self, name: str) -> bool:
        """根据工具名称注销/移除已注册的工具。

        Args:
            name (str): 待注销的工具唯一标识名称。

        Returns:
            bool: 移除成功返回 True; 若工具不存在则返回 False。
        """
        if name in self._tools:
            del self._tools[name]
            return True

        return False

    def get(self, name: str) -> Tool | None:
        """根据名称获取对应的工具实例。

        Args:
            name (str): 工具名称。

        Returns:
            Tool | None: 找到的工具实例，若未匹配到则返回 None。
        """
        if name in self._tools:
            return self._tools[name]
        return None

    def get_tools(self) -> list[Tool]:
        """获取当前已注册的所有工具列表。

        Returns:
            list[Tool]: 已注册工具实例的列表。
        """
        tools: list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)

        return tools

    def get_schemas(self) -> list[dict[str, Any]]:
        """获取所有已注册工具的 OpenAI 函数调用 (Function Calling) JSON Schema 集合。

        用于在向大模型 (LLM) 发送请求时，通过 `tools` 参数注入工具定义。

        Returns:
            list[dict[str, Any]]: 符合 OpenAI 格式规范的 Tool Schema 字典列表。
        """
        return [tool.to_openai_schema() for tool in self.get_tools()]

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path | None):
        """统一调度并异步执行指定的工具。

        包含工具存在性检查、输入参数 Schema 预校验、上下文构造以及异常结果包装。

        Args:
            name (str): 拟调用的工具名称。
            params (dict[str, Any]): 大模型生成的实参字典。
            cwd (Path | None, optional): 工具运行的上下文工作目录。默认为 None。

        Returns:
            ToolResult: 统一的工具执行结果（包含成功输出或错误摘要）。
        """
        # 1. 检索工具是否存在
        tool = self.get(name)
        if tool is None:
            return ToolResult.error_result(f"错误工具: {name}", metadata={"tool_name": name})

        # 2. 参数 Schema 预校验
        validation_errors = tool.validate_params(params)
        if validation_errors:
            return ToolResult.error_result(
                f"参数错误: {'; '.join(validation_errors)}",
                metadata={
                    "tool_name": name,
                    "validation_errors": validation_errors
                }
            )
        # 3. 构造调用上下文 (Invocation Context)
        invocation = ToolInvocation(
            params=params,
            cwd=cwd
        )
        try:
            # 4. 执行工具逻辑
            await tool.execute(invocation)
        except Exception as e:
            logger.exception(f"工具 {name} 抛出异常")
            return ToolResult.error_result(f"错误: {str(e)}", metadata={"tool_name", name})


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    for tool_class in get_all_builtin_tools():
        registry.register(tool_class())

    return registry
