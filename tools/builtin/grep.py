import os
from pathlib import Path
import re
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import is_binary_file, resolve_path


class GrepParams(BaseModel):
    pattern: str = Field(...,
                         description="要搜索的正则表达式模式")
    path: str = Field(
        ".", description="要搜索的文件或目录(默认：当前目录)"
    )
    case_insensitive: bool = Field(
        False,
        description="不区分大小写的搜索(默认值：否)",
    )


class GrepTool(Tool):
    name = "grep"
    description = "在文件内容中搜索正则表达式模式。返回匹配的行，并附带文件路径和行号。"
    kind = ToolKind.READ
    schema = GrepParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GrepParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists():
            return ToolResult.error_result(f"路径不存在: {search_path}")

        try:
            flags = re.IGNORECASE if params.case_insensitive else 0
            pattern = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(f"无效的正则表达式模式: {e}")

        if search_path.is_dir():
            files = self._find_files(search_path)
        else:
            files = [search_path]

        output_lines = []
        matches = 0

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            lines = content.splitlines()
            file_matches = False

            # === path.py ===
            # 1: async def execute()
            # 30: async def execute()

            # === path2.py ===
            # 1: async def execute()
            # 30: async def execute()
            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches += 1
                    if not file_matches:
                        rel_path = file_path.relative_to(invocation.cwd)
                        output_lines.append(f"=== {rel_path} ===")
                        file_matches = True

                    output_lines.append(f"{i}:{line}")

            if file_matches:
                output_lines.append("")

        if not output_lines:
            return ToolResult.success_result(
                f"未找到与模式匹配的内容 '{params.pattern}'",
                metadata={
                    "path": str(search_path),
                    "matches": 0,
                    "files_searched": len(files),
                },
            )

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "path": str(search_path),
                "matches": matches,
                "files_searched": len(files),
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
