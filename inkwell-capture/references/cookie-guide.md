# Cookie 获取指南

当采集遇到 **403 Forbidden** 或 **需要登录** 时，说明该站点需要认证才能访问。下面按站点列出需要哪些 Cookie 以及如何获取。

## 通用获取方式

所有站点的 Cookie 获取流程一致：

1. **浏览器打开目标网站并登录**
2. **F12 → Application → Cookies** → 选择目标域名
3. **复制需要的字段**（见下方各站点表格）
4. **拼接为 Cookie 字符串**：`字段1=值1; 字段2=值2`
5. **传给采集脚本**：`--cookie "字段1=值1; 字段2=值2"`

也可以在 Network 面板中直接复制：
- F12 → Network → 刷新页面 → 点击任意请求 → Request Headers → 找到 `Cookie:` 行 → 整行复制

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
