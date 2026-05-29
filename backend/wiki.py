"""颗粒化个人 Wiki 的文件操作层。

Wiki 是一组 markdown 颗粒页(每个经历/能力/盲区一页),由 agent 通过工具维护。
本模块只负责安全的文件 IO、检索、导航与 git 版本化,不含任何 LLM 逻辑。

目录结构见 wiki/WIKI_SCHEMA.md。
"""
import re
import subprocess
from pathlib import Path

from . import config

# 允许 agent 读写的相对路径前缀(防止越权)
_ALLOWED_PREFIXES = tuple(config.WIKI_CATEGORIES) + (
    config.SOURCES_DIR,
    config.ANSWERS_DIR,
)
_TOP_FILES = (config.NARRATIVE_FILE, config.INDEX_FILE, config.LOG_FILE)


# ---------- 基础设施 ----------
_SCHEMA_TEMPLATE = Path(__file__).resolve().parent / "wiki_schema_default.md"


def ensure_dirs() -> None:
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    for d in config.WIKI_CATEGORIES + [config.SOURCES_DIR, config.ANSWERS_DIR]:
        (config.WIKI_DIR / d).mkdir(parents=True, exist_ok=True)
    # 首次运行播种规约文件(随代码分发的默认模板),已存在则保留用户/agent 的改动
    schema = config.WIKI_DIR / config.SCHEMA_FILE
    if not schema.exists() and _SCHEMA_TEMPLATE.exists():
        schema.write_text(_SCHEMA_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")


def _safe_target(relpath: str) -> Path | None:
    """把相对路径解析为 wiki 内的绝对路径;越界或非法返回 None。"""
    relpath = (relpath or "").strip().lstrip("/\\")
    if not relpath:
        return None
    target = (config.WIKI_DIR / relpath).resolve()
    if not target.is_relative_to(config.WIKI_DIR.resolve()):
        return None
    return target


def _is_writable(relpath: str) -> bool:
    rel = (relpath or "").strip().lstrip("/\\").replace("\\", "/")
    if rel in _TOP_FILES:
        return True
    return rel.startswith(tuple(p + "/" for p in _ALLOWED_PREFIXES))


# ---------- 颗粒页读写(供 agent 工具调用) ----------
def read_page(relpath: str) -> str:
    target = _safe_target(relpath)
    if target is None or not target.exists() or not target.is_file():
        return f"(页面不存在: {relpath})"
    return target.read_text(encoding="utf-8")


def write_page(relpath: str, content: str) -> str:
    if not _is_writable(relpath):
        return f"(拒绝写入越权路径: {relpath})"
    target = _safe_target(relpath)
    if target is None:
        return f"(非法路径: {relpath})"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 {relpath} ({len(content)} 字)"


def delete_page(relpath: str) -> str:
    if not _is_writable(relpath):
        return f"(拒绝删除越权路径: {relpath})"
    target = _safe_target(relpath)
    if target is None or not target.exists():
        return f"(页面不存在: {relpath})"
    target.unlink()
    return f"已删除 {relpath}"


def append_log(line: str) -> str:
    """向 log.md 追加一行/一段。"""
    ensure_dirs()
    path = config.WIKI_DIR / config.LOG_FILE
    prev = path.read_text(encoding="utf-8") if path.exists() else "# 时间线\n"
    sep = "" if prev.endswith("\n") else "\n"
    path.write_text(prev + sep + line.rstrip() + "\n", encoding="utf-8")
    return "已追加 log.md"


def list_files() -> list[str]:
    """列出全部 wiki 页面的相对路径(不含 schema/sources 的原始大文件可选)。"""
    ensure_dirs()
    out = []
    for f in _TOP_FILES:
        if (config.WIKI_DIR / f).exists():
            out.append(f)
    for d in config.WIKI_CATEGORIES + [config.ANSWERS_DIR, config.SOURCES_DIR]:
        base = config.WIKI_DIR / d
        if base.exists():
            for p in sorted(base.glob("*.md")):
                out.append(f"{d}/{p.name}")
    return out


def read_index() -> str:
    return read_page(config.INDEX_FILE)


def search(query: str, limit: int = 20) -> list[dict]:
    """对全部页面做朴素全文检索,返回 {path, snippet} 列表。

    规模小,index + 朴素匹配足够,无需向量检索。
    """
    query = (query or "").strip()
    if not query:
        return []
    terms = [t for t in re.split(r"\s+", query) if t]
    results = []
    for rel in list_files():
        text = read_page(rel)
        low = text.lower()
        score = sum(low.count(t.lower()) for t in terms)
        if score:
            idx = min((low.find(t.lower()) for t in terms if t.lower() in low), default=0)
            start = max(0, idx - 40)
            snippet = text[start : start + 160].replace("\n", " ")
            results.append({"path": rel, "score": score, "snippet": snippet})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ---------- frontmatter 解析(供 lint / 导航 / 渲染) ----------
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """极简 YAML frontmatter 解析(只处理 key: value 与简单数组)。返回 (meta, body)。"""
    m = _FM_RE.match(text or "")
    if not m:
        return {}, text or ""
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            meta[key] = val
    return meta, body


# ---------- 面试计数(沿用 log/源数量,改读 frontmatter 计数文件) ----------
_META_FILE = ".meta.json"


def _meta_path() -> Path:
    return config.WIKI_DIR / _META_FILE


def interview_count() -> int:
    import json

    p = _meta_path()
    if p.exists():
        try:
            return int(json.loads(p.read_text(encoding="utf-8")).get("interviews", 0))
        except (ValueError, OSError):
            return 0
    return 0


def next_interview_number() -> int:
    return interview_count() + 1


def bump_interview_count() -> int:
    import json

    n = interview_count() + 1
    _meta_path().write_text(
        json.dumps({"interviews": n}, ensure_ascii=False), encoding="utf-8"
    )
    return n


# ---------- 原始源持久化 ----------
def save_source(source_id: str, content: str) -> str:
    rel = f"{config.SOURCES_DIR}/{source_id}.md"
    return write_page(rel, content)


# ---------- 给复盘教练的精简摘要 ----------
def wiki_summary(max_chars: int = 1500) -> str:
    """综合画像 + 目录,供复盘教练快速了解"过往的你"。"""
    ensure_dirs()
    parts = []
    narrative = read_page(config.NARRATIVE_FILE)
    if narrative and "页面不存在" not in narrative:
        _, body = split_frontmatter(narrative)
        parts.append("## 综合画像\n" + body.strip())
    index = read_index()
    if index and "页面不存在" not in index:
        parts.append("## 画像目录\n" + index.strip())
    return ("\n\n".join(parts))[:max_chars]


# ---------- 前端文件树 ----------
def get_tree() -> list[dict]:
    """返回前端展示用的嵌套文件树。"""
    ensure_dirs()
    tree: list[dict] = []

    def file_node(rel: str, label: str) -> dict:
        return {"label": label, "path": rel, "type": "file"}

    for f, label in [
        (config.NARRATIVE_FILE, "narrative.md"),
        (config.INDEX_FILE, "index.md"),
        (config.LOG_FILE, "log.md"),
    ]:
        if (config.WIKI_DIR / f).exists():
            tree.append(file_node(f, label))

    for d in config.WIKI_CATEGORIES + [config.ANSWERS_DIR]:
        base = config.WIKI_DIR / d
        children = []
        if base.exists():
            for p in sorted(base.glob("*.md")):
                children.append(file_node(f"{d}/{p.name}", p.stem))
        tree.append({"label": d, "type": "dir", "children": children})
    return tree


def read_relative(relpath: str) -> str:
    """前端读取任意 wiki 页面(含 sources)。"""
    target = _safe_target(relpath)
    if target is None or not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


# ---------- git 版本化 ----------
def git_commit(message: str) -> str:
    """对 wiki 目录做一次提交。wiki 是独立的 git 仓库,与代码仓库分离。

    若 wiki 还不是 git 仓库则先 init。失败静默返回提示(不影响主流程)。
    """
    wiki_dir = str(config.WIKI_DIR)
    try:
        if not (config.WIKI_DIR / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=wiki_dir, check=True)
            subprocess.run(
                ["git", "config", "user.name", "wiki-agent"], cwd=wiki_dir, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "wiki@local"], cwd=wiki_dir, check=True
            )
        subprocess.run(["git", "add", "-A"], cwd=wiki_dir, check=True)
        # 没有变更时 commit 会失败,忽略
        r = subprocess.run(
            ["git", "commit", "-q", "-m", message], cwd=wiki_dir
        )
        return "已提交" if r.returncode == 0 else "无变更可提交"
    except (subprocess.SubprocessError, OSError) as e:
        return f"git 跳过: {e}"
