from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

loader = PyPDFLoader("data/esi_handbook.pdf")
documents = loader.load()

embedding = OllamaEmbeddings(model="nomic-embed-text")

db = Chroma.from_documents(
    documents,
    embedding,
    persist_directory="./vector_db",
)
db.persist()
