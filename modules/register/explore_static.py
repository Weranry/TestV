"""把访客导航页 `/explore` 预渲染成静态文件 `public/pages/explore.html`。

为什么要有这个生成步骤：Vercel 侧不注册 `/explore` 端点（`app_core` 只在 is_local 分支挂
它），那条链路由 `vercel.json` 的 `rewrites` 把 `/explore` 指向静态页，和首页
`public/pages/index.html` 同一套路——走边缘静态直出，不经过 Serverless 函数、零冷启动。
（`public/**` 经 Vercel 的 CDN 发布后前缀被摘掉：`public/pages/explore.html` 对外是
`/pages/explore.html`，故 `rewrites` 的 destination 写 `/pages/…` 而不是 `/public/pages/…`。）

两种产物，由 `--live` 区分：

  * **默认（不加 `--live`）：占位兜底页**。整片卡片不铺（`include_plugins=False`），只渲染
    空态（一句说明 + 「阅读文档」按钮）。仓库里提交的就是这一份——它是 Vercel 构建失败时的
    降级产物，铺的是**构建机**读到的插件清单，跟某个具体实例未必一致，列出来只会张冠李戴。
  * **`--live`：真实插件清单**。Vercel 构建期用它铺真实卡片；本地手动命令 / 启动钩子都不用。

什么时候必须重跑：默认占位页只跟**外壳与取词**（`explore_page.py` / i18n catalog / 共享 UI）
走，插件目录怎么变都不影响它；`--live` 那份才跟插件目录挂钩（新增/删除插件、改 `plugin.json`、
增删视图种类、改 `plugin_config.py` 的 DEFAULT_ARGS）。改完外壳/取词重跑一次并把生成的文件
一起提交即可：

    python -B -m modules.register.explore_static

**不需要手动记这件事**：本地服务（`run_core.run_server`）每次启动时会自动跑一次
`--if-stale`（见 `refresh_static_explore`），所以只要发布前起过一次服务，仓库里那份就已经
是最新的了。CI 侧由 `ExploreStaticPageTest` 断言「提交的文件 == 生成器默认输出」，真漏了
会在测试阶段直接变红。手动命令仍然保留，用于「不想起服务、只想刷这一页」的场合。

**Vercel 构建期会自动跑这一页**：`vercel.json` 里挂了 `buildCommand`，每次部署都会先执行
本模块的 `--live` 模式，产物随本次部署一起上线。原先用不了构建期生成，是因为老配置走
`builds`（legacy）写法，而 Vercel 对带 `builds` 的项目会**整体忽略 Build Command**，平台侧
没有可挂脚本的钩子；现已去掉 `builds`、改用 `buildCommand` + `rewrites`，这一步才真正落在
构建期。

构建命令是**失败即降级**的（`… || … || echo '…skipped…'`，恒以退出码 0 结束）：Vercel 构建
镜像里有没有 `python3`、`pip install -r requirements.txt` 装出来的依赖能不能被 `python3 -m`
import 到，这两件事在本地都验证不了。任何一环不成立，这一步就只打印一行 WARNING、保留仓库里
已提交的那份占位页——最坏情况退化成「一个中性空态页」，不会张冠李戴，也不会因新假设没成立而
把整个部署打挂。是否真跑成功，看部署日志里这一行是「已生成」还是「WARNING skipped」。

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


def build_static_html(lang='en', live=False):
    """→ 静态版 `/explore` 的完整 HTML（取词与共享 UI 都已落定）

    `live=False`（默认）产出**占位兜底页**——不铺卡片，只留空态（见文件头说明）；
    `live=True` 铺**真实插件清单**，供 Vercel 构建期用。
    """
    from modules.i18n.registry import current_lang
    from modules.admin_ui.panel_render import panel_html
    from modules.register.explore_routes import build_explore_html

    # 用 vercel 模式建一次 app：它会跑 register_plugins，把 plugin_result / plugin_states /
    # plugin_routes 填好——正是 build_explore_html 要读的那几份 state。数据库在这一模式下
    # 被停用，与部署环境一致；插件出图本身不依赖库，清单与路由都照常读得到。
    from modules.app_core import create_app
    app = create_app(mode='vercel')[0]

    lang = current_lang(lang)
    inner = build_explore_html(_StaticRequest(app, lang), include_groups=False,
                               include_plugins=live)
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
    parser.add_argument('--live', action='store_true',
                        help='铺真实插件清单（Vercel 构建期用）；默认只生成中性占位兜底页')
    parser.add_argument('--if-stale', action='store_true',
                        help='只在内容确实有变化时写盘并输出，未变化时静默退出'
                             '（供本地服务启动时自动刷新用，见 run_core.refresh_static_explore）')
    args = parser.parse_args(argv)

    html = build_static_html(args.lang, live=args.live)

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
