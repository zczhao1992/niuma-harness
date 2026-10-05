import json
import uuid
from config.config import Config
from config.loader import get_data_dir
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class MemoryParams(BaseModel):
    action: str = Field(
        ..., description="动作：'set'、'get'、'delete'、'list'、'clear'"
    )
    key: str | None = Field(
        None, description="记忆键（执行 `set`、`get`、`delete` 时必填）"
    )
    value: str | None = Field(
        None, description="要存储的值（执行 `set` 时必填）")


class MemoryTool(Tool):
    name = "memory"
    description = "存储和检索持久化记忆。用它记住用户偏好、重要上下文或笔记。"
    kind = ToolKind.MEMORY
    schema = MemoryParams

    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        if not path.exists():
            return {"entries": {}}

        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            return {"entries": {}}

    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "user_memory.json"

        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False))

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)

        if params.action.lower() == "set":
            if not params.key or not params.value:
                return ToolResult.error_result(
                    "执行 'set' 动作时, `key` 和 `value` 为必填项"
                )
            memory = self._load_memory()
            memory["entries"][params.key] = params.value
            self._save_memory(memory)

            return ToolResult.success_result(f"已设置记忆: {params.key}")
        elif params.action.lower() == "get":
            if not params.key:
                return ToolResult.error_result("执行 'get' 动作时, `key` 为必填项")

            memory = self._load_memory()
            if params.key not in memory.get("entries", {}):
                return ToolResult.success_result(
                    f"未找到记忆: {params.key}",
                    metadata={
                        "found": False,
                    },
                )
            return ToolResult.success_result(
                f"已找到记忆：{params.key}: {memory['entries'][params.key]}",
                metadata={
                    "found": True,
                },
            )
        elif params.action == "delete":
            if not params.key:
                return ToolResult.error_result("执行 'delete' 动作时，`key` 为必填项")
            memory = self._load_memory()
            if params.key not in memory.get("entries", {}):
                return ToolResult.success_result(f"未找到记忆：{params.key}")

            del memory["entries"][params.key]
            self._save_memory(memory)

            return ToolResult.success_result(f"已删除记忆：{params.key}")
        elif params.action == "list":
            memory = self._load_memory()
            entries = memory.get("entries", {})
            if not entries:
                return ToolResult.success_result(
                    "没有存储任何记忆",
                    metadata={
                        "found": False,
                    },
                )
            lines = ["已存储的记忆："]
            for key, value in sorted(entries.items()):
                lines.append(f"  {key}: {value}")

            return ToolResult.success_result(
                "\n".join(lines),
                metadata={
                    "found": True,
                },
            )
        elif params.action == "clear":
            memory = self._load_memory()
            count = len(memory.get("entries", {}))
            memory["entries"] = {}
            self._save_memory(memory)
            return ToolResult.success_result(f"已清除 {count} 条记忆")
        else:
            return ToolResult.error_result(f"未知动作：{params.action}")
