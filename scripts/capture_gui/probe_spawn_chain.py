"""模拟后端 spawn 捕获子进程的完整链路: .venv python -> sys.executable -> 子进程。
验证子进程里 uiautomation 是否可用, 以及 sys.executable 解析成什么。
"""
import subprocess
import sys
import os

code = (
    "import sys, os; "
    "print('CHILD sys.executable:', sys.executable); "
    "print('CHILD has __PYVENV_LAUNCHER__:', '__PYVENV_LAUNCHER__' in os.environ); "
    "try:\n"
    "    import uiautomation; print('CHILD uiautomation: OK', uiautomation.VERSION)\n"
    "except Exception as e:\n"
    "    print('CHILD uiautomation: FAIL', repr(e))"
)

print("PARENT sys.executable:", sys.executable)
print("PARENT has __PYVENV_LAUNCHER__:", "__PYVENV_LAUNCHER__" in os.environ)
print("--- spawning via sys.executable (like commands_router) ---")
r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print(r.stdout)
if r.stderr.strip():
    print("CHILD stderr:", r.stderr[:500])
print("returncode:", r.returncode)
