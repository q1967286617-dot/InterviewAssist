"""一次性迁移:把旧的巨石 Wiki(每分区一个 main.md)爆破成颗粒页。

流程:
  1. 给当前 wiki 打 git 快照(可回退)。
  2. 把旧 main.md 内容喂给一个工具循环 agent,让它按 WIKI_SCHEMA 创建颗粒页 +
     index.md + log.md,并保留 narrative.md。
  3. 删除旧的 main.md 与 growth_log 目录。
  4. 再打一次 git 快照。

用法:  python -m tools.migrate_wiki
"""
from pathlib import Path

from backend import agents, config, qwen_client, wiki


def _old(section: str) -> str:
    p = config.WIKI_DIR / section / "main.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main() -> None:
    wiki.ensure_dirs()
    print("① 迁移前快照:", wiki.git_commit("pre-migration: 巨石 wiki 快照"))

    old_exp = _old("experiences")
    old_comp = _old("competencies")
    old_blind = _old("blind_spots")
    old_growth = _old("growth_log")
    narrative = (config.WIKI_DIR / config.NARRATIVE_FILE)
    narrative_txt = narrative.read_text(encoding="utf-8") if narrative.exists() else ""

    if not (old_exp or old_comp or old_blind):
        print("没有发现旧巨石内容,跳过迁移。")
        return

    schema = wiki.read_page(config.SCHEMA_FILE)
    system = (
        "你是个人画像 Wiki 的迁移 agent。下面是 Wiki 规约:\n\n"
        f"{schema}\n\n"
        "你通过工具写文件:write_page / read_page / append_log。"
        "write_page 是整文件覆盖,要写完整内容含 frontmatter。"
    )
    user = f"""下面是旧版「巨石」Wiki 的内容(每个分区一整块)。请把它们**拆解成颗粒页**,
严格遵守规约的目录结构、frontmatter 和 [[互链]]约定:

- 把【经历库】拆成 experiences/<标题>.md,一个经历一页。
- 把【能力图谱】每一行能力拆成 competencies/<能力>.md 一页,把表格里的证据转成「## 证据」列表,
  并尽量在证据里 [[链接]]到对应经历页。
- 把【盲区记录】每条拆成 blind_spots/<盲区>.md 一页,关联经历用 [[链接]]。
- 在能力/盲区页里补上反向链接,在经历页里列出「体现的能力」「暴露的盲区」并 [[链接]]。
- 根据【成长日志】内容,写出 log.md(把已有的成长记录作为历史条目)。
- 用全部颗粒页建立 index.md(按类别,每页一行 `- [[标题]] — 摘要`)。
- narrative.md 已存在,保持不变(不要改它)。
- frontmatter 里的面试场次:这些内容来自前 3 场面试,interviews 字段酌情填 [1,2,3] 或你能判断的子集。

【经历库】
{old_exp}

【能力图谱】
{old_comp}

【盲区记录】
{old_blind}

【成长日志】
{old_growth}

请开始逐页创建。完成后用一句话总结建了哪些页。"""

    tools = agents._READ_TOOLS + agents._WRITE_TOOLS
    handlers = {**agents._read_handlers(), **agents._write_handlers()}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    print("② 开始拆解(工具循环)…\n")
    for ev in qwen_client.tool_loop(messages, tools, handlers, temperature=0.4, max_iters=60):
        if ev["type"] == "tool":
            print(f"   · {ev['name']}({ev['args'].get('path', ev['args'].get('query',''))}) -> {ev['result'][:50]}")
        elif ev["type"] == "final":
            print("\n③ agent 总结:", ev["text"][:400])
        elif ev["type"] == "error":
            print("\n[错误]", ev["text"])

    # 删除旧巨石
    for section in ["experiences", "competencies", "blind_spots", "growth_log"]:
        mp = config.WIKI_DIR / section / "main.md"
        if mp.exists():
            mp.unlink()
            print("   删除旧文件:", mp.relative_to(config.WIKI_DIR))
    # growth_log 目录(已并入 log.md)清掉
    gl = config.WIKI_DIR / "growth_log"
    if gl.exists() and not any(gl.iterdir()):
        gl.rmdir()

    print("\n④ 迁移后快照:", wiki.git_commit("migration: 颗粒化拆解完成"))
    print("\n完成。当前页面:")
    for f in wiki.list_files():
        print("   -", f)


if __name__ == "__main__":
    main()
