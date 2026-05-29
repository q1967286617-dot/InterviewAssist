"""自动跑通完整面试流程:扮演一名应届本科生应聘银行管培生。

候选人的回答由 Qwen 实时生成(读取面试官的真实提问),保证是一场真实对话。
全程记录写入 transcripts/ 下的 markdown 文件,便于回档查看。
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import qwen_client  # noqa: E402

BASE = "http://127.0.0.1:8123"

CANDIDATE_SYSTEM = """你在参加一场银行管培生岗位的面试,扮演候选人本人,用第一人称回答。

人设:
- 你叫林知遥,某综合性大学经济学本科应届毕业生,GPA 中上。
- 经历:在某城商行网点做过 2 个月大堂实习;担任过院学生会财务部干事;做过一个《区域消费数据分析》课程项目;大二组织过一次校园信用卡推广活动(拉新效果不错)。
- 性格特点(请自然地表现出来,不要刻意点破):
  1) 表达积极、有亲和力,但谈成绩时经常缺乏具体数字,爱用"挺多""不少""效果挺好"这类模糊说法。
  2) 谈到"领导力"时,你习惯举学生会财务部的例子(其实较弱),而那次校园信用卡推广活动更能体现你的组织和领导力,但你自己没意识到。
  3) 你比较回避"失败/挫折"类问题,被问到时会下意识转移话题或轻描淡写。

回答要求:口语化、真实、每次 2-4 句话,符合一个紧张又想表现好的应届生状态。直接说话,不要加任何旁白或标注。"""

# 第二次面试:候选人已针对上次被点出的"数据薄弱"刻意改进,这次主动带数字,
# 但保留一个残留习惯(仍略微回避失败/挫折),从而产生真实的"成长 delta"。
CANDIDATE_SYSTEM_2 = """你在参加第二次银行管培生面试,扮演候选人本人(林知遥),用第一人称回答。

背景与上次相同(经济学应届、城商行实习、学生会财务部、校园信用卡推广活动),
但这一次,你认真复盘过上一场面试被指出的问题,有意识地改进:
- 这次你**主动给出具体数字和量化口径**:比如"覆盖约2400人、成功开卡317张、开卡率约13%""用极速卡片后弃单率从约40%降到22%""我们分两天同时段对照统计前50份"。
- 你能把经济学知识接到业务上(如用"损失厌恶""信息不对称"解释客户为何犹豫)。
- 但你仍**略微回避谈彻底的失败经历**,被直接追问失败时还是会先讲教训、淡化挫败感(这是你尚未完全改掉的习惯)。

回答要求:口语化、真实、每次 2-4 句话,体现一个"明显比上次更有准备、更会用数据说话"的应届生。直接说话,不要加旁白或标注。"""

_variant = sys.argv[1] if len(sys.argv) > 1 else "1"
_sys_prompt = CANDIDATE_SYSTEM_2 if _variant == "2" else CANDIDATE_SYSTEM
candidate_messages = [{"role": "system", "content": _sys_prompt}]
log_lines = []
observer_cum = {"experiences": [], "competency_signals": [], "weak_points": [], "contradictions": []}


def L(s=""):
    print(s)
    log_lines.append(s)


def post_stream(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    out = {"monologue": "", "reply": "", "observer": None, "session_id": None}
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line:
                continue
            o = json.loads(line)
            t = o.get("type")
            if t == "session":
                out["session_id"] = o["session_id"]
            elif t == "monologue":
                out["monologue"] += o["text"]
            elif t == "reply":
                out["reply"] += o["text"]
            elif t == "observer":
                out["observer"] = o["record"]
    return out


def post_json(path, body, timeout=300):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def save_transcript():
    out_dir = Path(__file__).resolve().parent.parent / "transcripts"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"interview_{stamp}.md"
    path.write_text("\n".join(log_lines), encoding="utf-8")
    return path


def candidate_answer(question):
    candidate_messages.append({"role": "user", "content": f"面试官说:{question}\n\n请你作为候选人回答。"})
    ans = qwen_client.chat(candidate_messages, temperature=0.8)
    candidate_messages.append({"role": "assistant", "content": ans})
    return ans.strip()


def merge_obs(rec):
    if not rec:
        return
    for k in observer_cum:
        observer_cum[k].extend(rec.get(k, []))


def log_obs(rec):
    if not rec:
        return
    if rec.get("experiences"):
        for e in rec["experiences"]:
            L(f"    · [经历] {e.get('title','')}: {e.get('detail','')}")
    if rec.get("competency_signals"):
        for s in rec["competency_signals"]:
            L(f"    · [能力] {s.get('competency','')}（{s.get('level','')}）: {s.get('signal','')}")
    if rec.get("weak_points"):
        for w in rec["weak_points"]:
            L(f"    · [薄弱] {w}")
    if rec.get("contradictions"):
        for c in rec["contradictions"]:
            L(f"    · [矛盾] {c}")


def main():
    L(f"# 面试完整记录 — 银行管培生")
    L(f"候选人:林知遥(应届经济学本科生)  ·  生成时间:{datetime.now():%Y-%m-%d %H:%M}")
    L()

    # 1. 开场(友善模式)
    L("## 阶段一:面试(友善模式)")
    L()
    r = post_stream("/api/session/start", {"job": "银行管培生", "style": "friendly", "persona": "亲和但敏锐的 HR 经理"})
    sid = r["session_id"]
    L(f"**面试官**:{r['reply']}")
    L(f"  > 内心独白:{r['monologue'].strip()}")
    L()

    rounds = [
        ("friendly", 2),
        ("pressure", 2),
    ]
    last_q = r["reply"]
    for phase, n in rounds:
        if phase == "pressure":
            post_json("/api/interview/switch_persona", {"session_id": sid, "style": "pressure"})
            L("## 阶段二:切换为高压模式")
            L()
        for _ in range(n):
            ans = candidate_answer(last_q)
            L(f"**候选人**:{ans}")
            r = post_stream("/api/interview/message", {"session_id": sid, "message": ans})
            L(f"**面试官**:{r['reply']}")
            L(f"  > 内心独白:{r['monologue'].strip()}")
            L("  > 观察者记录:")
            log_obs(r["observer"])
            merge_obs(r["observer"])
            L()
            last_q = r["reply"]

    # 即时反馈
    L("## 阶段三:即时反馈")
    L()
    fb = post_json("/api/interview/end", {"session_id": sid})
    L(fb.get("feedback", fb.get("error", "")))
    L()

    # 复盘
    L("## 阶段四:复盘对话(教练)")
    L()
    r = post_stream("/api/review/message", {"session_id": sid, "message": ""})
    L(f"**教练**:{r['reply']}")
    L()
    coach_q = r["reply"]
    # 候选人切换为反思心态
    reflect_msgs = [{"role": "system", "content": _sys_prompt + "\n\n现在面试已结束,你在和复盘教练对话,请以更真诚、愿意反思的状态回答,每次 2-3 句。"}]
    for _ in range(3):
        reflect_msgs.append({"role": "user", "content": f"教练问:{coach_q}\n\n请回答。"})
        ans = qwen_client.chat(reflect_msgs, temperature=0.8).strip()
        reflect_msgs.append({"role": "assistant", "content": ans})
        L(f"**候选人**:{ans}")
        r = post_stream("/api/review/message", {"session_id": sid, "message": ans})
        L(f"**教练**:{r['reply']}")
        L()
        coach_q = r["reply"]

    # 先保存对话与复盘记录(避免 wiki 整理耗时导致丢失)
    L("## 阶段五:写入个人 Wiki")
    L()
    pre_path = save_transcript()
    print(f"=== 对话/复盘记录已保存: {pre_path} ===")
    print(f"=== session_id: {sid} ===")

    # 写入 wiki(整理较慢,放宽超时)
    c = post_json("/api/wiki/commit", {"session_id": sid}, timeout=300)
    L(f"写入摘要:{c.get('summary', c.get('error',''))}")
    L()
    final_path = save_transcript()
    print(f"\n=== transcript saved: {final_path} ===")


if __name__ == "__main__":
    main()
