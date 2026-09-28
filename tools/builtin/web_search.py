from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from ddgs import DDGS


class WebSearchParams(BaseModel):
    query: str = Field(..., description="搜索查询")
    max_results: int = Field(
        10,
        ge=1,
        le=20,
        description="返回的最大结果数(默认值: 10)",
    )


class WebSearchTool(Tool):
    name = "web_search"
    description = "在网络上搜索信息。返回包含标题、网址和摘要的搜索结果"
    kind = ToolKind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        try:
            results = DDGS().text(
                params.query,
                region="zh-cn",
                safesearch="off",
                timelimit="y",
                page=1,
                backend="auto",
            )
        except Exception as e:
            return ToolResult.error_result(f"搜索失败: {e}")

        if not results:
            return ToolResult.success_result(
                f"未找到结果: {params.query}",
                metadata={
                    "results": 0,
                },
            )

        output_lines = [f"搜索结果: {params.query}"]

        for i, result in enumerate(results, start=1):
            output_lines.append(f"{i}. Title: {result['title']}")
            output_lines.append(f"   URL: {result['href']}")
            if result.get("body"):
                output_lines.append(f"   Snippet: {result['body']}")

            output_lines.append("")

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "results": len(results),
            },
        )
