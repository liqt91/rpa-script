"""
数据库模型
"""

import uuid as _uuid
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from src.config import settings as config
from src.config.utils import utcnow

_sqlite_args = {"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {}
engine = create_engine(config.DATABASE_URL, connect_args=_sqlite_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    is_admin = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id = Column(String(64), primary_key=True)
    hostname = Column(String(128))
    ip = Column(String(45))
    os = Column(String(64))
    version = Column(String(32))
    status = Column(String(16), default="offline")  # online / offline
    last_heartbeat = Column(DateTime)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(64), nullable=False)
    url = Column(Text, nullable=False)
    params = Column(Text)  # JSON
    status = Column(String(16), default="pending")  # pending / running / done / failed
    client_id = Column(String(64))
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Result(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=True, index=True)
    run_id = Column(String(64), default="", index=True)
    url = Column(Text)
    total = Column(Integer, default=0)
    data = Column(Text)  # JSON
    extract_time = Column(DateTime, default=utcnow)
    client_id = Column(String(64))
    trigger_type = Column(String(16), default="manual")  # manual / scheduled
    log_dir = Column(Text, default="")  # 本地日志目录路径
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    task = relationship("Task", foreign_keys=[task_id])
    workflow = relationship("Workflow", foreign_keys=[workflow_id])


class AIAppConfig(Base):
    __tablename__ = "ai_app_configs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    api_key = Column(String(256), default="")
    app_type = Column(String(16), default="chat")
    input_schema = Column(Text, default="{}")  # inputs 字段校验规则 {"field": {"type": "array", "required": true}}
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = {"sqlite_autoincrement": True}
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(32), unique=True, nullable=False, default=lambda: _uuid.uuid4().hex)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    url = Column(Text, default="")          # 目标页面 URL
    framework = Column(String(32), default="DrissionPage")
    target_browser = Column(String(16), default="")  # chrome / edge / ""=任意
    parameters = Column(Text, default="[]")  # JSON: [{name, label, type, default, direction}]
    api_enabled = Column(Integer, default=0)   # 0=disabled, 1=enabled
    api_key = Column(String(32), default="")   # API access key
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    nodes = relationship("WorkflowNode", back_populates="workflow",
                         cascade="all, delete-orphan",
                         order_by="WorkflowNode.order")
    data_tables = relationship("DataTable", back_populates="workflow",
                               cascade="all, delete-orphan")
    elements = relationship("WorkflowElement", back_populates="workflow",
                            cascade="all, delete-orphan")


class DataTable(Base):
    __tablename__ = "data_tables"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    columns = Column(Text, default='[]')   # JSON: [{"name": "A", "type": "text"}, ...]
    rows = Column(Text, default='[]')      # JSON: [{"A": "v1", "B": "v2"}, ...]
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    workflow = relationship("Workflow", back_populates="data_tables")


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("workflow_nodes.id"), nullable=True)  # 嵌套: forEach/if body
    order = Column(Integer, default=0)
    # node types: click|input|getText|hover|getAttr|findWithin|waitFor|forEach|if|else|endFor|endIf|custom
    type = Column(String(32), nullable=False)
    action = Column(String(32), nullable=True)
    element_name = Column(String(128), nullable=True)  # 引用 workflow_elements.name
    extra = Column(Text, default="{}")        # JSON: {text, attrName, subSelector, seconds, description}
    enabled = Column(Integer, default=1)       # 1=启用 0=禁用（执行时跳过）
    created_at = Column(DateTime, default=utcnow)
    workflow = relationship("Workflow", back_populates="nodes")
    parent = relationship("WorkflowNode", remote_side="WorkflowNode.id", backref="children")


class WorkflowElement(Base):
    __tablename__ = "workflow_elements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    target_mode = Column(String(16), default="single")   # single | list
    css_candidates = Column(Text, default="[]")          # JSON
    xpath_candidates = Column(Text, default="[]")        # JSON
    drission_candidates = Column(Text, default="[]")     # JSON
    web_selector = Column(Text, default="")              # css/xpath，供扩展执行用
    drission_selector = Column(Text, default="")         # 供 Python 导出用
    element_kind = Column(String(16), default="plain")   # plain | anchor | child
    relative_selector = Column(Text, default="")         # 相对最近重复祖先(循环项)的选择器，带 css:/xpath:/drission: 前缀；空=未锚定
    anchor_selector = Column(Text, default="")           # 该重复祖先(循环项)自身的选择器
    anchor_element_name = Column(String(128), nullable=True)  # 显式关联的锚点元素名（同流程唯一）
    anchor_mode = Column(String(16), default="none")     # none=无锚点 / anchor-first=系统根据 activeAnchor 生成 / manual=用户手动编辑
    dom_path = Column(Text, default="[]")                # JSON: DOM path hierarchy
    attributes = Column(Text, default="{}")              # JSON: 元素属性
    screenshot = Column(Text)                              # base64 dataURL
    page_url = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    workflow = relationship("Workflow", back_populates="elements")

    __table_args__ = (
        UniqueConstraint("workflow_id", "name", name="uq_workflow_element_name"),
    )


class WorkflowCommand(Base):
    __tablename__ = "workflow_commands"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(32), unique=True, nullable=False)
    label = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)
    icon = Column(String(32), default="fa-circle")
    icon_color = Column(String(16), default="text-gray-500")
    bg_color = Column(String(16), default="bg-gray-50")
    is_container = Column(Integer, default=0)
    is_branch = Column(Integer, default=0)
    is_structural = Column(Integer, default=0)
    closes_with = Column(String(32), nullable=True)  # 容器指令的闭合标记，如 forEachElement -> endFor
    fields = Column(Text, default="[]")
    description = Column(Text, default="")         # 指令说明，在编辑器中展示
    handler = Column(String(32), nullable=True)    # content.js handler name
    local = Column(Integer, default=0)             # 1 = local execution (backend), 0 = send to extension
    is_builtin = Column(Integer, default=0)
    enabled = Column(Integer, default=1)
    category_order = Column(Integer, default=0)
    command_order = Column(Integer, default=0)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
