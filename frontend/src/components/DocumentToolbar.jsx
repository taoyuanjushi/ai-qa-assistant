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


export default function DocumentToolbar({
  documents = [],
  error = '',
  isLoading = false,
  isUploading = false,
  onRefresh,
  onSelectDocumentIds,
  onToggleRag,
  onUpload,
  ragEnabled = false,
  selectedDocumentIds = [],
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
      </div>

      <div className="document-toolbar__selection" aria-label="知识库范围">
        <div className="document-toolbar__selection-head">
          <span>{selectedLabel}</span>
        </div>
        {documents.length > 0 && (
          <div className="document-toolbar__document-list">
            {documents.map((document) => (
              <label className="document-option" key={document.id}>
                <input
                  checked={selectedIdSet.has(document.id)}
                  disabled={isLoading}
                  onChange={(event) => handleDocumentToggle(document.id, event.target.checked)}
                  type="checkbox"
                />
                <span className="document-option__name">{document.filename}</span>
                <span className="document-option__meta">
                  {formatFileType(document.file_type)} · {document.chunk_count} chunks
                </span>
              </label>
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
