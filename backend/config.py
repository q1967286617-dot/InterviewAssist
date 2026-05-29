import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 项目根目录(backend 的上一级)
ROOT_DIR = Path(__file__).resolve().parent.parent
WIKI_DIR = ROOT_DIR / "wiki"
FRONTEND_DIR = ROOT_DIR / "frontend"

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
# 对话类(面试官/观察者/复盘教练)用的模型
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
# Wiki agent(ingest/query/lint,需要工具调用与较强推理)用的模型
AGENT_MODEL = os.getenv("AGENT_MODEL", "qwen3.6-plus")

# ---- 颗粒化 Wiki 结构 ----
# 实体分区(每个分区下是若干颗粒页,而非单一 main.md)
WIKI_CATEGORIES = ["experiences", "competencies", "blind_spots"]
# 不可变原始源 / 问答回填 的存放目录
SOURCES_DIR = "sources"
ANSWERS_DIR = "answers"
# 顶层固定文件
NARRATIVE_FILE = "narrative.md"
INDEX_FILE = "index.md"
LOG_FILE = "log.md"
SCHEMA_FILE = "WIKI_SCHEMA.md"
