import uuid
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class TodosParams(BaseModel):
    action: str = Field(...,
                        description="操作：'添加','完成','列出','清除'")
    id: str | None = Field(None, description="待办事项ID(用于完成)")
    content: str | None = Field(None, description="待办事项内容(用于添加)")


class TodosTool(Tool):
    name = "todos"
    description = "管理当前会话的任务列表。使用此列表可跟踪多步骤任务的进度。"
    kind = ToolKind.MEMORY
    schema = TodosParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._todos: dict[str, str] = {}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodosParams(**invocation.params)

        if params.action.lower() == "add":
            if not params.content:
                return ToolResult.error_result("'添加'操作所需的`content`")
            todo_id = str(uuid.uuid4())[:8]
            self._todos[todo_id] = params.content
            return ToolResult.success_result(
                f"增加待办 [{todo_id}]: {params.content}"
            )
        elif params.action.lower() == "complete":
            if not params.id:
                return ToolResult.error_result("'complete'操作所需的`id`")
            if params.id not in self._todos:
                return ToolResult.error_result(f"未找到待办事项: {params.id}")

            content = self._todos.pop(params.id)
            return ToolResult.success_result(f"已完成待办事项 [{params.id}]: {content}")
        elif params.action == "list":
            if not self._todos:
                return ToolResult.success_result("没有待办")
            lines = ["Todos:"]

            for todo_id, content in self._todos.items():
                lines.append(f"  [{todo_id}] {content}")
            return ToolResult.success_result("\n".join(lines))
        elif params.action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(f"完成 {count} 待办")
        else:
            return ToolResult.error_result(f"Unknown action: {params.action}")
