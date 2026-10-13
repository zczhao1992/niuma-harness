from datetime import datetime
from typing import Any
from client.response import TokenUsage
from config.config import Config
from prompts.system import get_system_prompt
from dataclasses import dataclass, field

from tools.base import Tool
from utils.text import count_tokens


@dataclass
class MessageItem:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_count: int | None = None
    pruned_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        if self.content:
            result["content"] = self.content
        elif self.role == "tool":

            result["content"] = ""
        elif self.tool_calls:

            result["content"] = None

        return result


class ContextManager:
    PRUNE_PROTECT_TOKENS = 40_000
    PRUNE_MINIMUM_TOKENS = 20_000

    def __init__(self, config: Config, user_memory: str | None, tools: list[Tool] | None) -> None:
        self._system_prompt = get_system_prompt(config, user_memory, tools)
        self.config = config
        self._model_name = self.config.model_name
        self._messages: list[MessageItem] = []
        self._latest_usage = TokenUsage()
        self.total_usage = TokenUsage()

    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role='user',
            content=content,
            token_count=count_tokens(content, self._model_name)
        )

        self._messages.append(item)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        item = MessageItem(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            token_count=count_tokens(content, self._model_name)
        )

        self._messages.append(item)

    def add_assistant_message(self, content: str, tool_calls: list[dict[str, Any]] | None = None) -> None:
        item = MessageItem(
            role='assistant',
            content=content or "",
            token_count=count_tokens(content or "", self._model_name),
            tool_calls=tool_calls or []
        )

        self._messages.append(item)

    def get_messages(self) -> list[dict[str, Any]]:
        messages = []

        if self._system_prompt:
            messages.append({
                "role": "system",
                "content": self._system_prompt
            })

        for item in self._messages:
            messages.append(item.to_dict())

        return messages

    def needs_compression(self) -> bool:
        context_limit = self.config.model.context_window
        current_tokens = self._latest_usage.total_tokens

        return current_tokens > (context_limit * 0.8)

    def set_latest_usage(self, usage: TokenUsage):
        self._latest_usage = usage

    def add_usage(self, usage: TokenUsage):
        self.total_usage += usage

    def replace_with_summary(self, summary: str) -> None:
        self._messages = []

        continuation_content = f"""# 上下文恢复(上一会话已压缩)

        由于上下文长度限制，先前的对话已被压缩。以下是迄今为止已完成工作的详细摘要. 

        **关键：列在'已完成操作'下的操作已经完成。不要重复它们.**

        ---

        {summary}

        ---

        从我们上次中断的地方继续工作。只专注于剩余的任务."""

        summary_item = MessageItem(
            role="user",
            content=continuation_content,
            token_count=count_tokens(continuation_content, self._model_name),
        )
        self._messages.append(summary_item)

        ack_content = """我已审阅上一会话的上下文。我明白:
                        - 最初的目标以及所请求的内容
                        - 哪些操作已经完成(我不会重复这些操作)
                        - 项目的当前状态
                        - 还有哪些工作仍需完成

                        我将仅继续处理剩余任务，从我们上次中断的地方开始."""
        ack_item = MessageItem(
            role="assistant",
            content=ack_content,
            token_count=count_tokens(ack_content, self._model_name),
        )
        self._messages.append(ack_item)

        continue_content = (
            "仅继续处理剩余的工作。不要重复任何已完成的操作. "
            "按照上述上下文中描述的下一步继续推进."
        )

        continue_item = MessageItem(
            role="user",
            content=continue_content,
            token_count=count_tokens(continue_content, self._model_name),
        )
        self._messages.append(continue_item)

    def prune_tool_outputs(self) -> int:
        user_message_count = sum(
            1 for msg in self._messages if msg.role == "user")

        if user_message_count < 2:
            return 0

        total_tokens = 0
        pruned_tokens = 0
        to_prune: list[MessageItem] = []

        for msg in reversed(self._messages):
            if msg.role == "tool" and msg.tool_call_id:
                if msg.pruned_at:
                    break

                tokens = msg.token_count or count_tokens(
                    msg.content, self._model_name)
                total_tokens += tokens

                if total_tokens > self.PRUNE_PROTECT_TOKENS:
                    pruned_tokens += tokens
                    to_prune.append(msg)

        if pruned_tokens < self.PRUNE_MINIMUM_TOKENS:
            return 0

        pruned_count = 0

        for msg in to_prune:
            msg.content = "[旧工具结果内容已清除]"
            msg.token_count = count_tokens(msg.content, self._model_name)
            msg.pruned_at = datetime.now()
            pruned_count += 1

        return pruned_count

    def clear(self) -> None:
        self._messages = []
