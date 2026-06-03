# AI 问答助手学习笔记 1

这份笔记用当前项目作为例子，解释一个最小 AI 问答应用是如何工作的。

## 1. React 组件怎么拆分

React 组件拆分的核心原则是：一个组件只负责一类事情。

当前前端可以这样理解：

- `App.jsx`：应用入口，只负责显示主页面。
- `ChatPage.jsx`：聊天页面的“大脑”，负责保存消息、loading、错误信息。
- `ChatInput.jsx`：输入框和发送按钮，负责收集用户输入。
- `MessageList.jsx`：消息列表，负责把多条消息循环显示出来。
- `MessageItem.jsx`：单条消息，负责显示“我”或“AI”的一条内容。
- `api/chatApi.js`：专门负责请求后端。

这样拆分的好处是：每个文件都比较短，出了问题更容易定位。

## 2. 前端如何用 fetch 请求后端

前端用 `fetch` 向后端发送 HTTP 请求。

当前项目的请求逻辑在 `frontend/src/api/chatApi.js`：

```js
fetch('http://127.0.0.1:8001/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ message, conversation_id }),
})
```

这段代码的意思是：

- 请求地址是 `/api/chat`。
- 请求方法是 `POST`。
- 请求内容是 JSON。
- 第一次发送的数据可以只有 `{ message: '用户输入的内容' }`。
- 后续追问时，还会带上 `{ conversation_id: 当前会话 ID }`。

后端返回数据后，前端再把 `answer` 显示到页面上。

## 3. FastAPI 如何定义接口

FastAPI 用装饰器定义接口。

例如：

```py
@app.get("/api/health")
def health_check():
    return {"status": "ok"}
```

意思是：

- 当前端或浏览器访问 `GET /api/health`；
- FastAPI 就会执行 `health_check()`；
- 函数返回的字典会自动变成 JSON。

聊天接口在 `backend/app/api/chat.py` 中：

```py
@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    ...
```

因为这个 router 在 `main.py` 里加了 `/api` 前缀，在 `chat.py` 里加了 `/chat` 前缀，所以完整地址是：

```text
POST /api/chat
```

## 4. Pydantic 如何校验请求体

Pydantic 用类来描述请求体格式。

当前项目中：

```py
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: int | None = None
```

意思是：

- `message` 必须传；
- `message` 必须是字符串；
- `message` 至少有 1 个字符；
- `conversation_id` 可以不传；
- 如果传了 `conversation_id`，它应该是整数。

如果前端传错了，比如没有传 `message`，FastAPI 会自动返回校验错误，不需要我们手动判断所有情况。

## 5. 后端如何组织 service 层

service 层用来放“业务逻辑”或“外部服务调用”。

当前项目中：

```text
backend/app/services/chat_service.py
backend/app/services/llm_service.py
```

`chat_service.py` 负责一次聊天请求的业务编排，`llm_service.py` 专门负责调用大模型 API。

为什么不直接写在 `chat.py` 里？

因为 `chat.py` 主要负责 HTTP 接口流程：

1. 接收请求；
2. 注入数据库连接；
3. 调用 `chat_service`；
4. 把业务错误转换成 HTTP 状态码。

而 `chat_service.py` 负责：

1. 找到或创建会话；
2. 读取最近几条历史消息；
3. 调用 `llm_service` 获取 AI 回答；
4. 保存当前用户消息和 AI 回答；
5. 提交数据库事务。

而 `llm_service.py` 负责：

1. 检查大模型配置；
2. 拼接请求地址；
3. 发送 HTTP 请求；
4. 解析模型返回结果；
5. 把错误变成清晰提示。

这样分开后，代码更容易读，也更容易测试。

## 6. .env 为什么不能上传

`.env` 通常保存本地私密配置，比如：

```env
LLM_API_KEY=真实 API Key
LLM_BASE_URL=模型服务地址
LLM_MODEL=模型名称
```

其中 `LLM_API_KEY` 就像账号密码。

如果上传到 GitHub 或发给别人，别人可能使用你的 API Key，造成费用损失或账号风险。

所以 `.env` 应该加入 `.gitignore`。

当前项目的 `.gitignore` 中已经包含：

```gitignore
.env
```

## 7. API Key 如何安全管理

API Key 的基本管理方式：

1. 不要写死在代码里。
2. 放到 `.env` 文件中。
3. `.env` 不上传。
4. 代码只通过环境变量读取。
5. 如果怀疑泄露，去模型平台重新生成 Key。

当前项目通过 `backend/app/core/config.py` 读取配置：

```py
llm_api_key: str = os.getenv("LLM_API_KEY", "")
```

代码只知道“去环境变量里拿 Key”，但代码本身不保存真实 Key。

## 8. SQLite 如何保存聊天记录

SQLite 是一个轻量数据库，适合本地学习和小项目。

当前数据库文件位置：

```text
backend/app.db
```

当前项目有两张表：

```text
conversation
message
```

`conversation` 表保存一次会话：

- `id`：会话 ID。
- `title`：会话标题。
- `created_at`：创建时间。
- `updated_at`：更新时间。

`message` 表保存每条消息：

- `id`：消息 ID。
- `conversation_id`：属于哪个会话。
- `role`：消息角色，比如 `user` 或 `assistant`。
- `content`：消息内容。
- `created_at`：创建时间。

一次问答会保存两条 message：

1. 用户发的问题；
2. AI 返回的回答。

## 9. 一次用户提问的完整链路是什么

完整链路可以这样看：

```text
用户在前端输入问题
  ↓
点击发送按钮
  ↓
ChatInput 把消息交给 ChatPage
  ↓
ChatPage 调用 sendChatMessage
  ↓
fetch 请求后端 POST /api/chat
  ↓
FastAPI 接收请求
  ↓
Pydantic 校验请求体
  ↓
chat_service 创建或查找 conversation
  ↓
chat_service 读取最近几条历史消息
  ↓
llm_service 把历史消息和当前问题一起发给大模型 API
  ↓
大模型返回 answer
  ↓
chat_service 保存当前用户问题和 AI 回答并提交 SQLite
  ↓
后端返回 conversation_id 和 answer
  ↓
前端把 AI 回答显示到页面
```

这就是一个最小 AI 问答应用的主流程。

## 10. Codex 如何辅助开发而不是替代学习

Codex 可以帮你做这些事：

- 读代码，解释代码结构；
- 按你的要求修改代码；
- 找 bug；
- 生成示例；
- 写文档；
- 给出验证命令；
- 帮你拆解学习路线。

但学习不能只看结果。

更好的使用方式是：

1. 先让 Codex 修改一个小功能。
2. 再让 Codex 解释修改了哪些文件。
3. 自己手动运行命令验证。
4. 自己尝试改一个小地方。
5. 报错后再让 Codex 帮你分析。

你应该重点理解：

- 为什么要这样拆文件；
- 请求是怎么从前端走到后端的；
- 数据是怎么被校验和保存的；
- API Key 为什么不能写进代码；
- 错误发生时应该如何定位。

Codex 的价值不是让你跳过学习，而是让你更快看到一个能运行的例子，然后围绕这个例子一步步理解。

## 本节复习

你可以尝试回答：

1. `ChatPage.jsx` 和 `ChatInput.jsx` 分别负责什么？
2. `fetch` 请求里为什么要写 `Content-Type: application/json`？
3. `ChatRequest` 中的 `message` 为什么要设置 `min_length=1`？
4. 为什么大模型调用逻辑适合放在 `llm_service.py`？
5. 一次聊天为什么会向 `message` 表写入两条记录？
