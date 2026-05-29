"""三个 agent 的调用逻辑。"""
import json
from typing import Iterator

from . import prompts, qwen_client

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


def _synthesize_messages(
    observer_record: str, review_transcript: str, current_wiki: dict, date: str, nth: int
) -> list[dict]:
    user = (
        f"今天日期:{date},这是第 {nth} 次面试。\n\n"
        f"本场观察记录:\n{observer_record}\n\n"
        f"复盘对话:\n{review_transcript or '(无)'}\n\n"
        f"现有 Wiki 各分区内容:\n{json.dumps(current_wiki, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": prompts.SYNTHESIZER_SYSTEM},
        {"role": "user", "content": user},
    ]


def synthesize_wiki_stream(
    observer_record: str, review_transcript: str, current_wiki: dict, date: str, nth: int
) -> Iterator[str]:
    """流式产出合成 Wiki 的原始文本(JSON),由调用方累积后解析。"""
    msgs = _synthesize_messages(
        observer_record, review_transcript, current_wiki, date, nth
    )
    yield from qwen_client.stream_chat(msgs, temperature=0.5)
