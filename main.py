from pathlib import Path
import sys
from typing import Any
from agent.agent import Agent
from agent.events import AgentEventType
from agent.persistence import PersistenceManager, SessionSnapshot
from agent.session import Session
from client.llm_client import LLMClient
import asyncio
import click
from config.config import ApprovalPolicy, Config
from config.loader import load_config
from ui.tui import TUI, get_console

console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.config = config
        self.tui = TUI(config, console)

    async def run_single(self, message: str) -> str | None:
        async with Agent(self.config) as agent:
            self.agent = agent
            return await self._process_message(message)

    async def run_interactive(self) -> str | None:
        self.tui.print_welcome(
            "NiuMa-Harness",
            lines=[
                f"模型名称: {self.config.model_name}",
                f"工作目录: {self.config.cwd}",
                "指令: /help /config /approval /model /exit"
            ]
        )
        async with Agent(self.config, confirmation_callback=self.tui.handle_confirmation) as agent:
            self.agent = agent

            while True:
                try:
                    user_input = console.input("\n[user]>[/user]").strip()
                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        should_continue = await self._handle_command(user_input)
                        if not should_continue:
                            break
                        continue

                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    console.print("\n[dim]使用 /exit 命令退出[/dim]")
                except EOFError:
                    break

        console.print("\n[dim]再见！[/dim]")

    def _get_tool_kind(self, tool_name: str) -> str | None:
        tool_kind = None
        tool = self.agent.session.tool_registry.get(tool_name)
        if not tool:
            tool_kind = None

        tool_kind = tool.kind.value

        return tool_kind

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        assistant_streaming = False
        final_response: str | None = None

        async for event in self.agent.run(message):
            # print(event)
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming = True
                self.tui.stream_assistant_delta(content)
            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming = False
            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                console.print(f"\n[error] Error: {error}[/error]")
            elif event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "未知")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {})
                )
            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "未知")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("diff"),
                    event.data.get("truncated", False),
                    event.data.get("exit_code")
                )

        return final_response

    async def _handle_command(self, command: str) -> bool:
        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        if cmd_name == "/exit" or cmd_name == "/quit":
            return False
        elif command == "/help":
            self.tui.show_help()
        elif command == "/clear":
            self.agent.session.context_manager.clear()
            self.agent.session.loop_detector.clear()
            console.print("[success]对话已清除 [/success]")
        elif command == "/config":
            console.print("\n[bold]当前配置[/bold]")
            console.print(f"  模型: {self.config.model_name}")
            console.print(f"  温度: {self.config.temperature}")
            console.print(f"  批准: {self.config.approval.value}")
            console.print(f"  工作目录: {self.config.cwd}")
            console.print(f"  最大轮数: {self.config.max_turns}")
            console.print(f"  已启用Hook: {self.config.hooks_enabled}")
        elif cmd_name == "/model":
            if cmd_args:
                self.config.model_name = cmd_args
                console.print(
                    f"[success]模型已更改: {cmd_args} [/success]")
            else:
                console.print(f"当前模型: {self.config.model_name}")
        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
                    self.config.approval = approval
                    console.print(
                        f"[success]批准策略已更改: {cmd_args} [/success]"
                    )
                except:
                    console.print(
                        f"[error]错误的批准策略: {cmd_args} [/error]"
                    )
                    console.print(
                        f"有效选项: {', '.join(p for p in ApprovalPolicy)}"
                    )
            else:
                console.print(
                    f"现行批准策略: {self.config.approval.value}")
        elif cmd_name == "/stats":
            stats = self.agent.session.get_stats()
            console.print("\n[bold]会话统计 [/bold]")
            for key, value in stats.items():
                console.print(f"   {key}: {value}")
        elif cmd_name == "/tools":
            tools = self.agent.session.tool_registry.get_tools()
            console.print(f"\n[bold]可用工具 ({len(tools)}) [/bold]")
            for tool in tools:
                console.print(f"  • {tool.name}")
        elif cmd_name == "/mcp":
            mcp_servers = self.agent.session.mcp_manager.get_all_servers()
            console.print(f"\n[bold]MCP 服务 ({len(mcp_servers)}) [/bold]")
            for server in mcp_servers:
                status = server["status"]
                status_color = "green" if status == "connected" else "red"
                console.print(
                    f"  • {server['name']}: [{status_color}]{status}[/{status_color}] ({server['tools']} tools)"
                )
        elif cmd_name == "/save":
            persistence_manager = PersistenceManager()
            session_snapshot = SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created_at,
                updated_at=self.agent.session.updated_at,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages(),
                total_usage=self.agent.session.context_manager.total_usage,
            )
            persistence_manager.save_session(session_snapshot)
            console.print(
                f"[success]会话已保存 {self.agent.session.session_id}[/success]"
            )
        elif cmd_name == "/sessions":
            persistence_manager = PersistenceManager()
            sessions = persistence_manager.list_sessions()
            console.print("\n[bold]已保存的会话[/bold]")
            for s in sessions:
                console.print(
                    f"  • {s['session_id']} (轮转: {s['turn_count']}, 更新: {s['updated_at']})"
                )
        elif cmd_name == "/resume":
            if not cmd_args:
                console.print(f"[error]用法: /resume <session_id> [/error]")
            else:
                persistence_manager = PersistenceManager()
                snapshot = persistence_manager.load_session(cmd_args)
                if not snapshot:
                    console.print(f"[error]会话不存在 [/error]")
                else:
                    session = Session(
                        config=self.config,
                    )
                    await session.initialize()
                    session.session_id = snapshot.session_id
                    session.created_at = snapshot.created_at
                    session.updated_at = snapshot.updated_at
                    session.turn_count = snapshot.turn_count
                    session.context_manager.total_usage = snapshot.total_usage

                    for msg in snapshot.messages:
                        if msg.get("role") == "system":
                            continue
                        elif msg["role"] == "user":
                            session.context_manager.add_user_message(
                                msg.get("content", "")
                            )
                        elif msg["role"] == "assistant":
                            session.context_manager.add_assistant_message(
                                msg.get("content", ""), msg.get("tool_calls")
                            )
                        elif msg["role"] == "tool":
                            session.context_manager.add_tool_result(
                                msg.get("tool_call_id", ""), msg.get(
                                    "content", "")
                            )

                    await self.agent.session.client.close()
                    await self.agent.session.mcp_manager.shutdown()

                    self.agent.session = session
                    console.print(
                        f"[success]续会: {session.session_id}[/success]"
                    )
        elif cmd_name == "/checkpoint":
            persistence_manager = PersistenceManager()
            session_snapshot = SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created_at,
                updated_at=self.agent.session.updated_at,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages(),
                total_usage=self.agent.session.context_manager.total_usage,
            )
            checkpoint_id = persistence_manager.save_checkpoint(
                session_snapshot)
            console.print(
                f"[success]已创建检查点: {checkpoint_id}[/success]")
        elif cmd_name == "/restore":
            if not cmd_args:
                console.print(
                    f"[error]用法: /restire <checkpoint_id> [/error]")
            else:
                persistence_manager = PersistenceManager()
                snapshot = persistence_manager.load_checkpoint(cmd_args)
                if not snapshot:
                    console.print(f"[error]检查点不存在 [/error]")
                else:
                    session = Session(
                        config=self.config,
                    )
                    await session.initialize()
                    session.session_id = snapshot.session_id
                    session.created_at = snapshot.created_at
                    session.updated_at = snapshot.updated_at
                    session.turn_count = snapshot.turn_count
                    session.context_manager.total_usage = snapshot.total_usage

                    for msg in snapshot.messages:
                        if msg.get("role") == "system":
                            continue
                        elif msg["role"] == "user":
                            session.context_manager.add_user_message(
                                msg.get("content", "")
                            )
                        elif msg["role"] == "assistant":
                            session.context_manager.add_assistant_message(
                                msg.get("content", ""), msg.get("tool_calls")
                            )
                        elif msg["role"] == "tool":
                            session.context_manager.add_tool_result(
                                msg.get("tool_call_id", ""), msg.get(
                                    "content", "")
                            )

                    await self.agent.session.client.close()
                    await self.agent.session.mcp_manager.shutdown()

                    self.agent.session = session
                    console.print(
                        f"[success]续会: {session.session_id}, 检查点: {checkpoint_id}[/success]"
                    )
        else:
            console.print(f"[error]未知命令: {cmd_name}[/error]")

        return True


async def run(messages: dict[str, Any]):
    client = LLMClient()
    async for event in client.chat_completion(messages, True):
        print(event)


@click.command()
@click.argument("prompt", required=False)
@click.option(
    "--cwd", "-c",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="当前工作目录"
)
def main(prompt: str | None, cwd: Path | None):

    try:
        config = load_config(cwd=cwd)
    except Exception as e:
        console.print(f"[error]配置错误: {e}[/error]")

    errors = config.validate()
    if errors:
        for error in errors:
            console.print(f"[error]{error}[/error]")

        sys.exit(1)

    cli = CLI(config)

    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli.run_interactive())

    # print("dddddddddddddd")


main()
