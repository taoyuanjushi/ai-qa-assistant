import MessageItem from './MessageItem'

// 消息列表组件负责渲染聊天记录和“正在生成回复”的占位状态。
export default function MessageList({ isLoading = false, messages = [] }) {
  if (messages.length === 0) {
    return (
      <div className="message-list" aria-live="polite">
        <p className="message-list__empty">
          {isLoading ? '正在生成回复...' : '暂无消息'}
        </p>
      </div>
    )
  }

  return (
    <div className="message-list" aria-live="polite">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      {isLoading && (
        <MessageItem
          message={{
            id: 'loading',
            role: 'assistant',
            content: '正在生成回复...',
          }}
        />
      )}
    </div>
  )
}
