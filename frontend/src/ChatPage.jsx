import { useCallback, useEffect, useState } from 'react'
import { sendChatMessageStream } from './api/chatApi'
import { fetchConversationMessages, fetchConversations } from './api/conversationApi'
import ChatInput from './components/ChatInput'
import ConversationList from './components/ConversationList'
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

function createMessageFromApi(message) {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
  }
}

export default function ChatPage() {
  // messages 保存当前页面上已经展示的聊天记录。
  const [messages, setMessages] = useState([])
  // isLoading 控制发送按钮禁用和“正在生成回复...”占位消息。
  const [isLoading, setIsLoading] = useState(false)
  // error 保存本次请求失败时展示给用户的错误提示。
  const [error, setError] = useState('')
  // conversationId 保存后端返回的当前会话 ID，后续追问会继续传给后端。
  const [conversationId, setConversationId] = useState(null)
  const [conversations, setConversations] = useState([])
  const [isLoadingConversations, setIsLoadingConversations] = useState(true)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [conversationError, setConversationError] = useState('')

  const loadConversations = useCallback(async () => {
    setIsLoadingConversations(true)
    setConversationError('')

    try {
      const data = await fetchConversations()
      setConversations(data)
    } catch (err) {
      setConversationError(err.message || '加载历史会话失败。')
    } finally {
      setIsLoadingConversations(false)
    }
  }, [])

  useEffect(() => {
    let isActive = true

    fetchConversations()
      .then((data) => {
        if (!isActive) {
          return
        }
        setConversations(data)
        setConversationError('')
      })
      .catch((err) => {
        if (!isActive) {
          return
        }
        setConversationError(err.message || '加载历史会话失败。')
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingConversations(false)
        }
      })

    return () => {
      isActive = false
    }
  }, [])

  async function handleSelectConversation(selectedConversationId) {
    setIsLoadingMessages(true)
    setError('')

    try {
      const data = await fetchConversationMessages(selectedConversationId)
      setConversationId(data.conversation_id)
      setMessages(data.messages.map(createMessageFromApi))
    } catch (err) {
      setError(err.message || '加载会话消息失败。')
    } finally {
      setIsLoadingMessages(false)
    }
  }

  function handleNewConversation() {
    setConversationId(null)
    setMessages([])
    setError('')
  }

  async function handleSend(message) {
    // 用户点击发送后的前端入口：先显示用户消息，再等待后端回答。
    const userMessage = createMessage('user', message)
    const assistantMessage = createMessage('assistant', '')

    // 乐观更新：先把用户输入和空 AI 消息展示到页面，不等后端返回。
    setMessages((currentMessages) => [...currentMessages, userMessage, assistantMessage])
    // 请求未完成前禁用输入区，避免重复提交。
    setIsLoading(true)
    // 新请求开始时清掉上一次的错误提示。
    setError('')

    try {
      // 调用流式 API，每个 chunk 都追加到同一条 assistant 消息。
      await sendChatMessageStream(
        message,
        conversationId,
        (chunk) => {
          setMessages((currentMessages) =>
            currentMessages.map((currentMessage) =>
              currentMessage.id === assistantMessage.id
                ? {
                    ...currentMessage,
                    content: currentMessage.content + chunk,
                  }
                : currentMessage,
            ),
          )
        },
        (nextConversationId) => {
          setConversationId(nextConversationId)
        },
      )
      await loadConversations()
    } catch (err) {
      setMessages((currentMessages) =>
        currentMessages.filter((currentMessage) => currentMessage.id !== assistantMessage.id),
      )
      // 请求失败或响应格式异常时，把错误显示在聊天区域下方。
      setError(err.message || '发送失败，请稍后重试。')
    } finally {
      // 无论成功失败，都结束 loading 状态，让用户可以继续输入。
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <div className="app-layout">
        <ConversationList
          activeConversationId={conversationId}
          conversations={conversations}
          error={conversationError}
          isLoading={isLoadingConversations}
          onNewConversation={handleNewConversation}
          onSelectConversation={handleSelectConversation}
        />

        <section className="chat-panel" aria-label="聊天窗口">
          <header className="chat-header">
            <h1>AI 问答助手</h1>
          </header>

          <div className="chat-body">
            {isLoadingMessages ? (
              <p className="message-list__empty">正在加载会话...</p>
            ) : (
              <MessageList isLoading={isLoading} messages={messages} />
            )}
            {error && (
              <p className="chat-error" role="alert">
                {error}
              </p>
            )}
          </div>

          {/* ChatInput 提交后会回调 handleSend，disabled 跟随 loading 状态。 */}
          <ChatInput disabled={isLoading || isLoadingMessages} onSubmit={handleSend} />
        </section>
      </div>
    </main>
  )
}
