import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { sendChatMessageStream } from './api/chatApi'
import { fetchConversationMessages, fetchConversations } from './api/conversationApi'
import {
  clearKnowledgeBase,
  deleteDocument,
  getDocuments,
  ragChatStream,
  regenerateDocumentSummary,
  reindexDocument,
  uploadDocuments,
} from './api/ragApi'
import ChatInput from './components/ChatInput'
import ConversationList from './components/ConversationList'
import DocumentToolbar from './components/DocumentToolbar'
import MessageList from './components/MessageList'

// 聊天页面容器：维护前端消息、loading、错误状态，并触发后端请求。
function createMessage(role, content, extra = {}) {
  return {
    // 前端临时 ID 只用于 React 列表渲染，不是数据库里的 message.id。
    id: crypto.randomUUID(),
    // role 决定消息显示成“我”还是“AI”。
    role,
    content,
    ...extra,
  }
}

function createMessageFromApi(message) {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
  }
}

function formatFileType(fileType) {
  if (fileType === 'markdown') {
    return 'Markdown'
  }

  return fileType ? fileType.toUpperCase() : '未知类型'
}

export default function ChatPage() {
  const messageScrollRef = useRef(null)
  const shouldStickToBottomRef = useRef(true)
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
  // documents 和 selectedDocumentIds 控制主聊天窗口里的“基于文档回答”知识库范围。
  const [documents, setDocuments] = useState([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  // ragEnabled 为 false 时保持原流式聊天；为 true 时走 /api/rag/chat/stream。
  const [ragEnabled, setRagEnabled] = useState(false)
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true)
  const [isUploadingDocument, setIsUploadingDocument] = useState(false)
  const [documentError, setDocumentError] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  // 以下三个状态用于文档维护操作互斥，避免同时删除、清空或重建造成列表状态错乱。
  const [deletingDocumentId, setDeletingDocumentId] = useState(null)
  const [isClearingKnowledgeBase, setIsClearingKnowledgeBase] = useState(false)
  const [reindexingDocumentId, setReindexingDocumentId] = useState(null)
  const [summarizingDocumentId, setSummarizingDocumentId] = useState(null)

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === conversationId) || null,
    [conversationId, conversations],
  )
  const headerSubtitle = activeConversation
    ? activeConversation.title
    : conversationId
      ? `会话 #${conversationId}`
      : '新会话'

  const scrollMessagesToBottom = useCallback((behavior = 'smooth') => {
    const scrollElement = messageScrollRef.current
    if (!scrollElement) {
      return
    }

    scrollElement.scrollTo({
      top: scrollElement.scrollHeight,
      behavior,
    })
  }, [])

  function handleMessageScroll() {
    const scrollElement = messageScrollRef.current
    if (!scrollElement) {
      return
    }

    const distanceToBottom =
      scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight
    shouldStickToBottomRef.current = distanceToBottom < 120
  }

  useEffect(() => {
    if (!isLoading && !isLoadingMessages && !shouldStickToBottomRef.current) {
      return undefined
    }

    const frameId = requestAnimationFrame(() => {
      scrollMessagesToBottom(isLoading ? 'auto' : 'smooth')
    })

    return () => cancelAnimationFrame(frameId)
  }, [isLoading, isLoadingMessages, messages, scrollMessagesToBottom])

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

  const loadDocuments = useCallback(async () => {
    setIsLoadingDocuments(true)
    setDocumentError('')

    try {
      // 文档列表来自 SQLite 的 document 元信息，不从 Chroma 读取正文。
      const data = await getDocuments()
      setDocuments(data)
      setSelectedDocumentIds((currentIds) => {
        const availableIds = new Set(data.map((document) => document.id))
        return currentIds.filter((id) => availableIds.has(id))
      })
    } catch (err) {
      setDocumentError(err.message || '加载文档列表失败。')
    } finally {
      setIsLoadingDocuments(false)
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

  useEffect(() => {
    let isActive = true

    // 页面首次打开时加载可选文档，方便用户直接切换到文档问答模式。
    getDocuments()
      .then((data) => {
        if (!isActive) {
          return
        }
        setDocuments(data)
        setSelectedDocumentIds([])
        setDocumentError('')
      })
      .catch((err) => {
        if (!isActive) {
          return
        }
        setDocumentError(err.message || '加载文档列表失败。')
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingDocuments(false)
        }
      })

    return () => {
      isActive = false
    }
  }, [])

  async function handleSelectConversation(selectedConversationId) {
    shouldStickToBottomRef.current = true
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

  async function handleUploadDocuments(files) {
    setIsUploadingDocument(true)
    setDocumentError('')
    setUploadStatus('')

    try {
      // 上传成功后后端已经完成 chunk 切分、embedding 生成和 Chroma 写入。
      const result = await uploadDocuments(files)
      const uploaded = result.uploaded || []
      const failed = result.failed || []

      if (uploaded.length > 0) {
        const chunkCount = uploaded.reduce((sum, document) => sum + document.chunk_count, 0)
        const uploadedNames = uploaded
          .map((document) => `${document.filename} [${formatFileType(document.file_type)}]`)
          .join('、')
        setUploadStatus(`已上传 ${uploaded.length} 个文档，${chunkCount} chunks：${uploadedNames}`)
      }

      if (failed.length > 0) {
        const failedSummary = failed
          .map((item) => `${item.filename}：${item.error}`)
          .join('；')
        setDocumentError(`部分文件上传失败：${failedSummary}`)
      }

      await loadDocuments()
      if (uploaded.length > 0) {
        setSelectedDocumentIds(uploaded.map((document) => document.document_id))
        setRagEnabled(true)
      }
    } catch (err) {
      setDocumentError(err.message || '上传文档失败。')
    } finally {
      setIsUploadingDocument(false)
    }
  }

  async function handleDeleteDocument(documentId) {
    setDeletingDocumentId(documentId)
    setDocumentError('')
    setUploadStatus('')

    try {
      const result = await deleteDocument(documentId)
      // 删除成功后先从当前选择里移除，再刷新列表，避免短时间内继续传已删除 ID。
      setSelectedDocumentIds((currentIds) => currentIds.filter((id) => id !== documentId))
      await loadDocuments()
      setUploadStatus(result.message || '文档已删除，对应向量索引也已清理')
    } catch (err) {
      setDocumentError(err.message || '删除文档失败。')
    } finally {
      setDeletingDocumentId(null)
    }
  }

  async function handleClearKnowledgeBase() {
    setIsClearingKnowledgeBase(true)
    setDocumentError('')
    setUploadStatus('')

    try {
      const result = await clearKnowledgeBase()
      // 清空知识库后关闭 RAG 开关，避免下一次发送时仍走文档问答但已无可用文档。
      setDocuments([])
      setSelectedDocumentIds([])
      setRagEnabled(false)
      await loadDocuments()
      setUploadStatus(result.message || '知识库已清空')
    } catch (err) {
      setDocumentError(err.message || '清空知识库失败。')
    } finally {
      setIsClearingKnowledgeBase(false)
    }
  }

  async function handleReindexDocument(documentId) {
    setReindexingDocumentId(documentId)
    setDocumentError('')
    setUploadStatus('')

    try {
      const result = await reindexDocument(documentId)
      // 重建索引不会改变选中范围，只刷新列表中的 chunk_count/status。
      await loadDocuments()
      setUploadStatus(`${result.message}：${result.filename}，${result.chunk_count} chunks`)
    } catch (err) {
      setDocumentError(err.message || '重建文档索引失败。')
    } finally {
      setReindexingDocumentId(null)
    }
  }

  async function handleRegenerateDocumentSummary(documentId) {
    setSummarizingDocumentId(documentId)
    setDocumentError('')
    setUploadStatus('')

    try {
      const result = await regenerateDocumentSummary(documentId)
      await loadDocuments()
      setUploadStatus(`${result.message}：${result.filename}`)
    } catch (err) {
      setDocumentError(err.message || '重新生成文档摘要失败。')
    } finally {
      setSummarizingDocumentId(null)
    }
  }

  function handleNewConversation() {
    shouldStickToBottomRef.current = true
    setConversationId(null)
    setMessages([])
    setError('')
  }

  async function handleSend(message) {
    if (ragEnabled && documents.length === 0) {
      setError('请先上传文档，或关闭“基于文档回答”。')
      return
    }

    // 用户点击发送后的前端入口：先显示用户消息，再等待后端回答。
    const userMessage = createMessage('user', message)
    const assistantMessage = createMessage('assistant', '', {
      isStreaming: true,
      sources: [],
    })
    shouldStickToBottomRef.current = true

    // 乐观更新：先把用户输入和空 AI 消息展示到页面，不等后端返回。
    setMessages((currentMessages) => [...currentMessages, userMessage, assistantMessage])
    // 请求未完成前禁用输入区，避免重复提交。
    setIsLoading(true)
    // 新请求开始时清掉上一次的错误提示。
    setError('')

    try {
      if (ragEnabled) {
        // 文档问答走 NDJSON 流：metadata 先返回 sources，chunk 再逐步追加回答。
        await ragChatStream({
          question: message,
          document_ids: selectedDocumentIds,
          conversation_id: conversationId,
          onMetadata: (metadata) => {
            setConversationId(metadata.conversation_id)
            setMessages((currentMessages) =>
              currentMessages.map((currentMessage) =>
                currentMessage.id === assistantMessage.id
                  ? {
                      ...currentMessage,
                      sources: Array.isArray(metadata.sources) ? metadata.sources : [],
                    }
                  : currentMessage,
              ),
            )
          },
          onChunk: (chunk) => {
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
          onDone: () => {
            setMessages((currentMessages) =>
              currentMessages.map((currentMessage) =>
                currentMessage.id === assistantMessage.id
                  ? {
                      ...currentMessage,
                      isStreaming: false,
                    }
                  : currentMessage,
              ),
            )
          },
          onError: (message) => {
            setError(message)
            setMessages((currentMessages) =>
              currentMessages.map((currentMessage) =>
                currentMessage.id === assistantMessage.id
                  ? {
                      ...currentMessage,
                      isStreaming: false,
                    }
                  : currentMessage,
              ),
            )
          },
        })
        setMessages((currentMessages) =>
          currentMessages.map((currentMessage) =>
            currentMessage.id === assistantMessage.id
              ? {
                  ...currentMessage,
                  isStreaming: false,
                }
              : currentMessage,
          ),
        )
      } else {
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
      }
      await loadConversations()
    } catch (err) {
      setMessages((currentMessages) =>
        currentMessages.flatMap((currentMessage) => {
          if (currentMessage.id !== assistantMessage.id) {
            return [currentMessage]
          }

          const hasSources = Array.isArray(currentMessage.sources) && currentMessage.sources.length > 0
          if (!currentMessage.content && !hasSources) {
            return []
          }

          return [{ ...currentMessage, isStreaming: false }]
        }),
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
            <div>
              <h1>AI 问答助手</h1>
              <p>{headerSubtitle}</p>
            </div>
          </header>

          <DocumentToolbar
            documents={documents}
            error={documentError}
            deletingDocumentId={deletingDocumentId}
            isClearingKnowledgeBase={isClearingKnowledgeBase}
            isLoading={isLoadingDocuments}
            isUploading={isUploadingDocument}
            onClearKnowledgeBase={handleClearKnowledgeBase}
            onDeleteDocument={handleDeleteDocument}
            onRefresh={loadDocuments}
            onRegenerateDocumentSummary={handleRegenerateDocumentSummary}
            onReindexDocument={handleReindexDocument}
            onSelectDocumentIds={setSelectedDocumentIds}
            onToggleRag={setRagEnabled}
            onUpload={handleUploadDocuments}
            ragEnabled={ragEnabled}
            reindexingDocumentId={reindexingDocumentId}
            selectedDocumentIds={selectedDocumentIds}
            summarizingDocumentId={summarizingDocumentId}
            uploadStatus={uploadStatus}
          />

          <div
            className="message-scroll-area"
            onScroll={handleMessageScroll}
            ref={messageScrollRef}
          >
            <div className="message-scroll-area__inner">
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
          </div>

          <footer className="chat-input-area">
            {/* ChatInput 提交后会回调 handleSend，disabled 跟随 loading 状态。 */}
            <ChatInput disabled={isLoading || isLoadingMessages} onSubmit={handleSend} />
          </footer>
        </section>
      </div>
    </main>
  )
}
