#!/usr/bin/env python3
"""Cookie 持久化存储。

从 .env 文件中按域名读取已保存的 Cookie，供采集脚本自动使用。

域名 → 环境变量映射（新增站点在此注册）：
  bbs.nga.cn      → NGA_COOKIE
  tieba.baidu.com → TIEBA_COOKIE
  v2ex.com        → V2EX_COOKIE
  xiaohongshu.com → XHS_COOKIE
"""

import os
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 域名 → 环境变量名 映射表（新增站点在此注册）
# ---------------------------------------------------------------------------

DOMAIN_COOKIE_MAP = {
    "bbs.nga.cn": "NGA_COOKIE",
    "nga.cn": "NGA_COOKIE",
    "tieba.baidu.com": "TIEBA_COOKIE",
    "www.v2ex.com": "V2EX_COOKIE",
    "v2ex.com": "V2EX_COOKIE",
    "xiaohongshu.com": "XHS_COOKIE",
    "xhslink.com": "XHS_COOKIE",
    "zhihu.com": "ZHIHU_COOKIE",
    "www.zhihu.com": "ZHIHU_COOKIE",
}


# ---------------------------------------------------------------------------
# 读取逻辑
# ---------------------------------------------------------------------------

def _read_env_file() -> dict[str, str]:
    """从项目根目录的 .env 文件读取所有变量。"""
    env = {}
    for base in [Path.cwd(), Path.cwd().parent, Path(__file__).resolve().parent.parent.parent]:
        env_file = base / ".env"
        if env_file.exists():
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            env[key] = value
            except Exception:
                pass
    return env


def get_cookie_for_url(url: str) -> str | None:
    """根据 URL 获取已保存的 Cookie。

    优先级：os.environ > .env 文件

    Returns:
        Cookie 字符串，或 None（未配置）
    """
    domain = urlparse(url).netloc.lower().replace("www.", "")

    # 查找映射
    env_var = None
    for pattern, var in DOMAIN_COOKIE_MAP.items():
        if domain == pattern or domain.endswith("." + pattern):
            env_var = var
            break

    if not env_var:
        return None

    # 优先 os.environ
    cookie = os.environ.get(env_var)
    if cookie:
        return cookie

    # 回退到 .env 文件
    file_env = _read_env_file()
    return file_env.get(env_var)


def get_env_var_for_url(url: str) -> str | None:
    """返回该域名对应的环境变量名（如 NGA_COOKIE），用于写入 .env。"""
    domain = urlparse(url).netloc.lower().replace("www.", "")
    for pattern, var in DOMAIN_COOKIE_MAP.items():
        if domain == pattern or domain.endswith("." + pattern):
            return var
    # 未注册域名：自动生成变量名
    parts = domain.split(".")
    return parts[0].upper() + "_COOKIE" if len(parts) >= 2 else domain.upper() + "_COOKIE"
