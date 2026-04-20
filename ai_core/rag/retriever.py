from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

embedding = OllamaEmbeddings(model="nomic-embed-text")

db = Chroma(
    persist_directory="./vector_db",
    embedding_function=embedding,
)


def retrieve(query: str) -> str:
    """Return top RAG context; empty string if Ollama/Chroma unavailable."""
    try:
        docs = db.similarity_search(query or "", k=3)
        return "\n".join([d.page_content for d in docs]) if docs else ""
    except Exception:
        return ""


def retrieve_sources(query: str) -> list:
    """Return list of RAG chunk contents; empty list if Ollama/Chroma unavailable."""
    try:
        docs = db.similarity_search(query or "", k=3)
        return [{"content": d.page_content} for d in docs]
    except Exception:
        return []
