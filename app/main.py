from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import UserRegister, UserLogin, AskQuestion
from app.auth import register_user, login_user, get_current_user
from app import rag

app = FastAPI(
    title="RAG Document Q&A API",
    description="Upload PDFs and ask questions using AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "running", "message": "RAG Document Q&A API", "version": "1.0.0"}


# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.post("/auth/register", tags=["Auth"])
def register(user: UserRegister):
    return register_user(user.username, user.password)


@app.post("/auth/login", tags=["Auth"])
def login(user: UserLogin):
    return login_user(user.username, user.password)


# ── DOCUMENTS ─────────────────────────────────────────────────────────────────

@app.post("/documents/upload", tags=["Documents"])
async def upload(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

    return rag.process_document(file_bytes, file.filename, username)


@app.get("/documents", tags=["Documents"])
def get_documents(username: str = Depends(get_current_user)):
    return rag.list_documents(username)


@app.delete("/documents/{doc_id}", tags=["Documents"])
def delete(doc_id: str, username: str = Depends(get_current_user)):
    return rag.delete_document(doc_id, username)


# ── CHAT ──────────────────────────────────────────────────────────────────────

@app.post("/chat/ask", tags=["Chat"])
def ask(body: AskQuestion, username: str = Depends(get_current_user)):
    return rag.ask_question(body.question, username, body.document_id)
