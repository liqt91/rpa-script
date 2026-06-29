"""
服务端配置
"""

import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    _data_dir = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "data")
    os.makedirs(_data_dir, exist_ok=True)
    DATABASE_URL = f"sqlite:///{os.path.join(_data_dir, 'data.db')}"

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(days=365*10)  # 单机应用：10 年免登录

# 脚本仓库
# 支持打包后通过环境变量指定，否则自动推导
REPO_DIR = os.environ.get("RPA_REPO_ROOT", os.path.join(os.path.dirname(BASE_DIR)))
JOBS_DIR = os.path.join(REPO_DIR, "service", "jobs")
VERSION_FILE = os.path.join(os.path.dirname(REPO_DIR), "VERSION")

# AI: Dify 配置（替换原有 OpenAI 配置）
# 每个 capability 对应独立的应用；所有密钥与地址均通过环境变量配置
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "")

# 每个分析能力独立配置：api_key, app_type, input_schema
# app_type: chat | agent | text | chatflow | workflow
# endpoint 由 app_type 自动推导，无需配置
# input_schema: inputs 字段校验规则 {"field": {"type": "array", "required": true, "description": "..."}}
# 注：启动时 lifespan 会将此默认值同步到数据库，之后以数据库为准
DIFY_APPS = {
    "sentiment": {
        "name": "情感分析",
        "api_key": os.getenv("DIFY_SENTIMENT_KEY", ""),
        "app_type": os.getenv("DIFY_SENTIMENT_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
        },
    },
    "stance": {
        "name": "倾向判断",
        "api_key": os.getenv("DIFY_STANCE_KEY", ""),
        "app_type": os.getenv("DIFY_STANCE_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
        },
    },
    "summary": {
        "name": "摘要提取",
        "api_key": os.getenv("DIFY_SUMMARY_KEY", ""),
        "app_type": os.getenv("DIFY_SUMMARY_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
        },
    },
    "topics": {
        "name": "话题聚类",
        "api_key": os.getenv("DIFY_TOPICS_KEY", ""),
        "app_type": os.getenv("DIFY_TOPICS_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
        },
    },
    "comment_analysis": {
        "name": "评论区讨论对象识别",
        "api_key": os.getenv("DIFY_COMMENT_ANALYSIS_KEY", ""),
        "app_type": os.getenv("DIFY_COMMENT_ANALYSIS_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
            "heavy_users": {"type": "array", "required": False, "description": "活跃作者"},
        },
    },
    "comment_analysis_jingpin": {
        "name": "评论区竞品分析",
        "api_key": os.getenv("DIFY_COMMENT_ANALYSIS_JINGPIN_KEY", ""),
        "app_type": os.getenv("DIFY_COMMENT_ANALYSIS_JINGPIN_TYPE", "chat"),
        "input_schema": {
            "comments": {"type": "array", "required": True, "description": "评论列表"},
        },
    },
}

# 兼容性：保留 OpenAI 配置（可选，若 dify 未配置可作为 fallback）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_DEFAULT_MODEL = os.getenv("AI_DEFAULT_MODEL", "gpt-4o-mini")

# 更新检查：Gitea 仓库（公开 releases 即可，无需 token）
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "")
GITEA_REPO_OWNER = os.getenv("GITEA_REPO_OWNER", "")
GITEA_REPO_NAME = os.getenv("GITEA_REPO_NAME", "")

# 服务端
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
