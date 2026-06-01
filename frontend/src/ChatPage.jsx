import { useState } from 'react'
import { sendChatMessage } from './api/chatApi'
import ChatInput from './components/ChatInput'
import MessageList from './components/MessageList'

// 聊天页面容器：维护前端消息、loading、错误状态，并触发后端请求。
function createMessage(role, content) {
  return {
    // 前端临时 ID 只用于 React 列表渲染，不是数据库里的 message.id。
    id: crypto.randomUUID(),
    // role 决定消息显示成“我”还是“AI”。
    role,
    content,
  }
}

export default function ChatPage() {
  // messages 保存当前页面上已经展示的聊天记录。
  const [messages, setMessages] = useState([])
  // isLoading 控制发送按钮禁用和“正在生成回复...”占位消息。
  const [isLoading, setIsLoading] = useState(false)
  // error 保存本次请求失败时展示给用户的错误提示。
  const [error, setError] = useState('')

  async function handleSend(message) {
    // 用户点击发送后的前端入口：先显示用户消息，再等待后端回答。
    const userMessage = createMessage('user', message)

    // 乐观更新：先把用户输入展示到页面，不等后端返回。
    setMessages((currentMessages) => [...currentMessages, userMessage])
    // 请求未完成前禁用输入区，避免重复提交。
    setIsLoading(true)
    // 新请求开始时清掉上一次的错误提示。
    setError('')

    try {
      // 调用封装好的 API 函数，真正发起 POST /api/chat。
      const data = await sendChatMessage(message)

      // 后端返回 answer 后，追加一条 AI 消息到页面。
      setMessages((currentMessages) => [
        ...currentMessages,
        createMessage('assistant', data.answer),
      ])
    } catch (err) {
      // 请求失败或响应格式异常时，把错误显示在聊天区域下方。
      setError(err.message || '发送失败，请稍后重试。')
    } finally {
      // 无论成功失败，都结束 loading 状态，让用户可以继续输入。
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="chat-panel" aria-label="聊天窗口">
        <header className="chat-header">
          <h1>AI 问答助手</h1>
        </header>

        <div className="chat-body">
          {/* 消息列表根据 isLoading 决定是否展示“正在生成回复...” */}
          <MessageList isLoading={isLoading} messages={messages} />
          {error && (
            <p className="chat-error" role="alert">
              {error}
            </p>
          )}
        </div>

        {/* ChatInput 提交后会回调 handleSend，disabled 跟随 loading 状态。 */}
        <ChatInput disabled={isLoading} onSubmit={handleSend} />
      </section>
    </main>
  )
}
