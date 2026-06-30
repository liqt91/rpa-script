"""
Pydantic schemas
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Any
from datetime import datetime
import json


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


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: Optional[int] = None
    run_id: str = ""
    url: str = ""
    total: int = 0
    data: Optional[dict] = None
    extract_time: Optional[datetime] = None
    trigger_type: str = "manual"
    log_dir: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


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
    action: Optional[str] = None
    element_name: Optional[str] = None
    enabled: Optional[int] = 1
    extra: Optional[dict] = Field(default_factory=dict)


class WorkflowNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    parent_id: Optional[int] = None
    order: int
    type: str
    action: Optional[str] = None
    element_name: Optional[str] = None
    enabled: Optional[int] = None
    extra: Optional[dict] = None


class WorkflowParameter(BaseModel):
    name: str
    label: str = ""
    type: str = "text"  # text | number | bool | select
    options: Optional[list] = None  # for select
    default: Any = None


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    url: str = ""
    framework: str = "DrissionPage"
    parameters: list[WorkflowParameter] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    framework: Optional[str] = None
    parameters: Optional[list[WorkflowParameter]] = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    description: str = ""
    url: str = ""
    framework: str = "DrissionPage"
    parameters: Optional[list] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    nodes: list[WorkflowNodeOut] = Field(default_factory=list)

    @field_validator("parameters", mode="before")
    @classmethod
    def _parse_parameters(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            try:
                return json.loads(v or "[]")
            except Exception:
                return []
        return v


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


# ====== Workflow Elements ======
class WorkflowElementIn(BaseModel):
    name: str
    target_mode: str = "single"
    css_candidates: list = Field(default_factory=list)
    xpath_candidates: list = Field(default_factory=list)
    drission_candidates: list = Field(default_factory=list)
    web_selector: str = ""
    drission_selector: str = ""
    dom_path: list = Field(default_factory=list)
    attributes: dict = Field(default_factory=dict)
    screenshot: Optional[str] = None
    page_url: Optional[str] = None


class WorkflowElementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    name: str
    target_mode: str = "single"
    css_candidates: Optional[list] = None
    xpath_candidates: Optional[list] = None
    drission_candidates: Optional[list] = None
    web_selector: str = ""
    drission_selector: str = ""
    dom_path: Optional[list] = None
    attributes: Optional[dict] = None
    screenshot: Optional[str] = None
    page_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ====== Data Tables ======
class DataTableColumn(BaseModel):
    name: str
    type: str = "text"


class DataTableIn(BaseModel):
    name: str
    columns: list[DataTableColumn] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)


class DataTableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    name: str
    columns: Optional[list] = None
    rows: Optional[list] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
