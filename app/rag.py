import os
import uuid
import json
from pathlib import Path

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from fastapi import HTTPException

UPLOAD_DIR = Path("uploads")
CHROMA_DIR = "chroma_db"
DOCS_META_FILE = "documents.json"
UPLOAD_DIR.mkdir(exist_ok=True)

PROMPT = ChatPromptTemplate.from_template("""You are a helpful assistant. Answer the question using ONLY the context below.
If the answer is not in the context, say: "I couldn't find that information in the uploaded documents."

Context:
{context}

Question: {question}

Answer:""")


def _get_embeddings():
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def _get_vectorstore():
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=_get_embeddings())


def _load_meta() -> dict:
    if not os.path.exists(DOCS_META_FILE):
        return {}
    with open(DOCS_META_FILE) as f:
        return json.load(f)


def _save_meta(meta: dict):
    with open(DOCS_META_FILE, "w") as f:
        json.dump(meta, f)


def _format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def process_document(file_bytes: bytes, filename: str, username: str) -> dict:
    doc_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{doc_id}_{filename}"

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    reader = PdfReader(file_path)
    text = "\n".join(
        page.extract_text() for page in reader.pages if page.extract_text()
    )

    if not text.strip():
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not extract text from this PDF")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents(
        texts=[text],
        metadatas=[{"doc_id": doc_id, "filename": filename, "username": username}],
    )

    _get_vectorstore().add_documents(chunks)

    meta = _load_meta()
    meta[doc_id] = {"filename": filename, "username": username, "chunks": len(chunks)}
    _save_meta(meta)

    return {"document_id": doc_id, "filename": filename, "chunks_stored": len(chunks)}


def ask_question(question: str, username: str, doc_id: str = None) -> dict:
    vectorstore = _get_vectorstore()
    if doc_id:
        filter_dict = {"$and": [{"username": {"$eq": username}}, {"doc_id": {"$eq": doc_id}}]}
    else:
        filter_dict = {"username": {"$eq": username}}

    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 4, "filter": filter_dict}
    )

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        groq_api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=1024,
    )

    # Retrieve docs separately so we can return sources
    docs = retriever.invoke(question)

    chain = (
        {"context": lambda _: _format_docs(docs), "question": RunnablePassthrough()}
        | PROMPT
        | llm
        | StrOutputParser()
    )

    answer = chain.invoke(question)
    sources = list({doc.metadata.get("filename", "unknown") for doc in docs})

    return {"question": question, "answer": answer, "sources": sources}


def list_documents(username: str) -> dict:
    return {k: v for k, v in _load_meta().items() if v["username"] == username}


def delete_document(doc_id: str, username: str):
    meta = _load_meta()
    if doc_id not in meta:
        raise HTTPException(status_code=404, detail="Document not found")
    if meta[doc_id]["username"] != username:
        raise HTTPException(status_code=403, detail="Access denied")

    _get_vectorstore()._collection.delete(where={"doc_id": doc_id})

    for f in UPLOAD_DIR.glob(f"{doc_id}_*"):
        f.unlink()

    del meta[doc_id]
    _save_meta(meta)
    return {"message": "Document deleted successfully"}
