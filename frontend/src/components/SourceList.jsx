export default function SourceList({ sources = [] }) {
  if (sources.length === 0) {
    return <p className="source-list__empty">本次没有返回 sources。</p>
  }

  // sources 来自 Chroma 检索结果，和后端拼进 RAG Prompt 的 chunk 保持一致。
  return (
    <div className="source-list" aria-label="引用片段">
      <strong>Sources</strong>
      {sources.map((source) => (
        <article
          className="source-item"
          key={`${source.document_id}-${source.chunk_index}-${source.score}`}
        >
          <div className="source-item__meta">
            {source.filename} [{formatFileType(source.file_type)}] · Chunk #
            {source.chunk_index} · score {formatScore(source.score)}
          </div>
          <p>{source.content}</p>
        </article>
      ))}
    </div>
  )
}


function formatScore(score) {
  // Chroma 使用 cosine distance，后端已经换算成越大越相关的 score。
  const numericScore = Number(score)
  return Number.isFinite(numericScore) ? numericScore.toFixed(4) : String(score)
}


function formatFileType(fileType) {
  if (fileType === 'markdown') {
    return 'Markdown'
  }

  return fileType ? String(fileType).toUpperCase() : '未知类型'
}
