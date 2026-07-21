# 支持的内容类型

## 网页文章

- **识别**: URL + 非论坛域名
- **L1**: `web_fetch.py` — requests + trafilatura
- **L2**: `web_fetch_full.py` — Playwright 渲染
- **输出**: type=webpage, Markdown 正文全量保留

## 论坛帖子

- **识别**: URL 域名匹配 forum_domains 列表
- **处理**: `forum_scraper.py` — 提取 OP + 评论树
- **输出**: type=forum, 一体式 Markdown（正文 + 全部评论）
- **阈值**: 评论数 > 500 询问用户截断还是全保留
- **已知论坛**: V2EX、贴吧（持续扩展）

## 截图（文字类）

- **识别**: .png/.jpg 文件 + 用户确认"文字类"
- **L1**: `ocr_text.py` — PaddleOCR + KenLM 质量评估
- **L2**: Surya（PaddleOCR 质量差时建议）
- **L3**: Claude Code 视觉分析（Surya 失败时）
- **输出**: type=screenshot_ocr, 提取的文本 + 质量评分
- **原始图**: 保存到 images/ 并在 frontmatter 记录路径

## 截图（图片类）

- **识别**: .png/.jpg 文件 + 用户确认"图片类"
- **处理**: Claude Code 对话中直接视觉分析（不经过脚本）
- **输出**: type=screenshot_multimodal, Claude 分析结果 + 原图归档

## PDF / 报告

- **处理**: 文本提取 + OCR 混合，按需
- **输出**: type=pdf, 提取文本 + 原始文件保存

## 聊天记录导出

- **处理**: 用户提供文件，直接归档
- **输出**: type=chat_export, 原始格式保留

## 社交媒体单条

- **处理**: 按平台适配（优先中文平台：知乎、微博、公众号）
- **输出**: type=social_media

## 手动粘贴文本

- **识别**: 用户直接粘贴文本内容
- **source**: `manual-{timestamp}` 格式
- **处理**: 跳过抓取步骤，直接进入理解字段生成 + 归档
