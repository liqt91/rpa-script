"""Handler 系统入口 — import 本包即注册所有 handler。"""
from .backend import *       # 后端 handler（注册 + 实现）
from .extension._manifest import *  # 扩展 handler（声明，实现归 content.js）
# emitters 待从 extension_emitter.py 迁移
