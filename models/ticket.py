from typing import List, Optional
from pydantic import BaseModel, Field


class TicketDraft(BaseModel):
    summary: str
    description: Optional[str] = None
    issuetype: str = Field(default="Feature Task")
    assignee: Optional[str] = None
    components: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    fix_versions: List[str] = Field(default_factory=list)
    due_date: Optional[str] = None
    expected_release_date: Optional[str] = None
    system_prefixes: List[str] = Field(default_factory=list)  # 例如 ['WP', 'NGS']
    sprint_id: Optional[int] = None  # Sprint ID for the ticket
    original_estimate: Optional[str] = None


class TicketPlan(BaseModel):
    story: Optional[TicketDraft] = None  # None for Bug tickets
    tasks: List[TicketDraft] = Field(default_factory=list)
    intent_type: str = Field(default="feature")  # "feature", "bug", or "add_task"
    parent_story_key: Optional[str] = None  # 既有 Story 的 Key (補建 Task 模式)


class TicketCreated(BaseModel):
    key: str
    summary: str
    link: str
