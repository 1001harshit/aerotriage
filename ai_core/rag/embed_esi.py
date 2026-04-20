"""
Load ESI handbook from data/esi_handbook.pdf, split into chunks, embed and store in ChromaDB.
Run from project root: python -m ai_core.rag.embed_esi
"""
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDF_PATH = os.path.join(PROJECT_ROOT, "data", "esi_handbook.pdf")
VECTOR_DIR = os.path.join(PROJECT_ROOT, "vector_db")


def main():
    if not os.path.isfile(PDF_PATH):
        raise FileNotFoundError(f"Place ESI handbook at {PDF_PATH}")

    loader = PyPDFLoader(PDF_PATH)
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    embedding = OllamaEmbeddings(model="nomic-embed-text")
    db = Chroma.from_documents(
        chunks,
        embedding,
        persist_directory=VECTOR_DIR,
    )
    db.persist()
    print(f"Embedded {len(chunks)} chunks into {VECTOR_DIR}")


if __name__ == "__main__":
    main()
