# NiuMa-Harness

牛马 harness 是一个从零手写的轻量级 Python 异步 AI Agent。参考了 Claude Code 的设计思路，一个能**看懂项目、自己思考、敲终端命令、改代码**的'AI 编程牛马'。

核心就是一个循环：把你的话交给大模型，模型说要调工具就去调，把结果再喂回去，直到模型给出最终答复。

> 默认对接 DeepSeek，其它 OpenAI 兼容接口也能用，改 `BASE_URL` 即可。

---

## 功能点

- **先读代码再动手**：会先用 `read_file`、`grep`、`glob` 摸清上下文再改代码。可以在 `AGENTS.md` 里给它定规则。
- **流式输出**：模型文本、工具调用、执行结果都实时渲染在终端上。
- **会敲命令、会改文件**：内置 shell、写文件、编辑文件工具，改文件时展示 diff。
- **危险操作会拦截**：`rm -rf /`、`curl ... | bash` 这类命令会被识别，默认先询问再执行。
- **上下文自动压缩**：对话接近窗口上限时，自动调模型生成摘要后继续，不会硬塞到报错。
- **死循环检测**：同一工具同一参数反复调用三次会插入提示，把循环拉回来。
- **会话持久化**：`/save` 存档、`/resume` 续聊；`/checkpoint` 打快照，`/restore` 回滚。
- **子 Agent**：把占用上下文较多的调查类任务交给独立子 Agent，只把结论带回主线程。
- **MCP 支持**：可接入外部工具服务器，支持 stdio 和 SSE，工具自动注册。
- **Hooks**：在工具调用、Agent 生命周期等节点挂脚本执行。
- **记忆**：用户偏好写入记忆文件，新会话仍生效。

---

## 安装

需要 Python 3.10+。

```bash
git clone <your-repo>
cd niuma-harness
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

API Key 和接口地址从环境变量读取：

```bash
# Windows PowerShell
$env:API_KEY="sk-xxxxxxxx"
$env:BASE_URL="https://api.deepseek.com"

# macOS / Linux
export API_KEY="sk-xxxxxxxx"
export BASE_URL="https://api.deepseek.com"
```

---

## 运行

交互模式：

```bash
python main.py
```

单次模式：

```bash
python main.py "帮我看看这个项目用的是什么 web 框架"
```

指定工作目录：

```bash
python main.py -c /path/to/your/project
```

---

## 斜杠命令

| 命令               | 作用                                 |
| ------------------ | ------------------------------------ |
| `/help`            | 查看帮助                             |
| `/config`          | 查看当前配置                         |
| `/model <名字>`    | 临时切换模型                         |
| `/approval <策略>` | 切换审批策略                         |
| `/tools`           | 列出可用工具                         |
| `/mcp`             | 查看 MCP 服务器状态                  |
| `/stats`           | 会话统计（轮数、消息数、token 用量） |
| `/clear`           | 清空当前上下文（不动记忆文件）       |
| `/save`            | 保存会话                             |
| `/sessions`        | 列出已保存会话                       |
| `/resume <id>`     | 继续某个会话                         |
| `/checkpoint`      | 创建当前状态快照                     |
| `/restore <id>`    | 恢复到某个快照                       |
| `/exit` `/quit`    | 退出                                 |

---

## 审批策略

| 策略         | 行为                           |
| ------------ | ------------------------------ |
| `on-request` | 默认。仅在工具要求确认时询问   |
| `on-failure` | 先执行，失败后询问             |
| `auto`       | 仅危险操作询问                 |
| `auto-edit`  | 读和编辑放行，其它危险操作询问 |
| `never`      | 从不询问，拒绝确认类操作       |
| `yolo`       | 全部放行                       |

在交互中用 `/approval yolo` 切换，也可写进配置文件。

---

## 配置

配置分两级，项目级覆盖系统级：

- 系统级：`<用户配置目录>/niuma-harness/config.toml`
- 项目级：`你的项目/.niuma-harness/config.toml`

带 hook 和 MCP 的示例：

```toml
hooks_enabled = true

[model]
name = "deepseek-chat"
temperature = 0

[[hooks]]
name = 'test_before_tool'
trigger = 'before_tool'
command = 'python ./scripts/test_tool.py'

[[hooks]]
name = 'test_before_agent'
trigger = 'before_agent'
command = 'python ./scripts/test_tool.py'

[mcp_servers.filesystem]
enabled = true
command = "cmd"          # Linux/macOS 下改成 "npx"
args = ["/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", "E:/xxx/niuma-harness"]
```

Hook 触发点：`before_agent`、`after_agent`、`before_tool`、`after_tool`、`on_error`。脚本通过 `AI_AGENT_*` 环境变量获取运行时信息，示例见 `scripts/test_tool.py`。

---

## 自定义工具

把 `.py` 文件放到 `你的项目/.niuma-harness/tools/` 下，继承 `Tool` 并实现 `name`、`description`、`schema`、`execute`，启动时会自动扫描注册。

```python
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "工具用途，模型据此判断是否调用"
    kind = ToolKind.READ   # READ / WRITE / SHELL / NETWORK / MEMORY / MCP

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        return ToolResult.success_result("执行完成")
```

---

## 目录结构

```
agent/       核心。agent.py 主循环，session.py 装配各子系统
tools/       工具。builtin/ 内置工具，mcp/ MCP 支持，subagents.py 子 Agent
context/     上下文管理。manager.py 消息与 token，compaction.py 摘要压缩，loop_detector.py 循环检测
safety/      approval.py 审批与危险命令识别
hooks/       hook_system.py 生命周期钩子
prompts/     系统提示词（中英两版）
config/      config.py 配置模型，loader.py 两级配置合并
client/      llm_client.py，OpenAI SDK 封装，带重试
ui/          tui.py，终端渲染，流式输出与 diff 着色
```

内置工具共 11 个：`read_file`、`write_file`、`edit_file`、`list_dir`、`glob`、`grep`、`shell`、`todo`、`memory`、`web_search`、`web_fetch`。
