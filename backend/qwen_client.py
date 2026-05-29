import json
import re
from typing import Callable, Iterator

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


def tool_loop(
    messages: list[dict],
    tools: list[dict],
    handlers: dict[str, Callable[[dict], str]],
    model: str | None = None,
    temperature: float = 0.4,
    max_iters: int = 24,
) -> Iterator[dict]:
    """运行一个 function-calling 工具循环,产出事件供上层流式展示。

    事件类型:
      {"type": "tool", "name", "args", "result"}  每次工具调用及其结果
      {"type": "final", "text"}                    模型不再调用工具时的收尾文本
      {"type": "error", "text"}                    出错

    handlers: 工具名 -> 处理函数(接收参数 dict,返回字符串结果)。
    """
    client = get_client()
    model = model or config.AGENT_MODEL
    convo = list(messages)
    for _ in range(max_iters):
        resp = client.chat.completions.create(
            model=model,
            messages=convo,
            tools=tools,
            temperature=temperature,
        )
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        # 把助手这一轮(可能含 tool_calls)原样加入对话
        convo.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in calls
                ],
            }
            if calls
            else {"role": "assistant", "content": msg.content or ""}
        )
        if not calls:
            yield {"type": "final", "text": msg.content or ""}
            return
        for c in calls:
            name = c.function.name
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            handler = handlers.get(name)
            if handler is None:
                result = f"(未知工具: {name})"
            else:
                try:
                    result = handler(args)
                except Exception as e:  # 工具内部异常也回喂模型,让它自愈
                    result = f"(工具 {name} 执行出错: {e})"
            yield {"type": "tool", "name": name, "args": args, "result": result}
            convo.append(
                {"role": "tool", "tool_call_id": c.id, "content": str(result)}
            )
    yield {"type": "error", "text": f"达到最大工具调用轮数({max_iters})上限"}


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
