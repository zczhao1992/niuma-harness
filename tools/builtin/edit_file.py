from pathlib import Path
from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from utils.paths import ensure_parent_directory, resolve_path


class EditParams(BaseModel):
    path: str = Field(
        ...,
        description="要编辑的文件的路径(相对于工作目录或绝对路径)",
    )
    old_string: str = Field(
        "",
        description="要查找和替换的确切文本。必须完全匹配，包括所有空格和缩进。对于新文件，请留空。",
    )
    new_string: str = Field(
        ...,
        description="要用新文本替换旧字符串。可以为空以删除文本",
    )
    replace_all: bool = Field(
        False, description="替换所有出现的 old_string(默认值: false)"
    )


class EditTool(Tool):
    name = "edit"
    description = (
        "通过替换文本来编辑文件。old_string必须完全匹配"
        "(包括空格和缩进), 且在文件中必须唯一"
        "除非replace_all为true。使用此功能进行精确、精细的编辑。"
        "如需创建新文件或完全重写,请使用write_file。"
    )
    kind = ToolKind.WRITE
    schema = EditParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EditParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            if params.old_string:
                return ToolResult.error_result(
                    f"文件不存在：{path}。要创建新文件，请将 old_string 设为空字符串。"
                )

            ensure_parent_directory(path)
            path.write_text(params.new_string, encoding="utf-8")

            line_count = len(params.new_string.splitlines())

            return ToolResult.success_result(
                f"创建 {path} {line_count} 行",
                diff=FileDiff(
                    path=path,
                    old_content="",
                    new_content=params.new_string,
                    is_new_file=True,
                ),
                metadata={
                    "path": str(path),
                    "is_new_file": True,
                    "lines": line_count,
                },
            )

        old_content = path.read_text(encoding="utf-8")

        if not params.old_string:
            return ToolResult.error_result(
                "old_string 参数为空,但目标文件已存在.此时需要提供 old_string 来定位要替换的内容,或者改用 write_file 直接覆盖整个文件."
            )

        occurrence_count = old_content.count(params.old_string)

        if occurrence_count == 0:
            return self._no_match_error(params.old_string, old_content, path)

        if occurrence_count > 1 and not params.replace_all:
            return ToolResult.error_result(
                f"在{path}中找到{occurrence_count}次旧字符串. "
                f"其中: \n"
                f"1. 提供更多背景信息以确保匹配独特或\n"
                f"2. 设置replace_all为真以替换所有出现的内容",
                metadata={
                    "occurence_count": occurrence_count,
                },
            )

        if params.replace_all:
            new_content = old_content.replace(
                params.old_string, params.new_string)
            replace_count = occurrence_count
        else:
            new_content = old_content.replace(
                params.old_string, params.new_string, 1)
            replace_count = 1

        if new_content == old_content:
            return ToolResult.error_result("未进行任何更改 - 旧字符串等于新字符串")

        try:
            path.write_text(new_content, encoding="utf-8")
        except IOError as e:
            return ToolResult.error_result(f"无法写入文件: {e}")

        old_lines = len(old_content.splitlines())
        new_lines = len(new_content.splitlines())
        line_diff = new_lines - old_lines

        diff_msg = ""

        if line_diff > 0:
            diff_msg = f" (+{line_diff} 行)"
        elif line_diff < 0:
            diff_msg = f" ({line_diff} 行)"

        return ToolResult.success_result(
            f"编辑 {path}: 替换 {replace_count} 事件 {diff_msg}",
            diff=FileDiff(path=path, old_content=old_content,
                          new_content=new_content),
            metadata={
                "path": str(path),
                "replaced_count": replace_count,
                "line_diff": line_diff,
            },
        )

    def _no_match_error(self, old_string: str, content: str, path: Path) -> ToolResult:
        lines = content.splitlines()

        partial_matches = []
        search_terms = old_string.split()[:5]

        if search_terms:
            first_term = search_terms[0]
            for i, line in enumerate(lines, 1):
                if first_term in line:
                    partial_matches.append((i, line.strip()[:80]))
                    if len(partial_matches) >= 3:
                        break

        error_msg = f"old_string 未找到 {path}."

        if partial_matches:
            error_msg += "\n\n可能的相似行:"
            for line_num, line_preview in partial_matches:
                error_msg += f"\n  行 {line_num}: {line_preview}"
            error_msg += "\n\n确保 old_string 完全匹配(包括空白字符和缩进)."
        else:
            error_msg += (
                "- 确保文本完全匹配，包括: \n"
                "- 所有空格和缩进\n"
                "- 换行符\n"
                "- 任何不可见字符\n"
                "尝试使用read_file工具重新读取, 然后进行编辑."
            )

        return ToolResult.error_result(error_msg)
