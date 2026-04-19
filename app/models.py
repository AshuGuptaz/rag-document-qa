from pydantic import BaseModel
from typing import Optional


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class AskQuestion(BaseModel):
    question: str
    document_id: Optional[str] = None
