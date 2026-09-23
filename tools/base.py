from __future__ import annotations
import abc

from pathlib import Path
from pydantic import BaseModel, ValidationError
from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from pydantic.json_schema import model_json_schema


class ToolKind(str, Enum):
    """工具分类枚举。

    用于声明工具的底层行为性质，指导框架层评估安全级别与是否需要二次人工确认。
    """

    READ = "read"       # 只读类操作（如读文件、列目录、搜索代码等）
    WRITE = "write"     # 修改类操作（如写文件、删除文件、修改配置等）
    SHELL = "shell"     # 终端系统命令执行（如 bash、python 运行等）
    NETWORK = "network"  # 网络通信操作（如 HTTP 请求、下载文件等）
    MEMORY = "memory"   # 记忆/上下文管理操作
    MCP = "mcp"         # 远程 MCP 协议扩展工具


@dataclass
class FileDiff:
    path: Path
    old_content: str
    new_content: str

    is_new_file: bool = False
    is_deletion: bool = False

    def to_diff(self) -> str:
        import difflib

        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith("\n"):
            old_lines[-1] += "\n"

        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        old_name = "/dev/null" if self.is_new_file else str(self.path)
        new_name = "/dev/null" if self.is_deletion else str(self.path)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name
        )

        return "".join(diff)


@dataclass
class ToolResult:
    """工具执行结果对象。

    标准化工具执行后的返回结构，供 Agent 捕获并转译为观察结果 (Observation)。
    """
    """工具是否成功执行"""
    success: bool
    """工具执行的核心文本输出结果（包含标准输出 stdout 或成功摘要）"""
    output: str
    """错误描述信息（包含标准错误 stderr 或 Python 异常信息）"""
    error: str | None = None
    """附加元数据（如耗时、代码行数、文件路径等额外结构化信息）"""
    metadata: dict[str, Any] = field(default_factory=dict)

    truncated: bool = False
    diff: FileDiff | None = None

    @classmethod
    def error_result(cls, error: str, output: str = "", **kwargs: Any):
        return cls(
            success=False,
            output=output,
            error=error,
            **kwargs
        )

    @classmethod
    def success_result(cls, output: str, **kwargs: Any):
        return cls(
            success=True,
            output=output,
            error=None,
            **kwargs
        )

    def to_model_output(self) -> str:
        if self.success:
            return self.output

        return f"错误: {self.error}\n\nOutput:\n{self.output}"


@dataclass
class ToolInvocation:
    """工具单次调用的上下文载体。

    封装了 LLM 拟调用的参数以及执行时的运行环境上下文。
    """
    """LLM 传入的具体实参字典"""
    params: dict[str, Any]
    """当前命令/工具执行的根工作目录 (Current Working Directory)"""
    cwd: Path


@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str


class Tool(abc.ABC):
    """所有 Agent 工具的抽象基类 (Abstract Base Class)。

    定义了工具的标准契约，包括 Schema 校验、危险度评估、参数验证以及异步执行主逻辑。
    所有自定义工具（如 ReadFileTool, BashTool 等）必须继承此类。
    """
    """工具唯一标识名称，供 LLM 在 tool_calls 中指定识别"""
    name: str = "base_tool"
    """工具的功能描述与使用指南，用于生成发送给 LLM 的 JSON Schema"""
    description: str = "Base tool"
    """工具的安全类别（默认只读）"""
    kind: ToolKind = ToolKind.READ

    def __init__(self) -> None:
        pass

    @property
    def schema(self) -> dict[str, Any] | type["BaseModel"]:
        """获取工具参数的校验 Schema。

        子类必须重写此属性，推荐返回一个继承自 `pydantic.BaseModel` 的类。

        Raises:
            NotImplementedError: 未在子类中实现该属性时抛出。
        """
        raise NotImplementedError("工具必须定义模式属性 (schema)")

    @abc.abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """执行工具的核心异步方法。

        Args:
            invocation (ToolInvocation): 包含了参数与环境上下文的调用对象。

        Returns:
            ToolResult: 统一的工具执行结果。
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """验证 LLM 传入的实参字典是否符合工具的 Schema 约束。

        Args:
            params (dict[str, Any]): 大模型模型生成的参数字典。

        Returns:
            list[str]: 校验失败的错误描述列表。若校验通过则返回空列表 `[]`。
        """
        schema = self.schema
        # 判断 schema 是否为继承自 Pydantic BaseModel 的具体数据模型类
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = ".".join(str(x) for x in error.get("loc", []))
                    msg = error.get("msg", "校验错误")
                    errors.append(f"Parameter '{field}': {msg}")
                return errors
            except Exception as e:
                return [str(e)]
        return []

    def is_mutating(self, params: dict[str, Any]) -> bool:
        """评估本次工具调用是否为具备'破坏性/修改性'的危险操作。

        例如写文件、跑 Shell 命令、发网络请求等属于高危操作，
        框架据此判断是否需要暂停并等待用户手动在终端确认 [Y/n]。

        Args:
            params (dict[str, Any]): 传入的实参。

        Returns:
            bool: 是否属于修改/破坏性操作。
        """
        return self.kind in {ToolKind.WRITE, ToolKind.SHELL, ToolKind.NETWORK, ToolKind.MEMORY}

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolInvocation | None:
        """获取人工交互二次确认的钩子方法。

        默认策略：如果不是高危修改类工具，直接返回 None 跳过人工确认；
        如果是高危操作，子类可重写此方法弹出确认菜单。

        Args:
            invocation (ToolInvocation): 拟执行的工具上下文。

        Returns:
            ToolInvocation | None: 经过人工确认/修改后的调用上下文；若放弃执行则返回 None。
        """
        if not self.is_mutating(invocation.params):
            return None

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute {self.name}"
        )

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            json_schema = model_json_schema(schema, mode="serialization")
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": json_schema.get("properties", {}),
                        "required": json_schema.get("required", []),
                    }
                }
            }

        if isinstance(schema, dict):
            result = {"name": self.name, 'description': self.description}

            if "parameters" in schema:
                result['parameters'] = schema['parameters']
            else:
                result['parameters'] = schema

            return result

        raise ValueError(
            f'Invalid schema type for tool {self.name}: {type(schema)}')
