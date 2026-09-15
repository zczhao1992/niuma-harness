from __future__ import annotations
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from client.llm_client import LLMClient
from client.response import StreamEventType
from context.manager import ContextManager
from tools.registry import create_default_registry


class Agent:
    """Agent 核心类

    负责管理与大模型的交互、智能体主循环 (Agentic Loop) 以及事件流的调度生成。
    """

    def __init__(self):
        """初始化 Agent 实例，延迟加载 LLM 客户端与上下文管理器。"""
        self.client = LLMClient()
        self.context_manager = ContextManager()
        self.tool_registry = create_default_registry()

    async def run(self, message: str):
        """运行 Agent 主逻辑入口，对外暴露标准的事件流接口。

         Args:
             message (str): 用户输入的提示词、指令或提问内容。

         Yields:
             AgentEvent: 智能体生命周期事件流（如 AGENT_START、TEXT_DELTA、TEXT_COMPLETE、AGENT_END 等）。
         """
        # 1. 产出智能体启动事件，通知上层UI/终端任务开始
        yield AgentEvent.agent_start(message)

        # 2. 将当前用户输入追加至上下文历史管理系统中
        self.context_manager.add_user_message(message)

        final_response: str | None = None
        # 3. 委托给内部的 _agentic_loop 处理具体的 LLM 交互与事件转换
        async for event in self._agentic_loop():
            yield event
            # 捕获单轮完整回复事件，提取最终文本内容
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
        # 4. 产出智能体终结事件，带上最终回复结果
        yield AgentEvent.agent_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        """智能体内部驱动循环 (Think-Act-Observe Loop)。

        监听 LLMClient 的底层 API 流式响应，负责：
        - 文本增量 (TEXT_DELTA) 的实时事件转换与拼接。
        - 异常错误 (ERROR) 的捕获与事件包装。
        - 轮次结束后助手回复 (Assistant Message) 的上下文回写。

        Yields:
            AgentEvent: 转换后的上层业务事件。
        """
        response_text = ""

        tool_schemas = self.tool_registry.get_schemas()

        # 开启流式响应，监听底层的 StreamEvent
        async for event in self.client.chat_completion(
                self.context_manager.get_messages(),
                tools=tool_schemas if tool_schemas else None,
        ):
            print(event)

            # 接收到模型增量输出文本
            if event.type == StreamEventType.TEXT_DELTA:
                if event.text_delta:
                    content = event.text_delta.content
                    response_text += content
                    yield AgentEvent.text_delta(content)
            # 触发异常/错误响应
            elif event.type == StreamEventType.ERROR:
                yield AgentEvent.agent_error(event.error or "Unknown error occurred.")
        # 轮次结束：将 LLM 生成的完整回复保存进上下文历史，维持多轮对话记忆
        self.context_manager.add_assistant_message(response_text or None)

        if response_text:
            yield AgentEvent.text_complete(response_text)

    async def __aenter__(self) -> Agent:
        """异步上下文管理器入口。

        支持使用 `async with Agent() as agent:` 方式安全调用。
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口。

        在退出 `async with` 作用域时自动触发，确保底层的 HTTP 会话与连接句柄被安全释放。
        """
        if self.client:
            await self.client.close()
            self.client = None
