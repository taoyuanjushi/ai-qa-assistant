import { useRef, useState } from 'react'


const SUPPORTED_UPLOAD_EXTENSIONS = ['.txt', '.md', '.markdown', '.pdf', '.docx']
const UNSUPPORTED_FILE_TYPE_MESSAGE = '当前仅支持 TXT、Markdown、PDF、DOCX 文件。'


function getFileExtension(filename) {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex === -1 ? '' : filename.slice(dotIndex).toLowerCase()
}


function formatFileType(fileType) {
  if (fileType === 'markdown') {
    return 'Markdown'
  }

  return fileType ? fileType.toUpperCase() : '未知类型'
}


function formatDocumentStatus(status) {
  // 后端 status 是机器可读值，这里转换成用户能看懂的短文案。
  if (status === 'reindexing') {
    return '重建中'
  }
  if (status === 'failed') {
    return '索引失败'
  }

  return '就绪'
}


function formatSummaryStatus(status) {
  if (status === 'ready') {
    return '摘要已生成'
  }
  if (status === 'failed') {
    return '摘要失败'
  }

  return '摘要待生成'
}


export default function DocumentToolbar({
  deletingDocumentId = null,
  documents = [],
  error = '',
  isClearingKnowledgeBase = false,
  isLoading = false,
  isUploading = false,
  onClearKnowledgeBase,
  onDeleteDocument,
  onRefresh,
  onRegenerateDocumentSummary,
  onReindexDocument,
  onSelectDocumentIds,
  onToggleRag,
  onUpload,
  ragEnabled = false,
  reindexingDocumentId = null,
  selectedDocumentIds = [],
  summarizingDocumentId = null,
  uploadStatus = '',
}) {
  const fileInputRef = useRef(null)
  // selectedFiles 只保存在工具条内，真正上传和入库逻辑由父组件 ChatPage 处理。
  const [selectedFiles, setSelectedFiles] = useState([])
  const [localError, setLocalError] = useState('')
  const selectedIdSet = new Set(selectedDocumentIds)

  function handleFileChange(event) {
    const files = Array.from(event.target.files || [])
    if (files.length === 0) {
      setSelectedFiles([])
      setLocalError('')
      return
    }

    const unsupportedFiles = files.filter(
      (file) => !SUPPORTED_UPLOAD_EXTENSIONS.includes(getFileExtension(file.name)),
    )
    if (unsupportedFiles.length > 0) {
      setSelectedFiles([])
      setLocalError(`${UNSUPPORTED_FILE_TYPE_MESSAGE} 不支持：${unsupportedFiles.map((file) => file.name).join('、')}`)
      event.target.value = ''
      return
    }

    setLocalError('')
    setSelectedFiles(files)
  }

  async function handleUpload(event) {
    event.preventDefault()
    if (selectedFiles.length === 0) {
      return
    }

    // 父组件上传成功后会刷新文档列表；批量上传会返回 uploaded / failed 明细。
    await onUpload?.(selectedFiles)
    setSelectedFiles([])
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  function handleDocumentToggle(documentId, checked) {
    if (checked) {
      onSelectDocumentIds?.([...selectedIdSet, documentId])
      return
    }

    onSelectDocumentIds?.(selectedDocumentIds.filter((id) => id !== documentId))
  }

  function handleUseAllDocuments() {
    onSelectDocumentIds?.([])
    onToggleRag?.(true)
  }

  function handleClearSelection() {
    onSelectDocumentIds?.([])
  }

  function handleDeleteDocument(document) {
    // 删除会同时清 SQLite 元信息和 Chroma 向量索引，因此必须二次确认。
    const confirmed = window.confirm('确定删除该文档吗？删除后将同时删除对应向量索引。')
    if (!confirmed) {
      return
    }

    onDeleteDocument?.(document.id)
  }

  function handleReindexDocument(document) {
    // 重建索引会重新生成 embedding，可能消耗外部 API 调用额度。
    const confirmed = window.confirm('确定重建该文档索引吗？这会删除旧向量并重新生成 embedding。')
    if (!confirmed) {
      return
    }

    onReindexDocument?.(document.id)
  }

  function handleRegenerateDocumentSummary(document) {
    const confirmed = window.confirm('确定重新生成该文档摘要吗？这会再次调用大模型。')
    if (!confirmed) {
      return
    }

    onRegenerateDocumentSummary?.(document.id)
  }

  function handleClearKnowledgeBase() {
    // 清空知识库不删除聊天历史，但会删除所有文档和向量索引。
    const confirmed = window.confirm(
      '确定清空整个知识库吗？这会删除所有文档和向量索引，但不会删除聊天历史。',
    )
    if (!confirmed) {
      return
    }

    onClearKnowledgeBase?.()
  }

  const selectedLabel =
    selectedDocumentIds.length > 0
      ? `已选 ${selectedDocumentIds.length} 个文档`
      : documents.length > 0
        ? '默认检索全部文档'
        : '暂无可用文档'
  const fileSummary =
    selectedFiles.length > 0
      ? `已选择 ${selectedFiles.length} 个文件`
      : '支持 TXT、Markdown、PDF、DOCX'

  return (
    <section className="document-toolbar" aria-label="文档问答工具栏">
      <form className="document-toolbar__upload" onSubmit={handleUpload}>
        <input
          accept=".txt,.md,.markdown,.pdf,.docx"
          aria-label="选择一个或多个文档文件"
          disabled={isUploading}
          multiple
          onChange={handleFileChange}
          ref={fileInputRef}
          type="file"
        />
        <button disabled={isUploading || selectedFiles.length === 0} type="submit">
          {isUploading
            ? '上传中'
            : selectedFiles.length > 1
              ? `上传 ${selectedFiles.length} 个文档`
              : '上传文档'}
        </button>
      </form>
      <p className="document-toolbar__hint">{fileSummary}</p>

      <div className="document-toolbar__controls">
        <label className="document-toolbar__toggle">
          <input
            checked={ragEnabled}
            onChange={(event) => onToggleRag?.(event.target.checked)}
            type="checkbox"
          />
          {/* 开关打开时，ChatPage 会把发送请求切到 /api/rag/chat/stream。 */}
          <span>基于文档回答</span>
        </label>
        <button disabled={isLoading || documents.length === 0} onClick={handleUseAllDocuments} type="button">
          全部文档
        </button>
        <button disabled={isLoading || selectedDocumentIds.length === 0} onClick={handleClearSelection} type="button">
          清空选择
        </button>
        <button disabled={isLoading} onClick={onRefresh} type="button">
          刷新
        </button>
        <button
          className="document-toolbar__clear"
          // 知识库维护操作互斥，避免一个操作未完成时又触发另一个破坏性操作。
          disabled={
            isLoading ||
            isUploading ||
            deletingDocumentId !== null ||
            reindexingDocumentId !== null ||
            summarizingDocumentId !== null ||
            isClearingKnowledgeBase
          }
          onClick={handleClearKnowledgeBase}
          type="button"
        >
          {isClearingKnowledgeBase ? '清空中' : '清空知识库'}
        </button>
      </div>

      <div className="document-toolbar__selection" aria-label="知识库范围">
        <div className="document-toolbar__selection-head">
          <span>{selectedLabel}</span>
        </div>
        {documents.length > 0 && (
          <div className="document-toolbar__document-list">
            {documents.map((document) => (
              <div className="document-option" key={document.id}>
                <input
                  aria-label={`选择文档 ${document.filename}`}
                  checked={selectedIdSet.has(document.id)}
                  disabled={
                    isLoading ||
                    deletingDocumentId !== null ||
                    reindexingDocumentId !== null ||
                    summarizingDocumentId !== null ||
                    isClearingKnowledgeBase
                  }
                  onChange={(event) => handleDocumentToggle(document.id, event.target.checked)}
                  type="checkbox"
                />
                <span className="document-option__name">{document.filename}</span>
                <span className="document-option__actions">
                  <button
                    aria-label={`重建文档索引 ${document.filename}`}
                    className="document-option__reindex"
                    // 单文档维护期间禁用其他文档操作，保持 selectedDocumentIds 和列表同步。
                    disabled={
                      isLoading ||
                      deletingDocumentId !== null ||
                      reindexingDocumentId !== null ||
                      summarizingDocumentId !== null ||
                      isClearingKnowledgeBase
                    }
                    onClick={() => handleReindexDocument(document)}
                    type="button"
                  >
                    {reindexingDocumentId === document.id ? '重建中' : '重建索引'}
                  </button>
                  <button
                    aria-label={`重新生成文档摘要 ${document.filename}`}
                    className="document-option__summary"
                    disabled={
                      isLoading ||
                      deletingDocumentId !== null ||
                      reindexingDocumentId !== null ||
                      summarizingDocumentId !== null ||
                      isClearingKnowledgeBase
                    }
                    onClick={() => handleRegenerateDocumentSummary(document)}
                    type="button"
                  >
                    {summarizingDocumentId === document.id ? '摘要中' : '生成摘要'}
                  </button>
                  <button
                    aria-label={`删除文档 ${document.filename}`}
                    className="document-option__delete"
                    disabled={
                      isLoading ||
                      deletingDocumentId !== null ||
                      reindexingDocumentId !== null ||
                      summarizingDocumentId !== null ||
                      isClearingKnowledgeBase
                    }
                    onClick={() => handleDeleteDocument(document)}
                    type="button"
                  >
                    {deletingDocumentId === document.id ? '删除中' : '删除'}
                  </button>
                </span>
                <span className="document-option__meta">
                  {formatFileType(document.file_type)} · {document.chunk_count} chunks · {formatDocumentStatus(document.status)} · {formatSummaryStatus(document.summary_status)}
                </span>
                {document.summary_preview && (
                  <span className="document-option__summary-preview">
                    {document.summary_preview}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {(error || localError) && (
        <p
          className="document-toolbar__error"
          role="status"
        >
          {error || localError}
        </p>
      )}

      {uploadStatus && (
        <p
          className="document-toolbar__status"
          role="status"
        >
          {uploadStatus}
        </p>
      )}
    </section>
  )
}
