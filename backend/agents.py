"""面试三 agent + Wiki 维护三 agent 的调用逻辑。"""
import json
from typing import Iterator

from . import config, prompts, qwen_client, wiki

MONO_MARK = "[独白]"
REPLY_MARK = "[回复]"


def interviewer_events(messages: list[dict]) -> Iterator[tuple[str, str]]:
    """流式产出 (channel, text_delta),channel 为 'monologue' 或 'reply'。

    模型输出形如:[独白]...[回复]...  在流中按标记切换通道。
    """
    buffer = ""
    channel = "monologue"  # 标记出现前默认归到独白
    switched = False
    full_raw = ""  # 累积全部原始输出,用于模型不守格式时兜底
    for delta in qwen_client.stream_chat(messages, temperature=0.85):
        buffer += delta
        full_raw += delta
        if not switched:
            # 还没切换到 reply,持续找 [回复] 标记
            idx = buffer.find(REPLY_MARK)
            if idx != -1:
                before = buffer[:idx].replace(MONO_MARK, "")
                if before.strip():
                    yield ("monologue", before)
                buffer = buffer[idx + len(REPLY_MARK) :]
                channel = "reply"
                switched = True
                if buffer:
                    yield ("reply", buffer)
                    buffer = ""
            else:
                # 安全地吐出已确定不含标记起始的部分
                emit = buffer.replace(MONO_MARK, "")
                # 保留尾部可能是标记前缀的字符
                keep = len(REPLY_MARK) - 1
                if len(emit) > keep:
                    out, buffer = emit[:-keep], emit[-keep:]
                    if out.strip():
                        yield ("monologue", out)
        else:
            yield ("reply", buffer)
            buffer = ""
    if switched:
        if buffer:
            yield ("reply", buffer)
    else:
        # 模型从未输出 [回复] 标记:把整段(去掉标记)当作回复吐出,
        # 保证前端机器人气泡不为空。
        fallback = full_raw.replace(MONO_MARK, "").replace(REPLY_MARK, "").strip()
        if fallback:
            yield ("reply", fallback)


def interviewer_feedback_stream(messages: list[dict]) -> Iterator[str]:
    """流式产出本场即时点评文本。"""
    msgs = messages + [{"role": "user", "content": prompts.INTERVIEWER_FEEDBACK}]
    yield from qwen_client.stream_chat(msgs, temperature=0.6)


def observer_extract(notes_summary: str, question: str, answer: str) -> dict:
    msgs = [
        {"role": "system", "content": prompts.OBSERVER_SYSTEM},
        {
            "role": "user",
            "content": prompts.OBSERVER_USER.format(
                notes_summary=notes_summary or "(暂无)",
                question=question or "(开场)",
                answer=answer,
            ),
        },
    ]
    data = qwen_client.chat_json(msgs)
    return {
        "experiences": data.get("experiences", []),
        "competency_signals": data.get("competency_signals", []),
        "weak_points": data.get("weak_points", []),
        "contradictions": data.get("contradictions", []),
    }


def coach_stream(
    history: list[dict], observer_record: str, wiki_summary: str
) -> Iterator[str]:
    system = prompts.COACH_SYSTEM.format(
        observer_record=observer_record or "(无)",
        wiki_summary=wiki_summary or "(空,这是第一次面试)",
    )
    msgs = [{"role": "system", "content": system}] + history
    yield from qwen_client.stream_chat(msgs, temperature=0.75)


# ============ Wiki 维护 agent(工具循环) ============

def _def(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


_STR = {"type": "string"}

_READ_TOOLS = [
    _def("read_page", "读取一个 wiki 页面的完整内容(含 frontmatter)。", {"path": _STR}, ["path"]),
    _def("list_files", "列出 wiki 中全部页面的相对路径。", {}, []),
    _def("search", "对全部页面做全文检索,返回相关页路径与片段。", {"query": _STR}, ["query"]),
]
_WRITE_TOOLS = [
    _def(
        "write_page",
        "写入(整文件覆盖)一个 wiki 页面,需写完整内容含 frontmatter。",
        {"path": _STR, "content": _STR},
        ["path", "content"],
    ),
    _def("delete_page", "删除一个 wiki 页面(用于合并重复页)。", {"path": _STR}, ["path"]),
    _def("append_log", "向 log.md 追加一条记录。", {"line": _STR}, ["line"]),
]


def _read_handlers() -> dict:
    return {
        "read_page": lambda a: wiki.read_page(a.get("path", "")),
        "list_files": lambda a: "\n".join(wiki.list_files()) or "(空)",
        "search": lambda a: json.dumps(
            wiki.search(a.get("query", "")), ensure_ascii=False
        ),
    }


def _write_handlers() -> dict:
    return {
        "write_page": lambda a: wiki.write_page(a.get("path", ""), a.get("content", "")),
        "delete_page": lambda a: wiki.delete_page(a.get("path", "")),
        "append_log": lambda a: wiki.append_log(a.get("line", "")),
    }


def _schema_text() -> str:
    txt = wiki.read_page(config.SCHEMA_FILE)
    return txt if "页面不存在" not in txt else "(规约文件缺失)"


def ingest_events(source_text: str, date: str, nth: int) -> Iterator[dict]:
    """Ingest:把一场面试的源整合进 Wiki。产出工具循环事件。"""
    wiki.ensure_dirs()
    messages = [
        {"role": "system", "content": prompts.INGEST_SYSTEM.format(schema=_schema_text())},
        {
            "role": "user",
            "content": prompts.INGEST_USER.format(date=date, nth=nth, source=source_text),
        },
    ]
    tools = _READ_TOOLS + _WRITE_TOOLS
    handlers = {**_read_handlers(), **_write_handlers()}
    yield from qwen_client.tool_loop(messages, tools, handlers, temperature=0.4)


def query_events(history: list[dict], question: str) -> Iterator[dict]:
    """Query:对画像提问。history 为既往 {role,content} 列表(不含 system)。"""
    wiki.ensure_dirs()
    messages = (
        [{"role": "system", "content": prompts.QUERY_SYSTEM.format(schema=_schema_text())}]
        + history
        + [{"role": "user", "content": question}]
    )
    tools = _READ_TOOLS + _WRITE_TOOLS  # 可写,但 prompt 限定只写 answers/
    handlers = {**_read_handlers(), **_write_handlers()}
    yield from qwen_client.tool_loop(messages, tools, handlers, temperature=0.5)


def lint_events() -> Iterator[dict]:
    """Lint:体检并产出下场面试提纲。只读。"""
    wiki.ensure_dirs()
    messages = [
        {"role": "system", "content": prompts.LINT_SYSTEM.format(schema=_schema_text())},
        {"role": "user", "content": "请对我的画像做一次体检,并给出下一场面试的提纲。"},
    ]
    yield from qwen_client.tool_loop(
        messages, _READ_TOOLS, _read_handlers(), temperature=0.4
    )
