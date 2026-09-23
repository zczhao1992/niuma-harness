from tools.base import Tool, ToolKind
from pydantic import BaseModel, Field


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
