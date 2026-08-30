from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

WorkspaceRole = Literal["owner", "editor", "viewer"]


class AuthenticatedUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str] = None
    auth_provider: str
    auth_subject: Optional[str] = None
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceSummaryResponse(BaseModel):
    id: UUID
    name: str
    slug: Optional[str] = None
    owner_user_id: UUID
    is_personal: bool
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceMembershipResponse(BaseModel):
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    invited_by_user_id: Optional[UUID] = None
    joined_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AuthBootstrapResponse(BaseModel):
    user: AuthenticatedUserResponse
    workspace: WorkspaceSummaryResponse
    membership: WorkspaceMembershipResponse
    bootstrap_completed: bool = Field(
        default=True,
        description="True when the user and default workspace context are ready for use.",
    )
