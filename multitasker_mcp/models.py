from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RepoSpec(BaseModel):
    url: str = Field(description="Git URL (https or ssh)")
    ref: str | None = Field(default=None, description="Optional ref/branch/tag to base from")


ModelFamily = Literal["opus", "gpt", "codex", "gemini"]
AgentCli = Literal["copilot", "codex", "claude"]


class AgentSpec(BaseModel):
    cli: AgentCli = "copilot"
    model_family: ModelFamily | None = Field(
        default=None,
        description="Only for copilot; picks the most recent configured model in that family.",
    )


class TaskSpec(BaseModel):
    goal: str
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    context: str | None = None


class PRSpec(BaseModel):
    create: bool = True
    base: str | None = None
    title: str | None = None
    body: str | None = None


class MergeSpec(BaseModel):
    auto: bool = False
    method: Literal["merge", "squash", "rebase"] = "squash"
    require_checks: bool = True
    require_reviews: bool = False


class RunRequest(BaseModel):
    repo: RepoSpec
    task: TaskSpec
    agent: AgentSpec = Field(default_factory=AgentSpec)
    pr: PRSpec = Field(default_factory=PRSpec)
    merge: MergeSpec = Field(default_factory=MergeSpec)


class RunResponse(BaseModel):
    run_id: str


class StatusRequest(BaseModel):
    run_id: str


class TailLogsRequest(BaseModel):
    run_id: str
    lines: int = 200


class AnswerQuestionRequest(BaseModel):
    run_id: str
    question_id: str
    answer: str
