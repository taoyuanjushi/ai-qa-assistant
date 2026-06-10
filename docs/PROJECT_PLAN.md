项目名称：AI 问答助手

技术栈：
- 前端：React + Vite
- 后端：FastAPI
- 数据库：SQLite
- 模型：通过大模型 API 调用

MVP 目标：
1. 前端可以输入问题；
2. 后端可以接收问题；
3. 后端可以调用大模型 API；
4. 前端可以显示 AI 回答；
5. 后端可以保存聊天记录。

当前已扩展能力：
1. 普通聊天和流式聊天；
2. 历史会话列表和会话消息加载；
3. TXT / Markdown / PDF / DOCX 文档解析；
4. 单文件和批量上传文档；
5. Chroma 多文档 RAG 和流式 RAG；
6. sources 展示；
7. 删除单个文档；
8. 清空知识库；
9. 基于 `document.content` 重建单文档索引；
10. Rerank 检索重排，优先专业 rerank API，可回退到 LLM/规则 rerank；
11. 文档摘要缓存和重新生成摘要；
12. 多文档论文分析结合 document summary 和 reranked sources；
13. 统一错误响应、请求日志和外部依赖耗时日志；
14. Docker Compose 基础启动；
15. GitHub Actions CI；
16. 后端 pytest 基础测试和前端手动测试清单。

开发原则：
1. 每次只完成一个小任务；
2. 修改前先说明计划；
3. 修改后说明改了哪些文件；
4. 每一步都要给出运行和验收方法；
5. 不要一次性引入复杂框架；
6. 不要把 API Key 写进代码；
7. .env 必须加入 .gitignore。
