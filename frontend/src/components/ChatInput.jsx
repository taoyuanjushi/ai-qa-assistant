import { useState } from 'react'

// 输入组件只负责收集文本，并把有效消息提交给父组件。
export default function ChatInput({ disabled = false, onSubmit }) {
  const [value, setValue] = useState('')

  function handleSubmit(event) {
    event.preventDefault()

    const message = value.trim()
    if (!message || disabled) {
      return
    }

    onSubmit(message)
    setValue('')
  }

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <textarea
        aria-label="聊天消息"
        className="chat-input__textarea"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入消息..."
        rows={3}
        value={value}
      />
      <button className="chat-input__button" disabled={disabled || !value.trim()} type="submit">
        {disabled ? '发送中' : '发送'}
      </button>
    </form>
  )
}
