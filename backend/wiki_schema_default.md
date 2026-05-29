---
type: schema
updated: 2026-05-29
---
# WIKI_SCHEMA — 个人画像 Wiki 的维护规约

这是「通过面试认识自己」这款应用的个人 Wiki 的**规约层**。所有维护 Wiki 的
agent（ingest / query / lint）都以本文件为唯一事实来源。人和 agent 可以共同
迭代本文件——它定义了 Wiki 长什么样、怎么维护、各操作的流程。

Wiki 的本质：它**不是流水账**，而是一个随每场面试持续复利的「自我画像」。
每场面试是一个**源**；agent 读取源，把信息**增量整合**进已有页面——更新实体页、
修订摘要、标记矛盾、强化或挑战正在演化的综合判断。知识被**编译一次，然后持续保鲜**，
而不是每次从零重写。

---

## 一、目录结构

```
wiki/
  WIKI_SCHEMA.md          # 本文件:规约
  index.md                # 全部页面目录(catalog),按类别,每页一行摘要
  log.md                  # 追加式时间线,记录每次 ingest/query/lint
  narrative.md            # 综合画像:"我是谁"
  experiences/<slug>.md   # 一个经历(项目/实习/作品)一页
  competencies/<slug>.md  # 一个能力维度一页
  blind_spots/<slug>.md   # 一个盲区一页
  sources/<id>.md         # 不可变原始源(每场面试的观察记录+复盘),只读不改
  answers/<slug>.md       # Query 模式中值得留存的好答案,回填于此
```

- `<slug>` 用简短的、人类可读的标识。中文标题可直接做文件名（如
  `experiences/校园信用卡推广.md`）。同一实体只能有一页——**新信息合并进已有页，
  而不是新建重复页**。整合前务必先读 `index.md` 判断是否已存在。
- `sources/` 是真相来源，**永不修改**。

## 二、页面格式

每个页面以 YAML frontmatter 开头，其后是 markdown 正文。frontmatter 供 lint 与
导航使用，正文给人读。

**经历页 `experiences/<slug>.md`：**
```markdown
---
type: experience
title: 校园信用卡推广
interviews: [1, 2]        # 哪几场面试提到
first_seen: 2026-04-10
last_seen: 2026-05-28
---
# 校园信用卡推广

## 概要
（一两句话）

## 要点
- ...

## 体现的能力
- [[问题洞察力]] —— 通过蹲点观察识别放弃临界点
- [[执行力与项目统筹]] —— ...

## 暴露的盲区
- [[量化归因习惯缺位]]
```

**能力页 `competencies/<slug>.md`：**
```markdown
---
type: competency
title: 问题洞察力
level: 强                  # 弱 / 中 / 强 / 卓越
status: strengthening      # new / strengthening / stable / weakening
evidence_count: 3
interviews: [1, 2, 3]
first_seen: 2026-04-10
last_seen: 2026-05-29
---
# 问题洞察力

## 证据
- 面试#1:[[校园信用卡推广]] 中通过蹲点识别放弃行为（信号:强）
- 面试#3:...

## 演化
- 面试#1 评级「中」→ 面试#3 上调「强」,因...

## 待验证
- 尚缺在 X 场景下的证据
```

**盲区页 `blind_spots/<slug>.md`：**
```markdown
---
type: blind_spot
title: 量化归因习惯缺位
status: open               # open / improving / resolved
interviews: [1, 2]
first_seen: 2026-04-10
last_seen: 2026-05-28
---
# 量化归因习惯缺位

## 表现
- ...

## 关联经历
- [[校园信用卡推广]]

## 历史
- 面试#1:首次发现
- 面试#2:仍未形成"先设指标再行动"的本能
```

## 三、互链规则

- 用 `[[页面标题]]` 互链，标题对应目标页 frontmatter 的 `title`。
- **经历页**链接到它体现的能力、暴露的盲区；**能力/盲区页**反向链接回证据经历。
- 链接要双向：在 A 里提到 B，就尽量在 B 里也提到 A。这张网就是画像的价值。

## 四、index.md 格式

按类别组织的目录，每页一行：`- [[标题]] — 一句话摘要`。每次 ingest 后更新。
query 时先读 index 找到相关页，再深入。

## 五、log.md 格式

追加式，每条以统一前缀开头便于检索：
```
## [2026-05-29] ingest | 面试#3 | 触及 N 页
- 新建 competencies/专业迁移思考.md
- 更新 narrative.md
...
```

## 六、三个操作

**Ingest（写入）** —— 每场面试结束触发。流程：
1. 先读 `index.md` 了解现有全貌。
2. 根据本场源（观察记录 + 复盘对话）判断要触及哪些页：读取相关已有页，
   增量合并新信息（**保留旧内容**，不要丢弃；矛盾就显式标记而非覆盖）。
3. 该新建的新建，该更新的更新，维护好双向 `[[互链]]`。
4. 更新 `narrative.md`（综合重写）、`index.md`（目录）、追加 `log.md`。
5. 完成后简述本场做了哪些改动。

**Query（问答）** —— 对画像提问。流程：先读 `index.md` 与 `search` 定位相关页，
读取后综合作答，**带 `[[页面]]` 引用**。若答案有长期价值，可写入 `answers/`。
默认只读，不要改动实体页。

**Lint（体检）** —— 健康检查并产出**下一场面试的提纲**。检查：
- 证据单薄的能力（evidence_count 低 / 只有 1 场面试）
- 状态仍为 open 的盲区（上次说要改，这次验证了吗？）
- 页面间的矛盾、过时结论
- 孤儿页（没有任何入链）、缺失的概念页、缺失的双向链接
报告末尾**必须**给出 3~5 个「下次面试官应聚焦的问题」，用于驱动下一场面试。
