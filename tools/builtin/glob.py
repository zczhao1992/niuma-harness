import os
from pathlib import Path
import re
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import is_binary_file, resolve_path


class GlobParams(BaseModel):
    pattern: str = Field(..., description="用于匹配的Glob模式")
    path: str = Field(
        ".", description="搜索目录(默认：当前目录)"
    )


class GlobTool(Tool):
    name = "glob"
    description = (
        "查找符合通配符模式的文件。支持使用'**'进行递归匹配。"
    )
    kind = ToolKind.READ
    schema = GlobParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(f"目录不存在: {search_path}")

        try:
            matches = list(search_path.glob(params.pattern))
            matches = [p for p in matches if p.is_file()]
        except Exception as e:
            return ToolResult.error_result(f"搜索错误: {e}")

        output_lines = []

        for file_path in matches[:1000]:
            try:
                rel_path = file_path.relative_to(invocation.cwd)
            except Exception:
                rel_path = file_path

            output_lines.append(str(rel_path))

        if len(matches) > 1000:
            output_lines.append(f"...(限制为1000个结果)")

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "path": str(search_path),
                "matches": len(matches),
            },
        )

    def _find_files(self, search_path: Path) -> list[Path]:
        files = []

        for root, dirs, filenames in os.walk(search_path):
            dirs[:] = [
                d
                for d in dirs
                if d not in {"node_modules", "__pycache__", ".git", ".venv", "venv"}
            ]

            for filename in filenames:
                if filename.startswith("."):
                    continue

                file_path = Path(root) / filename
                if not is_binary_file(file_path):
                    files.append(file_path)
                    if len(files) >= 500:
                        return files

        return files
