"""Inkwell Capture — 论坛专用处理器。

每个论坛域名对应一个模块，包含该论坛的抓取逻辑。
forum_scraper.py 通过 FORUM_HANDLERS 字典路由到对应处理器。
"""

from forum.nga import scrape_nga
from forum.v2ex import scrape_v2ex
from forum.tieba import scrape_tieba

# 域名 → 处理器函数 映射表
# 注意：detect_forum() 会先 strip "www." 前缀，
# 所以只需注册裸域名即可，www 子域名会自动匹配。
FORUM_HANDLERS = {
    "bbs.nga.cn": scrape_nga,
    "nga.cn": scrape_nga,
    "nga.178.com": scrape_nga,
    "v2ex.com": scrape_v2ex,
    "tieba.baidu.com": scrape_tieba,
}

__all__ = [
    "FORUM_HANDLERS",
    "scrape_nga",
    "scrape_v2ex",
    "scrape_tieba",
]
