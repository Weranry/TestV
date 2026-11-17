import sys
import os

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules.run_core import run_server

if __name__ == '__main__':
    if '-prod' in sys.argv:
        mode = 'prod'
    else:
        mode = 'dev'

    if '-help' in sys.argv or '-h' in sys.argv:
        print('用法: python -B run.py [-prod]')
        print('  (无参数)  开发模式（默认），跳过鉴权，启用缓存和管理面板')
        print('  -prod   生产模式，启用鉴权、缓存和管理面板')
        sys.exit(0)

    run_server(mode)