from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, model_validator


class ModelConfig(BaseModel):
    name: str = "deepseek-chat"
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int | None = 256000


class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"])
    set_vars: dict[str, str] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    enabled: bool = True
    startup_timeout_sec: float = 10

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: Path | None = None

    url: str | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> MCPServerConfig:
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(
                "MCP服务器必须具备 '命令' (stdio) 或 'URL' (http/sse) 功能")

        if has_command and has_url:
            raise ValueError(
                "MCP服务器不能同时具有 '命令' (stdio) 和 'URL' (http/sse)")


class Config(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)
    shell_environment: ShellEnvironmentPolicy = Field(
        default_factory=ShellEnvironmentPolicy)

    max_turns: int = 100
    # max_tool_output_tokens: int = 50000
    mcp_servers: dict[str, MCPServerConfig] = Field(
        default_factory=dict)

    allowed_tools: list[str] | None = Field(
        None,
        description="如果已设置，则代理只能使用这些工具",
    )

    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = False

    @property
    def api_key(self) -> str | None:
        return os.environ.get("API_KEY")

    @property
    def base_url(self) -> str | None:
        return os.environ.get("BASE_URL")

    @property
    def model_name(self) -> str:
        return self.model.name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @model_name.setter
    def trmperature(self, value: str) -> None:
        self.model.temperature = value

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.api_key:
            errors.append("未找到API密钥, 设置API密钥环境变量")

        if not self.cwd.exists():
            errors.append(f"工作目录不存在: {self.cwd}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
