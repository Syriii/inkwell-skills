# 错误处理规范

## 网页抓取降级链

```
web_fetch.py (requests + trafilatura)
  错误: 状态码错误 / 超时 / 内容为空 / SSL 错误
    ↓ 自动降级
web_fetch_full.py (Playwright 渲染)
  错误: Playwright 未安装 / 导航失败 / 渲染后仍无内容
    ↓ 告知用户备选方案
手动方案:
  - 复制全文粘贴
  - 截全页滚动图 → OCR
  - 尝试 archive.org / Google Cache
```

## OCR 降级链

```
ocr_text.py (PaddleOCR)
  错误: PaddleOCR 未安装 / 未检测到文字 / 质量= poor
    ↓ 建议降级
Surya (更强但需 PyTorch)
  错误: Surya 未安装 / 识别失败
    ↓ 最后兜底
Claude Code 视觉分析（在对话中看图提取文字）
  限制: 需要多模态模型支持
```

## 论坛抓取

```
forum_scraper.py
  错误: 请求失败 / 页面结构不匹配
    ↓ 降级
通用选择器兜底 (scrape_generic)
  错误: 仍无法提取
    ↓ 告知用户
手动方案: 复制内容粘贴
```

## 归档写入

```
archiver.py
  错误: JSON 格式错误 / 磁盘空间不足 / 目录权限
    ↓ 不静默失败，明确报告错误
  部分成功: article.md 已写但图片下载失败
    ↓ 标记 images 字段中的 download_error，继续
```

## 通用错误码约定

| 错误 | 含义 | 处理 |
|------|------|------|
| `request_failed` | HTTP 请求失败 | 降级到 L2 或手动 |
| `trafilatura_extraction_failed` | 无法提取正文 | 降级到 L2 |
| `playwright_not_installed` | Playwright 缺失 | 告知安装方式 |
| `playwright_navigation_failed` | 页面加载失败 | 降级到手动 |
| `paddleocr_not_installed` | PaddleOCR 缺失 | 告知安装方式 |
| `ocr_no_text` | 未检测到文字 | 可能是图片类截图 |
| `file_not_found` | 截图文件不存在 | 检查路径 |

## 日志与报告

- 每个脚本在 JSON 输出中明确标记 `error` 字段
- 正常输出不包含 `error` 字段
- 脚本退出码: 0 = 成功, 1 = 有 error
- Claude Code 在 SKILL.md 工作流中根据 error/message 决定下一步动作
