"""
数据库模型
"""

import uuid as _uuid
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from src.config import settings as config
from src.config.utils import utcnow

engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {})
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
    url = Column(Text)
    total = Column(Integer, default=0)
    data = Column(Text)  # JSON
    extract_time = Column(DateTime, default=utcnow)
    client_id = Column(String(64))
    task = relationship("Task", foreign_keys=[task_id])


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
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(32), unique=True, nullable=False, default=lambda: _uuid.uuid4().hex)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    url = Column(Text, default="")          # 目标页面 URL
    framework = Column(String(32), default="DrissionPage")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    nodes = relationship("WorkflowNode", back_populates="workflow",
                         cascade="all, delete-orphan",
                         order_by="WorkflowNode.order")


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("workflow_nodes.id"), nullable=True)  # 嵌套: forEach/if body
    order = Column(Integer, default=0)
    type = Column(String(32), nullable=False)   # click|input|getText|hover|getAttr|findWithin|waitFor|forEach|if|else|endFor|endIf|custom
    locator = Column(Text, nullable=True)
    locator_type = Column(String(16), nullable=True)  # css|id|class|xpath|text|data-attr|tag_text|...
    method = Column(String(16), nullable=True)        # ele|eles|s_ele|s_eles
    action = Column(String(32), nullable=True)
    element_id = Column(Integer, ForeignKey("captured_elements.id"), nullable=True)  # 关联元素库
    extra = Column(Text, default="{}")        # JSON: {text, attrName, subSelector, seconds, description}
    created_at = Column(DateTime, default=utcnow)
    workflow = relationship("Workflow", back_populates="nodes")
    parent = relationship("WorkflowNode", remote_side="WorkflowNode.id", backref="children")


class CapturedElement(Base):
    __tablename__ = "captured_elements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    locator = Column(Text, nullable=False)
    locator_type = Column(String(16), default="css")
    method = Column(String(16), default="ele")
    candidates = Column(Text, default="[]")    # JSON
    features = Column(Text, default="{}")      # JSON
    css_selector = Column(Text)
    tag = Column(String(32))
    text_preview = Column(String(128))
    page_url = Column(Text)
    hostname = Column(String(128), nullable=False, index=True)
    screenshot = Column(Text)    # base64 dataURL
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    user = relationship("User")


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
    fields = Column(Text, default="[]")
    is_builtin = Column(Integer, default=0)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
