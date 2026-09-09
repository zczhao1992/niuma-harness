# NiuMa-Harness

牛马 harness 一个从零开始构建的、支持工具调用与流式响应的轻量级 AI Coding Agent 框架。

项目基于 Python 异步架构，参考了 Claude Code 的 Agent 理念，旨在底层实现一个具备 **“感知-思考-决策-执行” (Think-Act-Observe)** 能力的智能体系统，支持本地文件系统操作、受控终端命令执行及上下文管理。

---

## 📋 开发清单 (Task List)

### 1. 基础通信 (Core Client)

- [x] 异步 `LLMClient` 封装
- [x] 流式与非流式响应处理
- [x] Token 消耗统计

### 2. 上下文与提示词 (Prompt & Context)

- [ ] 系统提示词 (`system_prompt`) 编写
- [ ] 当前工作目录 (CWD) 与系统环境感知

### 3. 工具库 (Tools)

- [ ] 文件工具：读取、写入、目录遍历
- [ ] 终端工具：受控 Bash 命令执行
- [ ] 搜索工具：代码库文本搜索

### 4. Agent 核心逻辑 (Agentic Loop)

- [ ] 工具调用 (Tool Call) 自动解析与执行循环
- [ ] 死循环检测与防护
- [ ] 上下文 Token 超限压缩 (Compaction)

### 5. 安全与 CLI 交互 (Safety & CLI)

- [ ] 危险命令二次确认 (Human-in-the-loop)
- [ ] 终端流式打字机界面
- [ ] 会话保存与恢复 (Checkpointing)

---
