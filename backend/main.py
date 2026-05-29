import json
import re
import uuid
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents, config, prompts, wiki

app = FastAPI(title="Interview Agent")

# 内存会话状态(演示原型,无数据库)
SESSIONS: dict[str, dict] = {}


# ---------- 请求模型 ----------
class StartReq(BaseModel):
    job: str
    style: str = "friendly"
    persona: str = ""


class MessageReq(BaseModel):
    session_id: str
    message: str


class SwitchReq(BaseModel):
    session_id: str
    style: str


class SessionReq(BaseModel):
    session_id: str


class QueryReq(BaseModel):
    history: list[dict] = []
    message: str


# ---------- 工具 ----------
def _jsonl(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _merge_records(store: dict, new: dict) -> None:
    for key in ["experiences", "competency_signals", "weak_points", "contradictions"]:
        store.setdefault(key, [])
        for item in new.get(key, []):
            store[key].append(item)


def _records_summary(store: dict, limit: int = 8) -> str:
    parts = []
    if store.get("weak_points"):
        parts.append("已记录薄弱点:" + "; ".join(store["weak_points"][-limit:]))
    if store.get("competency_signals"):
        sigs = [
            f"{s.get('competency')}({s.get('level')})" for s in store["competency_signals"][-limit:]
        ]
        parts.append("能力信号:" + "; ".join(sigs))
    if store.get("experiences"):
        exps = [e.get("title", "") for e in store["experiences"][-limit:]]
        parts.append("提到的经历:" + "; ".join(exps))
    return "\n".join(parts)


def _records_full_text(store: dict) -> str:
    return json.dumps(store, ensure_ascii=False, indent=2)


# ---------- 面试 ----------
@app.post("/api/session/start")
def start(req: StartReq):
    sid = uuid.uuid4().hex
    system = prompts.interviewer_system(req.job, req.style, req.persona)
    SESSIONS[sid] = {
        "config": req.model_dump(),
        "interview_messages": [{"role": "system", "content": system}],
        "review_messages": [],
        "observer": {},
        "last_reply": "",
        "feedback": "",
        "review_transcript": [],
    }
    sess = SESSIONS[sid]

    def gen():
        yield _jsonl({"type": "session", "session_id": sid})
        sess["interview_messages"].append(
            {"role": "user", "content": prompts.INTERVIEWER_OPENING}
        )
        reply_text = ""
        try:
            for channel, text in agents.interviewer_events(sess["interview_messages"]):
                if channel == "reply":
                    reply_text += text
                yield _jsonl({"type": channel, "text": text})
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"面试官生成出错:{exc}"})
            return
        sess["interview_messages"].append(
            {"role": "assistant", "content": reply_text}
        )
        sess["last_reply"] = reply_text
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/interview/message")
def interview_message(req: MessageReq):
    sess = SESSIONS.get(req.session_id)
    if not sess:
        return {"error": "会话不存在"}
    last_question = sess["last_reply"]
    sess["interview_messages"].append({"role": "user", "content": req.message})

    def gen():
        reply_text = ""
        try:
            for channel, text in agents.interviewer_events(sess["interview_messages"]):
                if channel == "reply":
                    reply_text += text
                yield _jsonl({"type": channel, "text": text})
            sess["interview_messages"].append(
                {"role": "assistant", "content": reply_text}
            )
            sess["last_reply"] = reply_text

            # 观察者:抽取本轮结构化信息
            new_rec = agents.observer_extract(
                _records_summary(sess["observer"]), last_question, req.message
            )
            _merge_records(sess["observer"], new_rec)
            yield _jsonl({"type": "observer", "record": new_rec})
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"生成出错:{exc}"})
            return
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/interview/switch_persona")
def switch_persona(req: SwitchReq):
    sess = SESSIONS.get(req.session_id)
    if not sess:
        return {"error": "会话不存在"}
    cfg = sess["config"]
    cfg["style"] = req.style
    sess["interview_messages"][0] = {
        "role": "system",
        "content": prompts.interviewer_system(cfg["job"], req.style, cfg["persona"]),
    }
    return {"ok": True, "style": req.style}


@app.post("/api/interview/end")
def interview_end(req: SessionReq):
    sess = SESSIONS.get(req.session_id)

    def gen():
        if not sess:
            yield _jsonl({"type": "error", "text": "会话不存在"})
            return
        feedback = ""
        try:
            for delta in agents.interviewer_feedback_stream(sess["interview_messages"]):
                feedback += delta
                yield _jsonl({"type": "reply", "text": delta})
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"生成点评出错:{exc}"})
            return
        sess["feedback"] = feedback
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------- 复盘 ----------
@app.post("/api/review/message")
def review_message(req: MessageReq):
    sess = SESSIONS.get(req.session_id)
    if not sess:
        return {"error": "会话不存在"}
    user_msg = req.message.strip() or "我准备好了,请开始复盘。"
    sess["review_messages"].append({"role": "user", "content": user_msg})
    sess["review_transcript"].append(f"我:{user_msg}")

    observer_text = _records_full_text(sess["observer"])
    wiki_sum = wiki.wiki_summary()

    def gen():
        reply_text = ""
        try:
            for delta in agents.coach_stream(
                sess["review_messages"], observer_text, wiki_sum
            ):
                reply_text += delta
                yield _jsonl({"type": "reply", "text": delta})
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"教练生成出错:{exc}"})
            return
        sess["review_messages"].append({"role": "assistant", "content": reply_text})
        sess["review_transcript"].append(f"教练:{reply_text}")
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------- Wiki: 工具循环 agent 的活动事件转人话 ----------
def _tool_activity(ev: dict) -> str | None:
    """把一次工具调用翻成活动流里的一行人话;不需要展示的返回 None。"""
    name, args = ev.get("name"), ev.get("args", {})
    path = args.get("path", "")
    if name == "read_page":
        return f"读取 {path}"
    if name == "write_page":
        return f"写入 {path}"
    if name == "delete_page":
        return f"删除 {path}"
    if name == "append_log":
        return "更新 log.md"
    if name == "search":
        return f"检索「{args.get('query', '')}」"
    if name == "list_files":
        return "浏览全部页面"
    return name


# ---------- 写入 Wiki(Ingest agent) ----------
@app.post("/api/wiki/commit")
def wiki_commit(req: SessionReq):
    sess = SESSIONS.get(req.session_id)

    def gen():
        if not sess:
            yield _jsonl({"type": "error", "text": "会话不存在"})
            return
        nth = wiki.next_interview_number()
        today = date.today().isoformat()
        observer = _records_full_text(sess["observer"])
        transcript = "\n".join(sess["review_transcript"]) or "(无复盘)"
        # 先把原始源不可变落盘
        source_id = f"interview-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        source_doc = (
            f"---\ntype: source\ninterview: {nth}\ndate: {today}\n---\n"
            f"# 面试 #{nth} 原始记录 ({today})\n\n"
            f"## 观察记录\n```json\n{observer}\n```\n\n## 复盘对话\n{transcript}\n"
        )
        wiki.save_source(source_id, source_doc)

        source_text = (
            f"观察记录(JSON):\n{observer}\n\n复盘对话:\n{transcript}\n\n"
            f"(原始记录已存于 {config.SOURCES_DIR}/{source_id}.md)"
        )
        summary = ""
        try:
            for ev in agents.ingest_events(source_text, today, nth):
                if ev["type"] == "tool":
                    line = _tool_activity(ev)
                    if line:
                        yield _jsonl({"type": "activity", "text": line})
                elif ev["type"] == "final":
                    summary = ev["text"]
                elif ev["type"] == "error":
                    yield _jsonl({"type": "error", "text": ev["text"]})
                    return
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"整理出错:{exc}"})
            return
        wiki.bump_interview_count()
        wiki.git_commit(f"面试#{nth}: {summary[:60] or '更新画像'}")
        yield _jsonl(
            {"type": "done", "summary": summary or "已更新个人 Wiki", "tree": wiki.get_tree()}
        )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------- Query: 问答画像 ----------
@app.post("/api/wiki/query")
def wiki_query(req: QueryReq):
    def gen():
        reply = ""
        try:
            for ev in agents.query_events(req.history, req.message):
                if ev["type"] == "tool":
                    line = _tool_activity(ev)
                    if line:
                        yield _jsonl({"type": "activity", "text": line})
                elif ev["type"] == "final":
                    reply = ev["text"]
                    yield _jsonl({"type": "reply", "text": reply})
                elif ev["type"] == "error":
                    yield _jsonl({"type": "error", "text": ev["text"]})
                    return
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"问答出错:{exc}"})
            return
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------- Lint: 体检 + 下场提纲 ----------
@app.post("/api/wiki/lint")
def wiki_lint():
    def gen():
        report = ""
        try:
            for ev in agents.lint_events():
                if ev["type"] == "tool":
                    line = _tool_activity(ev)
                    if line:
                        yield _jsonl({"type": "activity", "text": line})
                elif ev["type"] == "final":
                    report = ev["text"]
                elif ev["type"] == "error":
                    yield _jsonl({"type": "error", "text": ev["text"]})
                    return
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"体检出错:{exc}"})
            return
        questions = _extract_next_questions(report)
        yield _jsonl({"type": "report", "text": report, "questions": questions})
        yield _jsonl({"type": "done"})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _extract_next_questions(report: str) -> list[str]:
    """从 lint 报告末尾的 fenced json 里取出 next_questions。"""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", report or "", re.DOTALL)
    if not m:
        return []
    try:
        return list(json.loads(m.group(1)).get("next_questions", []))[:5]
    except json.JSONDecodeError:
        return []


@app.get("/api/wiki/tree")
def wiki_tree():
    return {"tree": wiki.get_tree(), "interviews": wiki.interview_count()}


@app.get("/api/wiki/file")
def wiki_file(path: str):
    return {"path": path, "content": wiki.read_relative(path)}


# ---------- 前端静态资源 ----------
@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
