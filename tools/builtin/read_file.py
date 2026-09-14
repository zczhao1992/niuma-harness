from pydantic import BaseModel, Field
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path
from utils.text import count_tokens, truncate_text


class ReadFileParams(BaseModel):
    path: str = Field(...,
                      description="要读取的文件路径 (相对于工作目录或绝对路径)")

    offset: int = Field(1, ge=1, description='行数从第1行开始')

    limit: int | None = Field(None, ge=1, description='最大行数不能超过文件行数')


class ReadFileTool(Tool):
    name = 'read_file'
    description = (
        "读取文本文件的内容，返回带有行号的文件内容。"
        "对于大型文件，可利用偏移量和读取范围来获取特定部分的内容。"
        "无法读取二进制文件（如图片、可执行文件等）。")
    kind = ToolKind.READ
    schema = ReadFileParams

    MAX_FILE_SIZE = 1024*1024*10
    MAX_OUTPUT_TOKENS = 25000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)

        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(f"文件未找到: {path}")

        if not path.is_file():
            return ToolResult.error_result(f"路径不是文件: {path}")

        file_size = path.stat().st_size

        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(f"文件太大 ({file_size / (1024*1024):.1f}MB)  最大为{self.MAX_FILE_SIZE / (1024*1024):.0f}MB")

        if is_binary_file(path):
            file_size_mb = file_size / (1024*1024)
            size_str = f"{file_size_mb:.2f}MB" if file_size_mb >= 1 else f"{file_size} bytes"
            return ToolResult.error_result(f"无法读取二进制文件: {path.name} ({size_str})")

        try:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.success("文件为空", metadata={"lines": 0})

            start_idx = max(0, params.offset - 1)

            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines

            selected_lines = lines[start_idx:end_idx]

            formatted_lines = []

            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:6}|{line}")

            output = "\n".join(formatted_lines)
            token_count = count_tokens(output)

            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    output,
                    self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n ...[truncated {total_lines} total lines]"
                )
                truncated = True

            metadata_lines = []
            if start_idx > 0 or end_idx < total_lines:
                metadata_lines.append(
                    f"行数 {start_idx + 1}-{end_idx} 在 {total_lines}")

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header + output

            return ToolResult.success_result(
                output=output,
                truncated=truncated,
                metadata={
                    "path": str(path),
                    "total_lines": total_lines,
                    "shown_start": start_idx + 1,
                    "shown_end": end_idx
                }
            )

        except Exception as e:
            return ToolResult.error_result(f"读取文件失败: {e}")
