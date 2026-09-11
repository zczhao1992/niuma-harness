from __future__ import annotations
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from client.llm_client import LLMClient
from client.response import StreamEventType
from context.manager import ContextManager


class Agent:
    """Agent 核心类

    负责管理与大模型的交互、智能体主循环 (Agentic Loop) 以及事件流的调度生成。
    """

    def __init__(self):
        """初始化 Agent, 实例化底层的异步 LLM 客户端"""
        self.client = LLMClient()
        self.context_manager = ContextManager()

    async def run(self, message: str):
        """运行 Agent 主逻辑入口

        Args:
            message (str): 用户输入的提示词或指令

        Yields:
            AgentEvent: 智能体事件流（如启动事件、文本输出事件、错误事件等）
        """
        # 1. 触发智能体启动事件
        yield AgentEvent.agent_start(message)

        # 上下文
        self.context_manager.add_user_message(message)

        final_response: str | None = None
        # 2. 委托给内部 Agentic Loop 处理后续流式响应
        async for event in self._agentic_loop():
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")

        yield AgentEvent.agent_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:
        """智能体内部驱动循环 (Think-Act-Observe Loop)

        处理与 LLMClient 的流式通信，将底层 HTTP 响应事件转换为上层业务定义的 AgentEvent。

        Yields:
            AgentEvent: 转换后的 Agent 业务事件
        """
        # TODO: 后续可将上下文历史与系统提示词 (system_prompt) 注入此处
        # messages = [{
        #     "role": "user",
        #     "content": "你好"
        # }]

        response_text = ""

        # 开启流式响应，监听底层的 StreamEvent
        async for event in self.client.chat_completion(self.context_manager.get_messages(), True):
            # print(event)

            # 接收到模型增量输出文本
            if event.type == StreamEventType.TEXT_DELTA:
                if event.text_delta:
                    content = event.text_delta.content
                    response_text += content
                    yield AgentEvent.text_delta(content)
            # 触发异常/错误响应
            elif event.type == StreamEventType.ERROR:
                yield AgentEvent.agent_error(event.error or "Unknown error occurred.")

        self.context_manager.add_assistant_message(response_text or None)

        if response_text:
            yield AgentEvent.text_complete(response_text)

    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.client:
            await self.client.close()
            self.client = None
