from pydantic import BaseModel, Field
from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import ensure_parent_directory, resolve_path


class WriteFileParams(BaseModel):
    path: str = Field(..., description="要写入的文件的路径(相对于工作目录或绝对路径)")
    content: str = Field(..., description="要写入文件的内容")
    create_directories: bool = Field(
        True, description="如果父目录不存在，则创建它们"
    )


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "将内容写入文件。如果文件不存在则创建，如果文件已存在则覆盖。"
        "父目录会自动创建。用于创建新文件或完全替换文件内容。"
        "如需部分修改，请改用编辑工具。"
    )

    kind = ToolKind.WRITE
    schema = WriteFileParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()

        old_content = ""

        if not is_new_file:
            try:
                old_content = path.read_text(encoding="utf-8")
            except:
                pass

        try:
            if params.create_directories:
                ensure_parent_directory(path)
            elif not path.parent.exists():
                return ToolResult.error_result(f"父目录不存在: {path.parent}")

            path.write_text(params.content, encoding="utf-8")

            action = "创建" if is_new_file else "修改"
            line_count = len(params.content.splitlines())

            return ToolResult.success_result(
                f"{action} {path} {line_count} 行",
                diff=FileDiff(
                    path=path,
                    old_content=old_content,
                    new_content=params.content,
                    is_new_file=is_new_file
                ),
                metadata={
                    "path": str(path),
                    "is_new_file": is_new_file,
                    "lines": line_count,
                    "bytes": len(params.content.encode("utf-8"))
                }
            )
        except OSError as e:
            return ToolResult.error_result(f"写入文件错误: {e}")
