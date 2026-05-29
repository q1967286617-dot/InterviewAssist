import json
import uuid
from datetime import date

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents, config, prompts, qwen_client, wiki

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


# ---------- 写入 Wiki ----------
@app.post("/api/wiki/commit")
def wiki_commit(req: SessionReq):
    sess = SESSIONS.get(req.session_id)

    def gen():
        if not sess:
            yield _jsonl({"type": "error", "text": "会话不存在"})
            return
        raw = ""
        try:
            for delta in agents.synthesize_wiki_stream(
                observer_record=_records_full_text(sess["observer"]),
                review_transcript="\n".join(sess["review_transcript"]),
                current_wiki=wiki.read_current_wiki(),
                date=date.today().isoformat(),
                nth=wiki.next_interview_number(),
            ):
                raw += delta
                # 上报已生成字数,让前端展示进度(原始 JSON 不直接渲染)
                yield _jsonl({"type": "progress", "chars": len(raw)})
        except Exception as exc:
            yield _jsonl({"type": "error", "text": f"整理出错:{exc}"})
            return
        synth = qwen_client.extract_json(raw)
        if not synth:
            yield _jsonl({"type": "error", "text": "整理失败,请重试"})
            return
        summary = wiki.write_wiki(synth)
        yield _jsonl({"type": "done", "summary": summary, "tree": wiki.get_tree()})

    return StreamingResponse(gen(), media_type="application/x-ndjson")


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
