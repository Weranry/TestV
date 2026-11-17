"""知乎日报 RSS 取数与解析。

数据源是 RSSHub 的知乎日报订阅（`<base>/zhihu/daily`，base 默认见
`_DEFAULT_RSSHUB_BASE`），返回 RSS(2.0) 或 Atom 格式的 XML。用 BeautifulSoup 的
html.parser 解析：它比 XML 解析器宽容，同时能捕获 <item> 与 <entry>，正好覆盖两种格式。

原默认实例 rsshub.umi.im 已经无法解析（DNS 找不到主机），这里换成可用实例；
公共实例的可用性会波动，因此 base 可由 rsshub_base 参数覆盖，建议指到自建实例。

网络与解析失败按「拿不到数据」抛 ParamError（沿用原插件的责任划分），并且保留真实
原因——不再像旧版那样用一个宽 try/except 把内部的 ParamError 二次包成一句泛化文案，
那样会把「解析不到 link」这类排障时最想看到的信息盖掉。
"""
import re
import warnings

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from modules.errors.errors import ParamError

# 原默认实例 rsshub.umi.im 已失效，换用可用实例；可用 rsshub_base 覆盖
_DEFAULT_RSSHUB_BASE = 'https://rsshub.rssforever.com'
_TIMEOUT_SECONDS = 10.0
_USER_AGENT = 'eInkViews-zhihu-plugin'

# 忽略 HTML 解析 XML 的警告
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def _extract_link(item, xml_data):
    """提取条目链接。

    html.parser 下 XML 的 `<link>url</link>` 可能被解析成自闭合的 `<link/>`，
    url 落到 next_sibling；再取不到时才用正则兜底。
    """
    link_tag = item.find('link')
    if link_tag:
        link = link_tag.get_text(strip=True)
        if not link:
            sibling = link_tag.next_sibling
            if sibling and isinstance(sibling, str):
                link = sibling.strip()
            elif link_tag.get('href'):
                link = link_tag.get('href')
        if link:
            return link

    match = re.search(r'<link>(.*?)</link>', xml_data, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ''


async def fetch_zhihu_daily(rsshub_base=None):
    """取当日知乎日报最新一条的标题与原文链接；`rsshub_base` 可覆盖默认实例。"""
    base = (rsshub_base or _DEFAULT_RSSHUB_BASE).rstrip('/')
    url = f'{base}/zhihu/daily'
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        # httpx 超时异常的 str() 可能是空串，带上类型名才看得出是超时还是连不上
        raise ParamError(f"知乎日报获取失败: {type(exc).__name__}: {str(exc)}")

    if resp.status_code != 200:
        raise ParamError(f"知乎日报获取失败: HTTP {resp.status_code}")

    # 强制按 UTF-8 解码，防止部分环境解析 RSS 时文字乱码
    xml_data = resp.content.decode('utf-8', errors='replace')

    soup = BeautifulSoup(xml_data, 'html.parser')
    item = soup.find('item') or soup.find('entry')
    if not item:
        raise ParamError("知乎日报响应里没有条目（item/entry）")

    title_tag = item.find('title')
    title = title_tag.get_text(strip=True) if title_tag else 'No Title'

    link = _extract_link(item, xml_data)
    if not link:
        raise ParamError("无法从知乎日报条目里解析出链接")

    return {'title': title, 'link': link}
