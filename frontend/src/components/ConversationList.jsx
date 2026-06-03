import ConversationItem from './ConversationItem'

export default function ConversationList({
  activeConversationId = null,
  conversations = [],
  error = '',
  isLoading = false,
  onNewConversation,
  onSelectConversation,
}) {
  return (
    <aside className="conversation-sidebar" aria-label="历史会话">
      <div className="conversation-sidebar__header">
        <h2>历史会话</h2>
        <button className="conversation-sidebar__new" onClick={onNewConversation} type="button">
          新建会话
        </button>
      </div>

      {error && (
        <p className="conversation-sidebar__error" role="alert">
          {error}
        </p>
      )}

      <div className="conversation-list">
        {isLoading && <p className="conversation-list__empty">正在加载...</p>}
        {!isLoading && conversations.length === 0 && (
          <p className="conversation-list__empty">暂无历史会话</p>
        )}
        {!isLoading &&
          conversations.map((conversation) => (
            <ConversationItem
              conversation={conversation}
              isActive={conversation.id === activeConversationId}
              key={conversation.id}
              onSelect={onSelectConversation}
            />
          ))}
      </div>
    </aside>
  )
}
