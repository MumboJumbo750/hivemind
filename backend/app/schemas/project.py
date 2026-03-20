import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.services.onboarding_templates import DEFAULT_ONBOARDING_DENY_PATTERNS, DEFAULT_ONBOARDING_PORT


WorkspaceMode = Literal["read_only", "read_write"]
OnboardingStatus = Literal["pending", "ready", "error"]
IntegrationProvider = Literal["youtrack", "sentry", "in_app", "github_projects"]
IntegrationStatus = Literal["active", "incomplete", "error", "disabled"]
ThreadPolicy = Literal["stateless", "attempt_stateful", "epic_stateful", "project_stateful"]


class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    repo_host_path: Optional[str] = None
    workspace_root: Optional[str] = None
    workspace_mode: Optional[WorkspaceMode] = None
    onboarding_status: Optional[OnboardingStatus] = None
    default_branch: Optional[str] = None
    remote_url: Optional[str] = None
    detected_stack: Optional[list[str]] = Field(default=None)
    agent_thread_overrides: Optional[dict[str, ThreadPolicy]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repo_host_path: Optional[str] = None
    workspace_root: Optional[str] = None
    workspace_mode: Optional[WorkspaceMode] = None
    onboarding_status: Optional[OnboardingStatus] = None
    default_branch: Optional[str] = None
    remote_url: Optional[str] = None
    detected_stack: Optional[list[str]] = Field(default=None)
    agent_thread_overrides: Optional[dict[str, ThreadPolicy]] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    repo_host_path: Optional[str]
    workspace_root: Optional[str]
    workspace_mode: Optional[WorkspaceMode]
    onboarding_status: Optional[OnboardingStatus]
    default_branch: Optional[str]
    remote_url: Optional[str]
    detected_stack: Optional[list[str]]
    agent_thread_overrides: Optional[dict[str, ThreadPolicy]]
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str = "developer"


class ProjectMemberResponse(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    username: str | None = None

    model_config = {"from_attributes": True}


class ProjectOnboardingRequest(BaseModel):
    port: int = DEFAULT_ONBOARDING_PORT
    container_path: str = "/workspace"
    deny_patterns: str = DEFAULT_ONBOARDING_DENY_PATTERNS


class ProjectOnboardingFile(BaseModel):
    path: str
    location: str
    writable: bool
    content: str


class ProjectOnboardingPreviewResponse(BaseModel):
    project_id: str
    project_slug: str
    repo_host_path: str
    container_path: str
    workspace_mode: Optional[WorkspaceMode]
    repo_accessible: bool
    repo_is_git_repo: bool
    detected_stack: list[str]
    requires_restart: bool
    warnings: list[str]
    files: list[ProjectOnboardingFile]
    next_steps: list[str]


class ProjectOnboardingApplyResponse(BaseModel):
    project_id: str
    status: Optional[OnboardingStatus]
    applied_files: list[str]
    pending_files: list[str]
    requires_restart: bool
    message: str


class ProjectOnboardingStatusResponse(BaseModel):
    project_id: str
    status: Optional[OnboardingStatus]
    repo_host_path: Optional[str]
    workspace_root: Optional[str]
    runtime_workspace_root: str
    runtime_workspace_accessible: bool
    detected_stack: list[str]
    deny_patterns: list[str]


class ProjectOnboardingVerifyResponse(BaseModel):
    project_id: str
    status: Optional[OnboardingStatus]
    workspace_root: str
    workspace_accessible: bool
    detected_stack: list[str]
    warnings: list[str]
    message: str


class ProjectIntegrationBase(BaseModel):
    display_name: Optional[str] = None
    integration_key: Optional[str] = None
    base_url: Optional[str] = None
    external_project_key: Optional[str] = None
    project_selector: Optional[dict[str, object]] = None
    status_mapping: Optional[dict[str, object]] = None
    routing_hints: Optional[dict[str, object]] = None
    config: Optional[dict[str, object]] = None
    webhook_secret: Optional[str] = None
    access_token: Optional[str] = None
    sync_enabled: bool = True
    sync_direction: str = "bidirectional"
    github_repo: Optional[str] = None
    github_project_id: Optional[str] = None
    status_field_id: Optional[str] = None
    priority_field_id: Optional[str] = None


class ProjectIntegrationCreate(ProjectIntegrationBase):
    provider: IntegrationProvider


class ProjectIntegrationUpdate(ProjectIntegrationBase):
    pass


class ProjectIntegrationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    provider: IntegrationProvider
    display_name: Optional[str]
    integration_key: Optional[str]
    base_url: Optional[str]
    external_project_key: Optional[str]
    project_selector: Optional[dict[str, object]]
    status_mapping: Optional[dict[str, object]]
    routing_hints: Optional[dict[str, object]]
    config: Optional[dict[str, object]]
    sync_enabled: bool
    sync_direction: str
    github_repo: Optional[str]
    github_project_id: Optional[str]
    status_field_id: Optional[str]
    priority_field_id: Optional[str]
    has_webhook_secret: bool
    has_access_token: bool
    status: IntegrationStatus
    status_detail: str
    last_health_state: Optional[str]
    last_health_detail: Optional[str]
    health_checked_at: Optional[datetime]
    last_event_at: Optional[datetime]
    last_error_at: Optional[datetime]
    last_error_detail: Optional[str]
    created_at: datetime
    updated_at: datetime
