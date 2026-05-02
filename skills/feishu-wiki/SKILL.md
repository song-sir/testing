---
name: feishu-wiki
description: 飞书知识库查询和搜索 — 浏览知识空间、节点，按关键词搜索文档并返回正文内容
triggers:
  - 从飞书查询
  - 从飞书搜索
  - 从知识库查询
  - 从知识库搜索
  - 查知识库
  - 搜索飞书文档
  - 搜索飞书wiki
  - 飞书wiki查
  - 飞书wiki搜
  - 飞书wiki找
  - feishu wiki
  - 查飞书
  - 搜飞书
---

# 飞书知识库查询 Skill

通过飞书 API 在知识库中搜索和浏览文档。

## 定位脚本

后端脚本 `feishu_wiki.py` 与本文件位于**同一目录**。根据安装方式不同，路径可能是：

- **项目级**：`<project>/.claude/skills/feishu-wiki/`
- **全局级**：`~/.claude/skills/feishu-wiki/`
- **其他位置**：由 Agent 或用户自行指定

执行前，先确定本 SKILL.md 所在目录的绝对路径，记为 `SKILL_DIR`。后续所有命令统一使用：

```bash
"$SKILL_DIR/venv/bin/python" "$SKILL_DIR/feishu_wiki.py" <子命令> [参数]
```

> **首次使用**：如果 `venv` 不存在，需先创建并安装依赖：
> ```bash
> cd "$SKILL_DIR" && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
> ```

## 可用子命令

| 子命令 | 参数 | 认证 | 说明 |
|--------|------|------|------|
| `init` | 交互式 | — | 配置 APP_ID/APP_SECRET 存入 keyring |
| `login` | 无 | OAuth | 浏览器授权获取 user_access_token |
| `refresh` | 无 | — | 检查/刷新 token |
| `list-spaces` | 无 | tenant | 列出所有知识空间 |
| `list-nodes` | `--space-id <id>` | tenant | 列出空间下一级节点 |
| `list-child-nodes` | `--space-id <id> --parent-node-token <token>` | tenant | 列出子节点 |
| `search` | `--query "关键词" [--space-id <id>] [--node-id <id>]` | user | 搜索 wiki（node-id 需配合 space-id） |
| `get-document` | `--document-id <id>` | tenant | 获取文档正文（仅 docx 类型） |

所有命令输出 JSON 到 stdout，错误输出到 stderr。

## 执行流程

### 步骤 1：检查认证状态

执行 `refresh` 命令检查 token 是否有效：

```bash
"$SKILL_DIR/venv/bin/python" "$SKILL_DIR/feishu_wiki.py" refresh
```

如果返回错误：
- `credentials_missing` → 提示用户在终端中手动执行 init 命令配置飞书应用凭证（需要交互式输入 APP_ID 和 APP_SECRET）
- `token_expired` → 提示用户在终端中手动执行 login 命令重新授权（需要浏览器完成 OAuth 登录）

等待用户完成后重新检查。

### 步骤 2：获取知识空间列表

执行 `list-spaces` 获取列表：

```bash
"$SKILL_DIR/venv/bin/python" "$SKILL_DIR/feishu_wiki.py" list-spaces
```

将结果按字母编号展示给用户：

```
找到以下知识空间：
A: [第一个知识库名称]
B: [第二个知识库名称]
C: [第三个知识库名称]
...
ALL: 全部知识库

请选择操作：
1) 搜索知识库 — 输入字母+关键词，如 "A 部署流程" 或 "all 部署流程"
2) 浏览节点 — 输入 "列出 A 的节点" 或 "列出 BC 的节点"
```

**重要：** 在内部记住每个字母对应的 space_id 和名称，后续操作会用到。

### 步骤 3：解析用户输入

用户可能用以下方式表达意图，你需要灵活理解：

**搜索模式：**
- `A 部署流程` → 在 A 对应的知识库搜索 "部署流程"
- `BC 监控配置` → 在 B 和 C 对应的知识库分别搜索 "监控配置"
- `产品知识库和测试知识库 搜索 xxx` → 按名称匹配知识库搜索
- `all 部署流程` → 在所有知识库搜索（不传 --space-id）

**浏览模式：**
- `列出 A 下面有哪些节点` → list-nodes for space A
- `列出 CD 下节点` → 分别列出 C 和 D 的节点
- `列出运维知识库和测试知识库下节点` → 按名称匹配

**子节点浏览：**
- `列出运维知识库节点 xxx 下的子节点` → list-child-nodes（需要从之前结果中找到该节点的 node_token）

**在节点下搜索：**
- `运维知识库下自监控节点查询如何监控 mysql` → search --space-id X --node-id Y --query "如何监控 mysql"

### 步骤 4：执行搜索并拉取正文

搜索后，对每个结果（最多 10 条）：

1. 直接尝试用 `get-document` 拉取正文（搜索 API 返回的 obj_type 整数编码与 list-nodes 不同，无法可靠判断类型）：
   ```bash
   "$SKILL_DIR/venv/bin/python" "$SKILL_DIR/feishu_wiki.py" get-document --document-id <obj_token>
   ```
2. 如果 `get-document` 返回错误，说明该文档不支持正文读取（如旧版 doc/sheet/bitable），只输出标题和链接
3. 从成功拉取的正文中找到与搜索关键词相关的段落（前后各约 200 字）

### 步骤 5：格式化输出

**搜索结果格式：**

```markdown
### [文档标题]
- 来源：[知识库名称] > [节点路径（如有）]
- 链接：[飞书文档 URL]

[文档相关内容片段...]

---
```

**浏览节点格式：**

```markdown
[知识库名称] 下的节点：

| 序号 | 标题 | 类型 | 有子节点 |
|------|------|------|---------|
| 1 | xxx | docx | 是 |
| 2 | yyy | sheet | 否 |

可以继续操作：
- 查看子节点："列出 [节点名] 的子节点"
- 在节点下搜索："[节点名] 搜索 [关键词]"
```

**无结果时：**

```
在 [知识库名称] 中未找到与「关键词」相关的内容。
```

**绝对不要杜撰知识库中不存在的内容。** 如果搜索无结果，直接告知用户。

## 注意事项

- `init` 和 `login` 命令需要用户交互（键盘输入/浏览器），不要在自动化环境中直接执行，必须提示用户在终端中手动运行
- 搜索 API 需要 user_access_token，refresh 命令会自动刷新
- `get-document` 仅支持新版文档类型，旧版 doc/sheet/bitable 会返回错误，此时只展示标题和链接
- `--node-id` 搜索时必须同时传 `--space-id`
- 所有输出基于 API 返回的真实数据，不添加、不推测、不杜撰
- 凭证通过 keyring 存储（macOS Keychain / Windows Credential Manager），与安装目录无关，全局可用
