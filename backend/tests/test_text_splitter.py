from app.services.rag_service import MAX_CHUNK_CHARS, split_text_into_chunks


def test_split_text_into_chunks_for_normal_text():
    chunks = split_text_into_chunks("第一段内容。\n\n第二段内容。")

    assert chunks == ["第一段内容。\n\n第二段内容。"]


def test_split_text_into_chunks_for_empty_text():
    assert split_text_into_chunks("") == []


def test_split_text_into_chunks_for_long_text():
    chunks = split_text_into_chunks("a" * (MAX_CHUNK_CHARS * 2 + 100))

    assert len(chunks) >= 3
    assert all(len(chunk) <= MAX_CHUNK_CHARS for chunk in chunks)
