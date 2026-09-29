from urllib.parse import urlparse

import httpx
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class WebFetchParams(BaseModel):
    url: str = Field(...,
                     description="要获取的URL(必须是http://或https://)")
    timeout: int = Field(
        30,
        ge=5,
        le=120,
        description="请求超时秒数(默认值: 120)",
    )


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "从URL获取内容。以文本形式返回响应正文"
    kind = ToolKind.NETWORK
    schema = WebFetchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebFetchParams(**invocation.params)

        parsed = urlparse(params.url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return ToolResult.error_result(f"Url 必须是 http:// 或 https://")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(params.timeout),
                follow_redirects=True,
            ) as client:
                response = await client.get(params.url)
                response.raise_for_status()
                text = response.text
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(
                f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
            )
        except Exception as e:
            return ToolResult.error_result(f"请求失败: {e}")

        if len(text) > 100 * 1024:
            text = text[: 100 * 1024] + "\n... [内容截断]"

        return ToolResult.success_result(
            text,
            metadata={
                "status_code": response.status_code,
                "content_length": len(response.content),
            },
        )
