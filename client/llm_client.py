import asyncio
import os
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from client.response import StreamEvent, TextDelta, TokenUsage, EventType
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError


load_dotenv()


class LLMClient:
    """LLM 客户端封装类，用于统一管理与 大模型 API 的异步通信。"""

    def __init__(self) -> None:
        """初始化客户端实例，默认底层 AsyncOpenAI 连接句柄为 None(延迟加载模式)。"""
        self._client: AsyncOpenAI | None = None
        """最大重试数"""
        self._max_retries: int = 3

    def get_client(self) -> None:
        """获取或初始化单例 AsyncOpenAI 客户端句柄。

        从环境变量加载配置，规避密钥硬编码问题。
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv(
                    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
                )
            )

        return self._client

    async def close(self) -> None:
        """安全关闭客户端连接，释放底层 HTTP 会话资源。"""
        if self._client:
            await self._client.close()
            self._client = None

    async def chat_completion(self, messages: list[dict[str, Any]], stream: bool = True) -> AsyncGenerator[StreamEvent, None]:
        """发起对话补全请求的核心入口方法。

        支持流式(Streaming)与非流式(Non-Streaming)两种响应方式。

        :param messages: 对话上下文消息列表
        :param stream: 是否开启流式传输模式(默认为 True)
        :return: 异步生成器，依次产出统一格式的 StreamEvent 事件对象
        """
        client = self.get_client()

        # 构建发送给 OpenAI API 的统一参数字典
        kwargs = {
            "model": "deepseek-chat",
            "messages": messages,
            "stream": stream
        }
        for attempt in range(self._max_retries + 1):
            try:

                # 根据 stream 参数路由到不同的响应处理生成器
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event

                return
            except RateLimitError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"超过最大限制: {e}"
                    )
                    return
            except APIConnectionError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"链接错误: {e}"
                    )
                    return
            except APIError as e:
                yield StreamEvent(
                    type=EventType.ERROR,
                    error=f"API错误: {e}"
                )
                return

    async def _stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:
        """处理流式响应，分块解析 API 增量数据并转换为内部 StreamEvent 类型。"""
        response = await client.chat.completions.create(**kwargs)

        finish_reason: str | None = None

        usage: TokenUsage | None = None

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=chunk.usage.prompt_tokens_details.cached_tokens,
                )

            # 跳过不包含 choices 的 Chunk（例如仅包含 usage 信息的末尾 chunk）
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            # 记录生成结束原因（例如 "stop", "length" 等）
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            # 若当前 Chunk 包含增量文本内容，立刻产出文本增量事件
            if delta.content:
                yield StreamEvent(
                    type=EventType.TEXT_DELTA,
                    text_delta=TextDelta(delta.content)
                )
        # 流结束，产出统一的 MESSAGE_COMPLETE 终结事件，附带 Token 统计与结束原因
        yield StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage
        )

    async def _non_stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> StreamEvent:
        """处理一次性非流式响应，并将完整结果包装为 MESSAGE_COMPLETE 类型的 StreamEvent。"""
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # 提取完整文本回复内容
        text_delta = None
        if message.content:
            text_delta = TextDelta(content=message.content)

        # 提取非流式响应的 Token 使用量统计
        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens,
            )
        # 返回一次性的完整消息事件
        return StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            usage=usage
        )
