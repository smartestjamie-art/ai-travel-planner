from __future__ import annotations

import re
from hashlib import md5

import httpx

from app.config import (
    BACKEND_DIR,
    CHROMA_COLLECTION_NAME,
    CHROMA_DB_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    LLM_API_KEY,
    LLM_BASE_URL,
)


DATA_DIR = BACKEND_DIR / "data"


def _split_markdown_into_chunks(markdown_text: str, source_name: str) -> list[dict[str, str]]:
    """Split Markdown by level-2 and level-3 headings, returning searchable chunks."""
    chunks: list[dict[str, str]] = []
    current_title = "Document start"
    current_lines: list[str] = []

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            if current_lines:
                chunks.append(
                    {
                        "title": current_title,
                        "text": "\n".join(current_lines).strip(),
                        "source": source_name,
                    }
                )
                current_lines = []
            current_title = stripped.lstrip("#").strip()
        elif stripped:
            current_lines.append(stripped)

    if current_lines:
        chunks.append(
            {
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
                "source": source_name,
            }
        )

    return chunks


def _build_chunk_id(source: str, title: str, text: str) -> str:
    """Generate a stable chunk ID based on source, title, and text."""
    digest = md5(f"{source}|{title}|{text}".encode("utf-8")).hexdigest()
    return f"{source}_{digest}"


def _build_document_text(chunk: dict[str, str]) -> str:
    """Join the title and body into the document text sent to the vector store."""
    return f"{chunk['title']}\n{chunk['text']}"


def load_guide_chunks() -> list[dict[str, str]]:
    """Read guide files under backend/data and split them into searchable chunks."""
    chunks: list[dict[str, str]] = []
    for guide_file in sorted(DATA_DIR.glob("*.md*")):
        text = guide_file.read_text(encoding="utf-8")
        raw_chunks = _split_markdown_into_chunks(text, guide_file.name)
        for chunk in raw_chunks:
            chunks.append(
                {
                    "id": _build_chunk_id(chunk["source"], chunk["title"], chunk["text"]),
                    "title": chunk["title"],
                    "text": chunk["text"],
                    "source": chunk["source"],
                }
            )
    return chunks


def _extract_keywords(query: str) -> list[str]:
    """Split the query into simple keywords for fallback matching."""
    raw_keywords = re.split(r"[\s,，。；;、]+", query)
    return [keyword.strip() for keyword in raw_keywords if keyword.strip()]


def _score_chunk(query: str, chunk_text: str) -> int:
    """Score a chunk by the number of keyword occurrences."""
    keywords = _extract_keywords(query)
    return sum(1 for keyword in keywords if keyword in chunk_text)


def _search_guide_chunks_by_keywords(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Fallback: match local guide chunks using keywords."""
    scored_chunks: list[tuple[int, dict[str, str]]] = []
    for chunk in load_guide_chunks():
        score = _score_chunk(query, _build_document_text(chunk))
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


def _build_embeddings():
    """Create an embedding model instance."""
    if not LLM_API_KEY:
        return None

    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        return None

    try:
        return OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL or None,
            chunk_size=EMBEDDING_BATCH_SIZE,
            check_embedding_ctx_length=False,
        )
    except TypeError:
        return OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=LLM_API_KEY,
            openai_api_base=LLM_BASE_URL or None,
            chunk_size=EMBEDDING_BATCH_SIZE,
            check_embedding_ctx_length=False,
        )


def _extract_embedding_token_usage(response_data: dict) -> dict[str, int]:
    """Read the official usage returned by the embeddings API; default to 0 when absent."""
    usage = response_data.get("usage") or {}
    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("input_token_count")
        or usage.get("total_tokens")
        or usage.get("total_token_count")
        or 0
    )
    return {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": 0,
    }


def _embed_query_with_usage(query: str) -> tuple[list[float] | None, dict[str, int]]:
    """Online query embedding: prefer calling the API directly for official usage; on failure, fall back to LangChain with usage reported as 0."""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not LLM_API_KEY:
        return None, empty_usage

    base_url = (LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
    endpoint = f"{base_url}/embeddings"
    payload = {
        "model": EMBEDDING_MODEL,
        "input": query,
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(endpoint, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            items = data.get("data") or []
            if items and "embedding" in items[0]:
                usage = _extract_embedding_token_usage(data)
                print(
                    "[embedding] query embedding token: "
                    f"prompt={usage['prompt_tokens']}, completion=0, source=api"
                )
                return items[0]["embedding"], usage
            print(f"[embedding] embeddings response missing vector: {response.text[:500]}")
        else:
            print(
                "[embedding] embeddings API failed: "
                f"status_code={response.status_code}, response={response.text[:500]}"
            )
    except Exception as exc:
        print(f"[embedding] embeddings API failed: {type(exc).__name__}: {exc}")

    embeddings = _build_embeddings()
    if embeddings is None:
        return None, empty_usage
    print("[embedding] falling back to LangChain embed_query; official token usage unavailable")
    return embeddings.embed_query(query), empty_usage


def _get_chroma_collection():
    """Get the Chroma collection."""
    try:
        import chromadb
    except ImportError:
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_guide_chunks_to_chroma() -> int:
    """
    Write local guide chunks into Chroma.

    The process is:
    1. Create the embedding model
    2. Get the Chroma collection
    3. Read and split the local guides
    4. Generate vectors
    5. Write the vectors, text, and metadata into Chroma together
    """
    embeddings = _build_embeddings()
    collection = _get_chroma_collection()
    chunks = load_guide_chunks()

    if embeddings is None:
        raise RuntimeError("The current environment lacks embedding capability; cannot write to Chroma.")
    if collection is None:
        raise RuntimeError("The current environment lacks chromadb; cannot write to Chroma.")

    documents = [_build_document_text(chunk) for chunk in chunks]
    vectors = embeddings.embed_documents(documents)
    ids = [chunk["id"] for chunk in chunks]
    metadatas = [
        {
            "title": chunk["title"],
            "source": chunk["source"],
        }
        for chunk in chunks
    ]

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=vectors,
    )
    return len(chunks)


def _search_guide_chunks_by_chroma(
    query: str, top_k: int = 3
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Prefer Chroma for vector search, and return the online query embedding token usage."""
    collection = _get_chroma_collection()
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    if collection is None:
        return [], empty_usage
    if collection.count() == 0:
        return [], empty_usage

    query_embedding, embedding_usage = _embed_query_with_usage(query)
    if query_embedding is None:
        return [], empty_usage
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    matched_chunks: list[dict[str, str]] = []
    for document, metadata in zip(documents, metadatas):
        title = metadata.get("title", "Untitled chunk") if metadata else "Untitled chunk"
        source = metadata.get("source", "Unknown source") if metadata else "Unknown source"
        text = document.split("\n", 1)[1] if "\n" in document else document
        matched_chunks.append(
            {
                "title": title,
                "text": text,
                "source": source,
            }
        )

    return matched_chunks, embedding_usage


def search_guide_chunks_with_usage(
    query: str, top_k: int = 3
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """
    Find the top_k most relevant results from local guide chunks.

    Prefer Chroma vector search; fall back to keyword search if the current
    environment is not ready.
    """
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    chroma_results, embedding_usage = _search_guide_chunks_by_chroma(query=query, top_k=top_k)
    if chroma_results:
        return chroma_results, embedding_usage
    return _search_guide_chunks_by_keywords(query=query, top_k=top_k), empty_usage


def search_guide_chunks(query: str, top_k: int = 3) -> list[dict[str, str]]:
    """Backward-compatible call: return only the search chunks, without token usage."""
    chunks, _ = search_guide_chunks_with_usage(query=query, top_k=top_k)
    return chunks
