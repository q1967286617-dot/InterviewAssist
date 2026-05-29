# Interview Agent — 通过面试，认识自己

一个 agentic Web 应用：通过模拟面试持续沉淀「自我画像」。面试三 agent + 一个随时间复利、由
agent 自我维护的颗粒化个人 Wiki（[LLM-Wiki 范式](#个人-wiki颗粒化-llm-wiki-范式)）。

## 面试三 Agent

| Agent | 职责 |
|---|---|
| **面试官** | 主导面试，支持岗位/风格（友善·高压）配置，可中途切换风格；每次回复同时产出「内心独白」与「对外回复」 |
| **观察者/书记员** | 静默旁听，每轮抽取经历 / 能力信号 / 薄弱点 / 矛盾，实时显示在侧栏 |
| **复盘教练** | 面试结束后激活，读取观察记录 + 历史 Wiki，只提问、引导反思，对比「上次 vs 这次」 |

## Wiki 维护三 Agent（工具循环）

这三个 agent 通过 function calling 直接读写 wiki 文件（`read_page` / `write_page` /
`search` / …），以 `wiki/WIKI_SCHEMA.md` 为规约自主维护画像：

| Agent | 操作 | 职责 |
|---|---|---|
| **Ingest** | 写入 | 每场面试结束，把源（观察记录+复盘）增量整合进画像：更新颗粒页、维护 `[[互链]]`、刷新 index / log，原始记录不可变落盘到 `sources/` |
| **Query** | 问答 | 「问问你的画像」：检索相关页、带 `[[引用]]` 作答；好答案可回填 `answers/` |
| **Lint** | 体检 | 健康检查（证据单薄的能力、未验证的盲区、矛盾、孤儿页），并产出**下一场面试的提纲**，可一键带入新面试 |

完整流程：**配置 → 面试 → 即时反馈 → 复盘对话 → Ingest 写入 Wiki → 浏览 / Query / Lint**。

## 技术栈

- 后端：Python + FastAPI（流式用 ndjson）
- 前端：原生 HTML / CSS / JS（颗粒页渲染：隐藏 frontmatter、`[[链接]]`可点击跳转）
- 模型：阿里云 Qwen，经 DashScope 的 OpenAI 兼容接口接入
  - 对话类（面试官/观察者/教练）：`QWEN_MODEL`（默认 `qwen-plus`）
  - Wiki agent（ingest/query/lint，需工具调用）：`AGENT_MODEL`（默认 `qwen3.6-plus`）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env        # Windows: copy .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY（从 https://dashscope.console.aliyun.com 获取）

# 3. 启动
uvicorn backend.main:app --reload

# 4. 打开浏览器
# http://127.0.0.1:8000
```

## 演示脚本（约 8 分钟）

1. **友善模式面试**（2 min）：选岗位、友善模式开场，观察侧栏实时出现「内心独白」和「观察者记录」。
2. **切换高压模式**（1.5 min）：点「切换为高压模式」，对比面试官语气/策略变化。
3. **复盘教练登场**（1.5 min）：结束面试 → 看即时点评 → 进复盘，教练以提问方式引导。
4. **Ingest 写入 Wiki**（1.5 min）：点「整理并写入 Wiki」，看 agent 实时活动流逐页创建/更新，
   完成后浏览颗粒页、点 `[[链接]]` 在经历↔能力↔盲区之间跳转。
5. **Query**（0.5 min）：点「问问画像」，问「我有哪些证据支撑领导力？」看带引用的回答。
6. **Lint**（1 min）：点「体检 · 下场提纲」，看体检报告与「下次该问什么」，一键带入新面试 → 体现复利闭环。

## 个人 Wiki（颗粒化 LLM-Wiki 范式）

Wiki 不是流水账，而是一个由 agent 维护、随每场面试复利的「自我画像」：每个经历/能力/盲区
各自一页（含 YAML frontmatter + `[[互链]]`），知识被编译一次后持续保鲜，而非每次从零重写。

```
wiki/
  WIKI_SCHEMA.md          # 规约:结构/约定/流程的单一事实来源(人和 agent 共同迭代)
  index.md                # 全部页面目录
  log.md                  # 追加式时间线
  narrative.md            # 综合画像:我是谁
  experiences/<经历>.md   # 一个经历一页
  competencies/<能力>.md  # 一个能力一页(证据/演化/待验证)
  blind_spots/<盲区>.md   # 一个盲区一页(状态机:open/improving/resolved)
  sources/<面试>.md       # 不可变原始记录,真相来源
  answers/<问题>.md       # Query 回填的好答案
```

> **`wiki/` 是一个独立的 git 仓库**（与本代码仓库分离，且被本仓库 `.gitignore` 排除）。
> 每次 Ingest 后自动提交，给画像免费的版本历史，也防止覆盖式更新丢内容。
> 删除整个 `wiki/` 目录即可清空重来。
>
> 旧版「5 个巨石文件 + 单次整体覆盖」的画像已通过 `python -m tools.migrate_wiki` 迁移为颗粒页。
