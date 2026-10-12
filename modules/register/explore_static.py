"""把访客导航页 `/explore` 预渲染成静态文件 `public/pages/explore.html`。

为什么要有这个生成步骤：Vercel 侧不注册 `/explore` 端点（`app_core` 只在 is_local 分支挂
它），那条链路由 `vercel.json` 把 `/explore` 直接指向 `public/pages/explore.html`，和首页
`public/pages/index.html` 同一套路——走边缘静态直出，不经过 Serverless 函数、零冷启动。

什么时候必须重跑：只要插件目录的形态变了，这一页的内容就变了——新增/删除插件、改
`plugin.json`、增删视图种类（可选尺寸列在路由下面）、改 `plugin_config.py` 的 DEFAULT_ARGS
（参数名列表）。改完按提示重跑一次并把生成的文件一起提交即可。

    python -B -m modules.register.explore_static

**不需要手动记这件事**：本地服务（`run_core.run_server`）每次启动时会自动跑一次
`--if-stale`（见 `refresh_static_explore`），所以只要发布前起过一次服务，仓库里那份就已经
是最新的了。CI 侧由 `ExploreStaticPageTest` 断言「提交的文件 == 生成器当前输出」，真漏了
会在测试阶段直接变红。手动命令仍然保留，用于「不想起服务、只想刷这一页」的场合。

为什么不是 Vercel 构建期自动跑：本仓库用的是 `vercel.json` 的 `builds`（legacy）写法，
Vercel 对带 `builds` 的项目会**整体忽略 Build Command 与项目设置里的构建配置**，因此平台
侧没有可以挂脚本的钩子。要改成构建期自动生成，得把配置迁到 `functions` 写法并把入口挪到
`api/`，那是另一件事（会动到函数打包方式，未经验证不轻易改）。

生成环境与线上环境的差异（体现在这一页上的）：
  * 「可用用户组」整行不渲染。它的数据源是**运行实例自己的库**，而静态页是在构建机上生成的，
    写死一份名单只会是一份对不上任何人库的快照。见 `build_explore_html(include_groups=False)`。
  * 顶栏的「登录」入口被摘掉（`login-entry` 锚点块）：Vercel 上没有 `/login`，留着就是死链。
  * 语言在生成时定死（静态文件没法按请求头取词），默认英文，与首页静态版口径一致；
    要换语言用 `--lang zh-CN`。
"""
import argparse
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'public', 'pages', 'explore.html')

# 只存在于本地链路的锚点块：生成静态版时整块（含锚点）去掉
_LOCAL_ONLY_BLOCK_RE = re.compile(
    r'<!--\s*(?P<name>[a-z][a-z0-9-]*):start\s*-->.*?<!--\s*(?P=name):end\s*-->', re.S)
_LOCAL_ONLY_BLOCKS = ('login-entry',)


class _StaticRequest:
    """只带 `build_explore_html` 真正用到的那两样：`app.state` 与 `headers`

    不造完整 Request：这里要的是「渲染结果」，与请求生命周期无关，造得越像越容易在
    某天被别人的中间件/属性访问绊住。
    """

    def __init__(self, app, accept_language):
        self.app = app
        self.headers = {'accept-language': accept_language}


def _strip_local_blocks(html):
    def _repl(match):
        return '' if match.group('name') in _LOCAL_ONLY_BLOCKS else match.group(0)
    return _LOCAL_ONLY_BLOCK_RE.sub(_repl, html)


def build_static_html(lang='en'):
    """→ 静态版 `/explore` 的完整 HTML（取词与共享 UI 都已落定）"""
    from modules.i18n.registry import current_lang
    from modules.admin_ui.panel_render import panel_html
    from modules.register.explore_routes import build_explore_html

    # 用 vercel 模式建一次 app：它会跑 register_plugins，把 plugin_result / plugin_states /
    # plugin_routes 填好——正是 build_explore_html 要读的那几份 state。数据库在这一模式下
    # 被停用，与部署环境一致；插件出图本身不依赖库，清单与路由都照常读得到。
    from modules.app_core import create_app
    app = create_app(mode='vercel')[0]

    lang = current_lang(lang)
    inner = build_explore_html(_StaticRequest(app, lang), include_groups=False)
    # 与运行时同一个出口渲染：取词、共享 UI 注入、语言包注入都只有这一处口径，
    # 生成版与线上版才不会出现「某个标记没被替换」这类只有一版才有的差异
    body = panel_html(inner, lang).body.decode('utf-8')
    return _strip_local_blocks(body)


def _write(html):
    """写盘；内容与现有文件**逐字节一致时不碰盘**——启动钩子每次开机都会调到这里，
    没变化还去重写一遍只会刷 mtime、让编辑器与构建工具误以为文件动过。→ 是否真的写了"""
    if _read_current() == html:
        return False
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8', newline='') as f:
        f.write(html)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='生成静态版访客导航页 public/pages/explore.html')
    parser.add_argument('--lang', default='en', help='页面语言，默认 en（与首页静态版一致）')
    parser.add_argument('--check', action='store_true',
                        help='只比对生成结果与磁盘上的文件是否一致，不写入（供测试用）')
    parser.add_argument('--if-stale', action='store_true',
                        help='只在内容确实有变化时写盘并输出，未变化时静默退出'
                             '（供本地服务启动时自动刷新用，见 run_core.refresh_static_explore）')
    args = parser.parse_args(argv)

    html = build_static_html(args.lang)
    if args.check:
        return 0 if _read_current() == html else 1

    changed = _write(html)
    if not changed and args.if_stale:
        # 启动钩子的正常路径：没变化就一个字都不输出（终端静默，见 rules 的启动输出约定）
        return 0
    if changed:
        sys.stdout.write('%s 已生成（%s，%d 字节）\n'
                         % (os.path.relpath(OUTPUT_PATH, PROJECT_ROOT), args.lang,
                            len(html.encode('utf-8'))))
    else:
        sys.stdout.write('%s 已是最新，无需改动\n' % os.path.relpath(OUTPUT_PATH, PROJECT_ROOT))
    return 0


def _read_current():
    try:
        with open(OUTPUT_PATH, 'r', encoding='utf-8', newline='') as f:
            return f.read()
    except FileNotFoundError:
        return None


if __name__ == '__main__':
    sys.exit(main())
