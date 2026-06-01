# 核心文件作用说明

本文记录当前 MVP 中需要重点阅读和维护的核心文件。源码内也已经补充了简短职责注释。

## 前端

| 文件 | 作用 |
| --- | --- |
| `frontend/src/main.jsx` | React 挂载入口，把 `App` 渲染到 `index.html` 的 `#root`。 |
| `frontend/src/App.jsx` | 应用根组件，当前只渲染聊天页。 |
| `frontend/src/ChatPage.jsx` | 聊天页面状态中心，维护 `messages`、`isLoading`、`error`，并处理发送后的 UI 状态更新。 |
| `frontend/src/components/ChatInput.jsx` | 输入框和发送按钮，负责校验空消息、触发表单提交、清空输入框。 |
| `frontend/src/components/MessageList.jsx` | 消息列表，负责空状态、历史消息列表和 loading 占位消息。 |
| `frontend/src/components/MessageItem.jsx` | 单条消息展示，根据 `role` 显示“我”或“AI”。 |
| `frontend/src/api/chatApi.js` | 前端 API 封装，负责调用后端 `POST /api/chat` 并处理错误响应。 |
| `frontend/src/App.css` | 聊天页面布局、消息气泡、输入区等页面级样式。 |
| `frontend/src/index.css` | 全局 CSS 变量、基础字体、浅色/深色主题变量。 |

## 后端

| 文件 | 作用 |
| --- | --- |
| `backend/app/main.py` | FastAPI 应用入口，初始化数据库、配置 CORS、挂载 `/api/chat` 路由和健康检查。 |
| `backend/app/api/chat.py` | HTTP 路由层，接收 `POST /api/chat`，注入数据库 Session，把业务交给 `chat_service`，并转换错误码。 |
| `backend/app/services/chat_service.py` | 聊天业务编排层，负责创建或读取会话、保存用户消息、调用 `llm_service`、保存 AI 回复、提交事务。 |
| `backend/app/services/llm_service.py` | 大模型访问层，校验环境变量，构造 OpenAI-compatible 请求，解析模型响应，统一抛出模型调用错误。 |
| `backend/app/core/config.py` | 配置读取层，从 `backend/.env` 加载大模型 API Key、Base URL、模型名称和超时时间。 |
| `backend/app/core/prompt.py` | Prompt 构造层，把系统提示词和用户消息包装成 `messages` 数组。 |
| `backend/app/db/database.py` | SQLite 和 SQLAlchemy ORM 层，定义数据库连接、`Conversation`、`Message`、`get_db()`、`init_db()`。 |
| `backend/app/schemas/chat_schema.py` | Pydantic schema，定义聊天请求体 `ChatRequest` 和响应体 `ChatResponse`。 |

## 非核心运行产物

这些文件或目录来自本地安装、运行、构建或数据库生成，不作为业务源码维护：

- `frontend/node_modules/`
- `frontend/dist/`
- `backend/app.db`
- `backend/**/*.log`
- `backend/app/**/__pycache__/`
- `backend/app/**/*.pyc`

## 分层边界

- React 只负责页面交互和调用 HTTP API，不直接了解数据库或大模型 API。
- `api/chat.py` 只负责 HTTP 层，不直接写业务流程。
- `chat_service.py` 是当前聊天链路的业务中心，所有 SQLite 写入都在这里编排。
- `llm_service.py` 只负责外部大模型调用，不直接读写 SQLite。
- `database.py` 只定义数据库模型和连接，不主动参与业务判断。
