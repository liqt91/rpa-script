"""后端 handler — 每个文件定义 handler（注册 + 实现）"""
from .set_var import SetVarHandler
from .log import LogHandler
from .open_browser import OpenBrowserHandler
from .append_to_list import AppendToListHandler
from .increment import IncrementHandler
from .sleep import SleepHandler
from .random_sleep import RandomSleepHandler
from .dicts import SetDictValueHandler, GetDictValueHandler, RemoveDictKeyHandler, StringConcatHandler
from .custom import CustomHandler
from .data_handlers import HttpRequestHandler, WriteTableRowHandler, ReadTableCellHandler, WriteTableCellHandler, GetTableRowCountHandler
