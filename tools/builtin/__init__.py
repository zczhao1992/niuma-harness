from tools.builtin.read_file import ReadFileTool
from tools.builtin.write_file import WriteFileTool

__all__ = ["ReadFileTool", "WriteFileTool"]


def get_all_builtin_tools() -> list[type]:
    return [
        ReadFileTool,
        WriteFileTool
    ]
