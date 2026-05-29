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
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

# Wiki 的五个分区
WIKI_SECTIONS = ["experiences", "competencies", "blind_spots", "growth_log"]
NARRATIVE_FILE = "narrative.md"
