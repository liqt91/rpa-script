"""
Pydantic schemas
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any
from datetime import datetime


# ====== Auth ======
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


# ====== Scripts / Job Metadata ======
class ParamConstraint(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    choices: Optional[list] = None


class ScriptParam(BaseModel):
    type: str
    description: str = ""
    default: Optional[Any] = None
    required: bool = False
    constraints: Optional[ParamConstraint] = None


class ScriptMeta(BaseModel):
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    main: str = "main.py"
    params: dict[str, ScriptParam] = Field(default_factory=dict)
    min_client_version: str = "0.0.0"
    enabled: bool = True
    requirements_file: str = "requirements.txt"
    requirements: list[str] = Field(default_factory=list)


class ScriptDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


# ====== Tasks ======
class TaskCreate(BaseModel):
    job_type: str
    urls: list[str]
    params: Optional[dict] = None
    client_id: Optional[str] = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: str
    url: str
    params: Optional[dict] = None
    status: str
    client_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ====== Results ======
class ResultUpload(BaseModel):
    task_id: Optional[int] = None
    url: str
    total: int
    data: dict
    client_id: Optional[str] = None
    extract_time: Optional[str] = None


# ====== Clients ======
class ClientHeartbeat(BaseModel):
    client_id: str
    hostname: Optional[str] = None
    ip: Optional[str] = None
    os: Optional[str] = None
    status: str = "idle"
    version: Optional[str] = None


class ClientRegister(BaseModel):
    hostname: str
    ip: str
    os: str


# ====== AI ======
class AIInvokeRequest(BaseModel):
    """Dify 透传请求。payload 为原始 Dify 请求体，服务端只做校验 + 加 appkey + 转发。"""
    capability: str  # AI 能力标识，如 sentiment
    payload: dict    # Dify 原始请求体


class InputFieldSchema(BaseModel):
    type: str = "string"  # string / integer / float / boolean / array / object
    required: bool = False
    description: str = ""


class AIAppConfigIn(BaseModel):
    type: str
    name: str
    api_key: str = ""
    app_type: str = "chat"  # text / chat / agent / chatflow / workflow
    input_schema: dict[str, InputFieldSchema] = Field(default_factory=dict)
    enabled: bool = True


# ====== Workflows ======
class WorkflowNodeIn(BaseModel):
    id: Optional[int] = None
    parent_id: Optional[int] = None
    order: int = 0
    type: str
    locator: Optional[str] = None
    locator_type: Optional[str] = None
    method: Optional[str] = "ele"
    action: Optional[str] = None
    element_id: Optional[int] = None
    extra: Optional[dict] = Field(default_factory=dict)


class WorkflowNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    parent_id: Optional[int] = None
    order: int
    type: str
    locator: Optional[str] = None
    locator_type: Optional[str] = None
    method: Optional[str] = None
    action: Optional[str] = None
    element_id: Optional[int] = None
    extra: Optional[dict] = None


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    url: str = ""
    framework: str = "DrissionPage"


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    framework: Optional[str] = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    description: str = ""
    url: str = ""
    framework: str = "DrissionPage"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    nodes: list[WorkflowNodeOut] = Field(default_factory=list)


class WorkflowListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    description: str = ""
    url: str = ""
    framework: str = "DrissionPage"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ====== Captured Elements ======
class CapturedElementIn(BaseModel):
    name: str
    description: str = ""
    locator: str
    locator_type: str = "css"
    method: str = "ele"
    candidates: list = Field(default_factory=list)
    features: dict = Field(default_factory=dict)
    css_selector: Optional[str] = None
    tag: Optional[str] = None
    text_preview: Optional[str] = None
    page_url: Optional[str] = None
    hostname: str
    screenshot: Optional[str] = None


class CapturedElementUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CapturedElementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    description: str = ""
    locator: str
    locator_type: str = "css"
    method: str = "ele"
    candidates: Optional[list] = None
    features: Optional[dict] = None
    css_selector: Optional[str] = None
    tag: Optional[str] = None
    text_preview: Optional[str] = None
    page_url: Optional[str] = None
    hostname: str
    screenshot: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
