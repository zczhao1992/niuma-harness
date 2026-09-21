from pydantic import BaseModel, Field
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path
from utils.text import count_tokens, truncate_text


class ReadFileParams(BaseModel):
    """读文件工具的输入参数校验模型。"""
    path: str = Field(...,
                      description="要读取的文件路径 (相对于工作目录或绝对路径)")

    offset: int = Field(1, ge=1, description='行数从第1行开始')

    limit: int | None = Field(None, ge=1, description='最大行数不能超过文件行数')


class ReadFileTool(Tool):
    """读文件工具实现类。

    具备行号格式化输出、分页读取、二进制过滤、多编码容错降级以及 Token 截断保护机制。
    """
    name = 'read_file'
    description = (
        "读取文本文件的内容，返回带有行号的文件内容。"
        "对于大型文件，可利用偏移量和读取范围来获取特定部分的内容。"
        "无法读取二进制文件（如图片、可执行文件等）。")
    kind = ToolKind.READ
    schema = ReadFileParams

    # 限制条件约束
    MAX_FILE_SIZE = 1024 * 1024 * 10  # 单次读取的最大文件上限 (10 MB)
    MAX_OUTPUT_TOKENS = 25000         # 输出给大模型的最大 Token 限制

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """异步执行读取文件主逻辑。

        Args:
            invocation (ToolInvocation): 包含输入参数及工作目录上下文的调用对象。

        Returns:
            ToolResult: 带有带行号文本内容及元数据的统一工具执行结果。
        """
        # 1. 解析参数与工作路径
        params = ReadFileParams(**invocation.params)

        path = resolve_path(invocation.cwd, params.path)

        # 2. 存在性与文件类型校验
        if not path.exists():
            return ToolResult.error_result(f"文件未找到: {path}")

        if not path.is_file():
            return ToolResult.error_result(f"路径不是文件: {path}")

        # 3. 文件大小校验
        file_size = path.stat().st_size

        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(f"文件太大 ({file_size / (1024*1024):.1f}MB)  最大为{self.MAX_FILE_SIZE / (1024*1024):.0f}MB")

        # 4. 二进制文件过滤
        if is_binary_file(path):
            file_size_mb = file_size / (1024*1024)
            size_str = f"{file_size_mb:.2f}MB" if file_size_mb >= 1 else f"{file_size} bytes"
            return ToolResult.error_result(f"无法读取二进制文件: {path.name} ({size_str})")

        try:
            try:
                # 5. 读取文件内容（支持 UTF-8 与 Latin-1 自动降级解析）
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)

            # 空文件特殊处理
            if total_lines == 0:
                return ToolResult.success("文件为空", metadata={"lines": 0})

            # 6. 计算分页切片范围 (1-based offset 转为 0-based 切片)
            start_idx = max(0, params.offset - 1)

            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines

            selected_lines = lines[start_idx:end_idx]

            # 7. 拼接带固定宽度行号的前缀文本 (如: "     1|import os")
            formatted_lines = []

            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:6}|{line}")

            output = "\n".join(formatted_lines)
            token_count = count_tokens(output)

            # 8. Token 溢出保护截断
            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    output,
                    self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n ...[truncated {total_lines} total lines]"
                )
                truncated = True

            # 9. 组合范围说明头信息（若使用了分页切片）
            metadata_lines = []
            if start_idx > 0 or end_idx < total_lines:
                metadata_lines.append(
                    f"行数 {start_idx + 1}-{end_idx} 在 {total_lines}")

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header + output

            # 10. 返回成功结果与元数据
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
