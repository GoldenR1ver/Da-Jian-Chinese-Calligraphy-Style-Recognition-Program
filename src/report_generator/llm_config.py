"""LLM API 配置：可在本文件硬编码（请勿将含真实密钥的文件提交到公开仓库）。"""

from __future__ import annotations

import os
from typing import Optional

# 若设置非空字符串，且命令行未传入对应参数，则优先于环境变量使用
HARDCODED_OPENAI_API_KEY: str = ""

HARDCODED_OPENAI_BASE_URL: str = ""

HARDCODED_OPENAI_MODEL: str = ""


def resolve_openai_api_key(cli: Optional[str] = None) -> Optional[str]:
    if cli and str(cli).strip():
        return str(cli).strip()
    if HARDCODED_OPENAI_API_KEY.strip():
        return HARDCODED_OPENAI_API_KEY.strip()
    v = os.environ.get("OPENAI_API_KEY")
    return v.strip() if v and v.strip() else None


def resolve_openai_base_url(cli: Optional[str] = None) -> str:
    if cli and str(cli).strip():
        return str(cli).strip()
    if HARDCODED_OPENAI_BASE_URL.strip():
        return HARDCODED_OPENAI_BASE_URL.strip()
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()


def resolve_openai_model(cli: Optional[str] = None) -> str:
    if cli and str(cli).strip():
        return str(cli).strip()
    if HARDCODED_OPENAI_MODEL.strip():
        return HARDCODED_OPENAI_MODEL.strip()
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
