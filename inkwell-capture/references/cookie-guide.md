# Cookie 获取指南

当采集遇到 **403 Forbidden** 或 **需要登录** 时，说明该站点需要认证才能访问。下面按站点列出需要哪些 Cookie 以及如何获取。

## 通用获取方式（推荐：Network 面板一键复制）

**最简单的方法 —— 从 Network 面板直接复制全部 Cookie：**

1. **浏览器打开目标网站并登录**
2. **打开要采集的具体页面**
3. **按 F12（⌘+Option+I）打开开发者工具** → 切换到 **Network** 标签
4. **刷新页面** → 点击列表中**第一个请求**（发给当前域名的）
5. 右侧切换到 **Headers** 标签 → 向下滚动找到 **Request Headers**
6. 找到 `Cookie:` 这一行 → **复制冒号后面的全部内容**（不要复制 `Cookie: ` 这几个字）
7. **不管有多少个键值对，全部复制就行**，不需要筛选或删减，脚本会原样发送。

**备选方法 —— 从 Application 面板复制指定字段：**

1. **浏览器打开目标网站并登录**
2. **F12 → Application → Cookies** → 选择目标域名
3. **按站点表格复制需要的字段**
4. **手动拼接**：`字段1=值1; 字段2=值2`

> 💡 **推荐用 Network 方法**：一键复制全部，不容易错，也不需要记哪些字段必需。

## 各站点 Cookie 要求

### NGA (bbs.nga.cn)

NGA 帖子和回复都需要登录才能查看。

**必需的 Cookie 字段**（二选一）：

| 认证系统 | 字段 | 说明 |
|----------|------|------|
| **新版通行证**（推荐） | `ngaPassportUid` | 用户数字 ID |
| | `ngaPassportCid` | 会话凭证（长字符串） |
| **旧版认证** | `CURL_uin` | 用户标识 |

**获取步骤**：
1. 浏览器打开 https://bbs.nga.cn 并登录
2. F12 → Application → Cookies → `bbs.nga.cn`
3. 找到 `ngaPassportUid` 和 `ngaPassportCid`（新版通行证），或 `CURL_uin`（旧版）
4. 拼接：`ngaPassportUid=12345678; ngaPassportCid=abcdef...`

**验证是否有效**：
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Cookie: ngaPassportUid=xxx; ngaPassportCid=yyy" \
  "https://bbs.nga.cn/read.php?tid=47189694"
```
返回 200 则有效。

### V2EX (www.v2ex.com)

V2EX 大部分帖子无需登录即可访问。如遇到需要登录的情况：

| 字段 | 说明 |
|------|------|
| `A2` | 登录 token |

### 贴吧 (tieba.baidu.com)

| 字段 | 说明 |
|------|------|
| `BDUSS` | 百度统一登录凭证 |

### 知乎 (zhihu.com)

知乎回答完整内容需要登录才能查看。未登录时只能看到回答摘要，无法获取全文。

**必需字段（如手动复制时）：**
| 字段 | 说明 |
|------|------|
| `z_c0` | 知乎核心认证令牌 |
| `_xsrf` | CSRF 令牌 |
| `q_c1` | 环境识别 |

**获取步骤**：
1. 浏览器打开 https://www.zhihu.com 并登录
2. F12 → Application → Cookies → `zhihu.com`（或 `www.zhihu.com`）
3. 找到 `z_c0`、`_xsrf`、`q_c1` 三个字段
4. 拼接：`z_c0=xxx; _xsrf=yyy; q_c1=zzz`

> 推荐直接用 Network 方法复制全部，不用手动挑字段。

**验证是否有效**：
```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Cookie: z_c0=xxx; _xsrf=yyy; q_c1=zzz" \
  "https://www.zhihu.com/api/v4/me"
```
返回 200 则有效。

### 通用 / 其他站点

如果遇到未知站点的 403：
1. 确认该站点是否需要登录才能访问内容
2. 登录后从 F12 → Application → Cookies 复制全部 Cookie
3. 先全量传试试，能工作后再精简到必要字段
4. 精简后在本文件中补充该站点的记录

## Cookie 持久化

用户提供 Cookie 后，采集脚本会**自动保存**到 `.env` 文件中（无需手动操作）：

```bash
# .env（自动写入，无需手动编辑）
NGA_COOKIE="ngaPassportUid=xxx; ngaPassportCid=yyy"
TIEBA_COOKIE="BDUSS=xxx"
```

**自动流程**：
1. 用户提供 Cookie → 采集成功 → 自动写入 `.env`
2. 下次采集同域名 → 脚本自动从 `.env` 读取，无需重复提供
3. Cookie 过期（返回 403）→ 提示用户重新获取 → 用户提供新的 → 覆盖 `.env` 旧值

命名规范由 `scripts/cookie_store.py` 中的 `DOMAIN_COOKIE_MAP` 管理，新增站点时在映射表中注册。
