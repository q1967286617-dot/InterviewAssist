import json
import re
from typing import Iterator

from openai import OpenAI

from . import config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.QWEN_BASE_URL,
        )
    return _client


def stream_chat(messages: list[dict], temperature: float = 0.8) -> Iterator[str]:
    """流式调用,逐段产出文本增量。"""
    stream = get_client().chat.completions.create(
        model=config.QWEN_MODEL,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


def chat(messages: list[dict], temperature: float = 0.7) -> str:
    """一次性返回完整文本。"""
    resp = get_client().chat.completions.create(
        model=config.QWEN_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def chat_json(messages: list[dict], temperature: float = 0.3) -> dict:
    """要求模型返回 JSON 对象,带解析容错。失败时返回空 dict。"""
    text = chat(messages, temperature=temperature)
    return _extract_json(text)


def extract_json(text: str) -> dict:
    """从一段(可能带 ```json 包裹或多余文字的)文本中解析出 JSON 对象。

    供流式调用结束后解析累积文本使用。失败时返回空 dict。
    """
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    # 去掉可能的 ```json ... ``` 包裹
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # 退而求其次:截取第一个 { 到最后一个 }
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}
