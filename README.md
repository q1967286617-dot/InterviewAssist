# Interview Agent — 通过面试，认识自己

一个 agentic Web 应用：通过模拟面试持续沉淀「自我画像」。三个协作 agent + 随时间增长的个人 Wiki。

## 三个 Agent

| Agent | 职责 |
|---|---|
| **面试官** | 主导面试，支持岗位/风格（友善·高压）配置，可中途切换风格；每次回复同时产出「内心独白」与「对外回复」 |
| **观察者/书记员** | 静默旁听，每轮抽取经历 / 能力信号 / 薄弱点 / 矛盾，实时显示在侧栏 |
| **复盘教练** | 面试结束后激活，读取观察记录 + 历史 Wiki，只提问、引导反思，对比「上次 vs 这次」 |

完整流程：**配置 → 面试 → 即时反馈 → 复盘对话 → 写入 Wiki → 浏览 Wiki**。

## 技术栈

- 后端：Python + FastAPI（流式用 ndjson）
- 前端：原生 HTML / CSS / JS
- 模型：阿里云 Qwen，经 DashScope 的 OpenAI 兼容接口接入

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

## 演示脚本（约 7 分钟）

1. **友善模式面试**（2 min）：选岗位、友善模式开场，观察侧栏实时出现「内心独白」和「观察者记录」。
2. **切换高压模式**（2 min）：点「切换为高压模式」，对比面试官语气/策略变化。
3. **复盘教练登场**（2 min）：结束面试 → 看即时点评 → 进复盘，教练以提问方式引导。
4. **展示 Wiki**（1 min）：点「整理并写入 Wiki」，浏览生成的 `experiences / competencies / blind_spots / growth_log / narrative.md`。
5. 再跑一次面试，验证 `growth_log` 出现「本次 vs 上次」的 delta —— 体现随时间复利增长。

## 个人 Wiki 结构

```
wiki/
  experiences/    经历库
  competencies/   能力图谱
  blind_spots/    盲区记录
  growth_log/     成长日志（每场 delta）
  narrative.md    个人叙事（我是谁）
```

> Wiki 以文件形式落地，跨会话持续累积。删除 `wiki/` 目录即可清空重来。
