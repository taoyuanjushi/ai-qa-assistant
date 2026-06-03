export default function ConversationItem({ conversation, isActive = false, onSelect }) {
  return (
    <button
      className={`conversation-item${isActive ? ' conversation-item--active' : ''}`}
      onClick={() => onSelect(conversation.id)}
      type="button"
    >
      <span className="conversation-item__title">{conversation.title}</span>
      <span className="conversation-item__time">
        {new Date(conversation.updated_at).toLocaleString()}
      </span>
    </button>
  )
}
