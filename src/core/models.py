from __future__ import annotations
import time
from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# 4 actions as per requirements
class ActionEnum(str, Enum):
    ASK = "ask"
    INSTRUCT = "instruct"
    RESOLVED = "resolved"
    ESCALATE = "escalate"


class ConfirmationType(str, Enum):
    FACTORY_RESET = "factory_reset"

# Must have citation
class Citation(BaseModel):
    source_id: str = Field(description="Document slug matching manifest ID or filename stem")
    locator: str = Field(description="Exact section heading or subsection locator")


class ResponseEnvelope(BaseModel):
    response: str = Field(description="One diagnostic question, safe step, resolution, or escalation message")
    citations: List[Citation] = Field(default_factory=list, description="Grounding citations from corpus")
    action: ActionEnum = Field(description="Conversation action state")


class ChunkMetadata(BaseModel):
    chunk_id: str
    source_id: str
    doc_title: str
    locator: str
    product_line: Optional[str] = None
    is_archived: bool = False
    effective_date: Optional[str] = None
    version: Optional[str] = None
    header_path: List[str] = Field(default_factory=list)
    sha256: str


class DocumentChunk(BaseModel):
    text: str
    metadata: ChunkMetadata


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: float = Field(default_factory=time.time)


class SessionState(BaseModel):
    session_id: str
    identified_model: Optional[str] = None
    attempted_steps: List[str] = Field(default_factory=list)
    pending_confirmation: Optional[str] = None
    dialogue_window: List[ChatMessage] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    reported_issue: Optional[str] = None
    confirmed_facts: Dict[str, Any] = Field(default_factory=dict)
    turns_count: int = 0
    is_escalated: bool = False
    is_resolved: bool = False

    @property
    def history(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.dialogue_window]


DiagnosticSession = SessionState
