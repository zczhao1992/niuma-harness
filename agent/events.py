from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

from client.response import TokenUsage


class AgentEventType(str, Enum):
    """
    智能体事件类型枚举。
    定义了 Agent 在整个生命周期及运行过程中可能抛出的所有标准事件类型。
    继承自 `str` 以确保在序列化（如 JSON/SSE 传输）时可以直接作为字符串处理。
    """

    # --- Agent 整体生命周期事件 ---
    AGENT_START = "agent_start"  # Agent 任务接收并开始执行
    AGENT_END = "agent_end"      # Agent 任务整体执行结束
    AGENT_ERROR = "agent_error"  # Agent 运行过程中发生不可逆或需上报的错误

    # --- 流式文本输出事件 ---
    TEXT_DELTA = "text_delta"    # 大模型实时返回的增量文本片段（用于打字机流式渲染）
    TEXT_COMPLETE = "text_complete"  # 本轮文本生成完毕，包含拼接后的完整文本内容


@dataclass
class AgentEvent:
    """智能体统一事件对象。

    作为 Agent 内部与外部UI/应用层通信的标准数据载体。
    推荐使用类方法 (Factory Methods) 快捷构造具体的事件实例。
    """
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls, message: str) -> AgentEvent:
        """构造 Agent 启动事件。

        Args:
            message (str): 用户本次传入的原始指令或提示词。

        Returns:
            AgentEvent: 包含了用户原始输入的 AGENT_START 类型事件。
        """
        return cls(
            type=AgentEventType.AGENT_START,
            data={"message": message}
        )

    @classmethod
    def agent_end(cls, response: str | None = None, usage: TokenUsage | None = None) -> AgentEvent:
        """构造 Agent 任务完成终结事件。

        Args:
            response (str | None): Agent 最终输出给用户的完整文本回复。
            usage (TokenUsage | None): 本轮交互消耗的 Token 统计信息（可选）。

        Returns:
            AgentEvent: 包含了最终回复和 Token 信息的 AGENT_END 类型事件。
        """
        return cls(
            type=AgentEventType.AGENT_END,
            data={"response": response, "usage": usage.__dict__ if usage else None}
        )

    @classmethod
    def agent_error(cls, error: str, details: dict[str, Any] | None = None) -> AgentEvent:
        """构造 Agent 运行错误事件。

        Args:
            error (str): 简要的错误信息说明。
            details (dict[str, Any] | None): 错误的详细上下文或堆栈信息（可选）。

        Returns:
            AgentEvent: 包含了错误详情的 AGENT_ERROR 类型事件。
        """
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={"error": error, "details": details or {}}
        )

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        """构造增量文本输出事件（用于打字机效果）。

        Args:
            content (str): 本次增量返回的一小块文本片段 (Text Chunk)。

        Returns:
            AgentEvent: 包含了增量文本的 TEXT_DELTA 类型事件。
        """
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={"content": content}
        )

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        """构造单轮文本生成完毕事件。

        Args:
            content (str): 本轮交互生成的完整拼接文本内容。

        Returns:
            AgentEvent: 包含了完整文本的 TEXT_COMPLETE 类型事件。
        """
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={"content": content}
        )
