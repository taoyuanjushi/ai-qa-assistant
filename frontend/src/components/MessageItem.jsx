// 单条消息组件只关心角色和内容的展示样式。
export default function MessageItem({ isPending = false, message }) {
  const content =
    isPending && !message.content ? '正在生成回复...' : message.content

  return (
    <article className={`message-item message-item--${message.role}`}>
      <strong>{message.role === 'assistant' ? 'AI' : '我'}</strong>
      <p>{content}</p>
    </article>
  )
}
