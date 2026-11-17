import sys
sys.dont_write_bytecode = True

from modules.app_core import create_app

# 必须写成单个 Name 赋值：Vercel 的 @vercel/python 是用 AST 静态分析找顶层入口的，
# 元组解包（app, _ = ...）的赋值目标是 ast.Tuple，它认不出来，会直接报
# "Could not find a top-level app, application, or handler in app.py"。
app = create_app(mode='vercel')[0]