import { useRef, useState } from 'react'

// 输入组件只负责收集文本，并把有效消息提交给父组件。
export default function ChatInput({ disabled = false, onSubmit }) {
  const textareaRef = useRef(null)
  const [value, setValue] = useState('')

  function resizeTextarea() {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }

    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }

  function submitMessage() {
    const message = value.trim()
    if (!message || disabled) {
      return
    }

    onSubmit(message)
    setValue('')
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    })
  }

  function handleSubmit(event) {
    event.preventDefault()
    submitMessage()
  }

  function handleKeyDown(event) {
    if (event.key !== 'Enter' || event.shiftKey) {
      return
    }

    event.preventDefault()
    submitMessage()
  }

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <textarea
        aria-label="聊天消息"
        className="chat-input__textarea"
        disabled={disabled}
        onKeyDown={handleKeyDown}
        onChange={(event) => {
          setValue(event.target.value)
          requestAnimationFrame(resizeTextarea)
        }}
        placeholder="输入消息..."
        ref={textareaRef}
        rows={1}
        value={value}
      />
      <button className="chat-input__button" disabled={disabled || !value.trim()} type="submit">
        {disabled ? '发送中' : '发送'}
      </button>
    </form>
  )
}
