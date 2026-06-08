# 核心文件作用说明

本文记录当前 MVP 中需要重点阅读和维护的核心文件。源码内也已经补充了简短职责注释。

## 前端

| 文件 | 作用 |
| --- | --- |
| `frontend/src/main.jsx` | React 挂载入口，把 `App` 渲染到 `index.html` 的 `#root`。 |
| `frontend/src/App.jsx` | 应用根组件，当前只渲染聊天页。 |
| `frontend/src/ChatPage.jsx` | 聊天页面状态中心，维护 `messages`、`isLoading`、`error` 和当前 `conversationId`，并处理流式发送、历史会话加载后的 UI 状态更新。 |
| `frontend/src/components/ChatInput.jsx` | 输入框和发送按钮，负责校验空消息、触发表单提交、清空输入框。 |
| `frontend/src/components/ConversationList.jsx` | 历史会话侧边栏，负责展示会话列表、新建会话按钮和列表加载错误。 |
| `frontend/src/components/ConversationItem.jsx` | 单个历史会话按钮，展示会话标题和更新时间，并标记当前选中会话。 |
| `frontend/src/components/DocumentToolbar.jsx` | 主聊天窗口内的文档工具条，负责批量上传文档、多选知识库范围、切换“基于文档回答”。 |
| `frontend/src/components/MessageList.jsx` | 消息列表，负责空状态、历史消息列表和流式输出时的 loading 占位。 |
| `frontend/src/components/MessageItem.jsx` | 单条消息展示，根据 `role` 显示“我”或“AI”，并在 RAG 回答中渲染 sources。 |
| `frontend/src/components/SourceList.jsx` | RAG sources 展示组件，负责显示 Chroma 返回的引用片段、文件名、文件类型、chunk 序号和相似度分数。 |
| `frontend/src/api/chatApi.js` | 前端聊天 API 封装，保留普通 `POST /api/chat` 调用，并新增 `POST /api/chat/stream` 的 fetch 流式读取逻辑。 |
| `frontend/src/api/conversationApi.js` | 前端历史会话 API 封装，负责查询会话列表和某个会话的消息。 |
| `frontend/src/api/ragApi.js` | 前端 RAG API 封装，负责单文件/批量上传、查询文档列表、普通 RAG 问答和 `POST /api/rag/chat/stream` 的 NDJSON 流式读取。 |
| `frontend/src/App.css` | 聊天页面布局、消息气泡、输入区等页面级样式。 |
| `frontend/src/index.css` | 全局 CSS 变量、基础字体、浅色/深色主题变量。 |

## 后端

| 文件 | 作用 |
| --- | --- |
| `backend/app/main.py` | FastAPI 应用入口，初始化数据库、配置 CORS、暴露 `X-Conversation-Id` 响应头、挂载 `/api/chat` 路由和健康检查。 |
| `backend/app/api/chat.py` | HTTP 路由层，接收普通 `POST /api/chat` 和流式 `POST /api/chat/stream`，把业务交给 `chat_service`，并转换错误码。 |
| `backend/app/api/conversation.py` | HTTP 路由层，提供历史会话列表和会话消息查询接口。 |
| `backend/app/api/rag.py` | HTTP 路由层，提供单文件上传、批量上传、文档列表、普通 RAG 问答和流式 RAG 问答接口。 |
| `backend/app/services/chat_service.py` | 聊天业务编排层，负责创建或读取会话、读取最近历史消息、调用 `llm_service`、保存本轮用户消息和 AI 回复；流式模式下负责逐步 yield chunk，并在流结束后保存一条完整 assistant 消息。 |
| `backend/app/services/chroma_service.py` | Chroma 向量库访问层，负责初始化 PersistentClient、获取 collection、写入 chunks、删除旧 chunks，以及按 `document_ids` 范围执行 top-k 检索并合并排序。 |
| `backend/app/services/conversation_service.py` | 历史会话查询业务层，负责按更新时间查询会话摘要、按会话查询消息、处理标题兜底。 |
| `backend/app/services/document_parser.py` | 上传文档解析层，统一提取 TXT、Markdown、PDF、DOCX 的纯文本，并给出用户可理解的解析错误。 |
| `backend/app/services/embedding_service.py` | Embedding 调用层，读取 embedding 配置，调用 OpenAI-compatible `/embeddings`，把文本转换成 `list[float]`。 |
| `backend/app/services/llm_service.py` | 大模型访问层，校验环境变量，构造 OpenAI-compatible 普通请求和 `stream=True` 请求，解析完整响应或流式 chunk，统一抛出模型调用错误。 |
| `backend/app/services/rag_service.py` | Chroma RAG 业务层，负责调用文档解析服务、chunk 切分、生成 embedding、单文件/批量写入 Chroma、解析 `document_ids`、检索 Chroma、构造 RAG Prompt、普通/流式模型调用和消息落库。 |
| `backend/app/core/config.py` | 配置读取层，从 `backend/.env` 加载大模型、embedding 和 Chroma 的配置。 |
| `backend/app/core/prompt.py` | Prompt 构造层，把系统提示词、最近历史消息和当前用户问题包装成 `messages` 数组；同时提供 RAG Prompt 模板。 |
| `backend/app/db/database.py` | SQLite 和 SQLAlchemy ORM 层，定义数据库连接、`Conversation`、`Message`、`Document`、旧版 `DocumentChunk`、`get_db()`、`init_db()`。新版 RAG 不再用 `DocumentChunk` 检索。 |
| `backend/app/schemas/chat_schema.py` | Pydantic schema，定义聊天请求体 `ChatRequest` 和响应体 `ChatResponse`。 |
| `backend/app/schemas/conversation_schema.py` | Pydantic schema，定义历史会话摘要和会话消息查询响应。 |
| `backend/app/schemas/rag_schema.py` | Pydantic schema，定义单文件/批量上传响应、文档摘要、兼容 `document_id` / `document_ids` 的 RAG 问答请求、sources 和响应。 |

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
- `api/conversation.py` 只负责历史会话查询的 HTTP 层，不调用大模型。
- `chat_service.py` 是当前聊天链路的业务中心，SQLite 历史读取、本轮消息写入、普通回答保存和流式回答结束后的完整保存都在这里编排。
- `conversation_service.py` 只读 SQLite 历史数据，不创建新消息、不调用大模型。
- `document_parser.py` 只负责把上传文件转换成纯文本，不切分 chunk、不调用 embedding、不写数据库。
- `embedding_service.py` 只负责文本转向量，不参与 RAG 业务判断。
- `chroma_service.py` 只负责 Chroma collection 的读写和检索，不调用聊天模型、不写 SQLite；多文档检索按多个 `document_id` 分别查询后合并排序。
- `rag_service.py` 复用现有 conversation/message 保存 RAG 问答，chunk 文本和 embedding 统一写入 Chroma；`document_ids` 为空时检索全部文档，流式 RAG 只在结束后保存一条完整 assistant 消息。
- `llm_service.py` 只负责外部大模型调用和响应解析，不直接读写 SQLite。
- `database.py` 只定义数据库模型和连接，不主动参与业务判断。
