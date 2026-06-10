# GitHub 项目整理说明

本文记录把当前项目上传到 GitHub 前需要检查的工程化事项。

## 不要提交的内容

- `backend/.env`
- `frontend/.env.local`
- `backend/app.db`
- `backend/chroma_db/`
- `backend/data/`
- `frontend/node_modules/`
- `frontend/dist/`
- 日志文件 `*.log`

这些内容已在 `.gitignore` 中排除。

## 建议提交的内容

- `README.md`
- `backend/.env.example`
- `frontend/.env.example`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `docs/`
- `backend/tests/`
- `.github/workflows/ci.yml`

## CI 检查

`.github/workflows/ci.yml` 会在 push 和 pull request 时运行：

- 后端：`python -m pytest -q`
- 前端：`npm run lint`
- 前端：`npm run build`

CI 不依赖真实大模型 API Key。涉及 LLM、Embedding、Chroma 的测试应继续使用 mock 或纯函数方式。

## 发布前检查

1. 本地运行后端测试。
2. 本地运行前端 lint 和 build。
3. 确认 `.env` 没有被加入 git。
4. 确认 README 中的启动命令和端口仍然正确。
5. 确认 Docker Compose 能读取 `backend/.env`。
