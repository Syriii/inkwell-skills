# 已沉淀站点规则

仅在 URL 匹配本文件列出的域名时读取对应章节。

## 知乎（zhihu.com）

### URL 与采集范围

| URL 模式 | 含义 | 采集范围 |
|---------|------|---------|
| `/question/{id}/answer/{aid}` 或 `/answer/{id}` | 单个回答 | 仅该回答正文 + 评论区，目录名为模型总结的回答标题 |
| `/question/{id}` | 整个问题 | 询问用户：全部回答 / 前 N 个高赞？是否含评论？ |

`/answer/{id}` 会自动重定向到 `/question/{qid}/answer/{aid}`，问题上下文始终可用。

### 反爬与宿主能力

| 层级 | 方式 | 结果 |
|------|------|------|
| L1 | `web_fetch.py` | 通常 403 |
| L2 | `web_fetch_full.py` + Cookie | 可能返回 40362 |
| L3 | 已登录浏览器 | 通常可访问并滚动加载 |

知乎通常需要 L3。使用前读取[宿主兼容说明](host-compatibility.md)，完成导航、增量滚动和 DOM 提取。

### 目录结构

单回答：

```text
archived/YYYYMMDD/{回答标题-slug}/
├── {回答标题-slug}.md
├── comments.md
└── images/
```

- 回答标题 slug 必须为中文，由内容总结生成；作者写入 frontmatter，不进入目录名。

全问题：

```text
archived/YYYYMMDD/{问题名称-slug}/
├── {问题名称-slug}.md
├── 回答/
│   ├── {回答1标题-slug}.md
│   └── ...
└── images/
```

- 只有问题总览写完整 frontmatter；回答文件放在 `回答/` 子目录且不写 frontmatter。
- 总览通过 wikilink `[[{回答slug}]]` 导航；图片统一放在 `images/`。
- 评论超过 `comment_limit` 时先询问用户。

### 全问题执行

1. 用已登录浏览器打开问题页并用真实滚轮事件增量加载。
2. 在页面上下文提取回答和元数据，写入目标归档目录内的临时 JSON，完成后删除：
   - 回答：`.List-item`、赞同数、作者、正文与 `data-original` 图片；
   - 元数据：回答总数、回答链接、日期和 `.QuestionRichText` 描述。
3. 为回答生成中文 slug。
4. 执行：

   ```bash
   python <skill-dir>/scripts/zhihu_writer.py \
     --qid {id} --title {标题} --answers {answers.json} --meta {meta.json} \
     --category {分类} --tags {标签} --desc {描述} --slugs {slugs.json}
   ```

用户只要问题总览时，不调用 `zhihu_writer.py`。

## NGA（bbs.nga.cn）

- URL：`/read.php?tid={数字}`。
- 使用 `forum_scraper.py`，其会调用 `forum/nga.py` 并从 `.env` 加载 `NGA_COOKIE`。
- 页面显示帖子锁定或不存在时立即停止，不重试，并明确告知用户。
- 图片 CDN 可能对 Python requests 返回 567；`archiver.py` 会自动用 `curl` + Cookie + Referer 降级重试。

## 煎蛋（jandan.net）

| URL 模式 | 类型 | 特征 |
|----------|------|------|
| `/t/{id}` | 树洞 | OP + 动态评论，图片常是内容主体 |
| `/p/{id}` | 文章 | 长文 + 评论，服务端渲染 |

`/t/{id}` 使用专用入口，由脚本在一次运行中完成静态主帖与 L2 动态评论合并：

```bash
python <skill-dir>/scripts/jandan_capture.py --url "https://jandan.net/t/{id}"
```

需要直接归档时，由宿主模型生成语义字段后在同一命令提供 `--project-root`、`--title`、`--category`、`--tags` 和 `--summary`。脚本检测到相同 source 时会停止，由用户决定跳过或覆盖。

`/t/{id}` 渲染后可能自动跳到新帖子。专用入口会执行以下确定性检查：

- 正文与正文图片只从 SSR 原始 HTML 的 `.post-content` 获取；
- 评论只接受同时具有 `.floor` 和 `.comment-id` 的 `.comment-row`，排除热门区重复项；
- 评论图片只接受 `.comment-content img`，不扫描头像和界面资源；
- 核对最终 URL、页面 source ID，以及静态/渲染页面作者；不一致时拒绝合并；
- `comment_count` 只取实际评论数组长度，不从通用页面元素推测。

执行规则：

- 只要正文与图片时可加 `--no-render`；需要评论时使用默认 L1+L2 合并模式；只有专用入口失败或返回不完整时才用 L3。
- `completeness.complete=false` 时禁止归档，不得把“脚本退出成功”当作内容完整。
- 图片含文字时使用 OCR，并将结果附在图片下方。
- 标题禁止使用“煎蛋无聊图 + ID”前缀；用内容型中文标题，源站 ID 留在 `source`，正文注明来源编号。
