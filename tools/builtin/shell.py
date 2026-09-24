from tools.base import Tool, ToolKind


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = "执行一个Shell命令。使用它来运行系统命令、脚本和CLI工具。"
