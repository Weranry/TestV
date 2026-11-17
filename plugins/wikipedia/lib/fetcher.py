"""中文维基百科首页抓取与解析。

数据源是桌面版首页（默认 `/zh-cn/Wikipedia:首页`），页面使用 mp-2012 版式。
解析只按与语言无关的区块 id 定位，区块标题按页面实际内容读取，因此首页在
「典范条目 / 特色列表」之间轮换时不需要改代码：

- `#mp-2012-column-feature-block`：典范条目 / 特色列表
- `#mp-2012-column-itn-block`：新闻动态，以及「正在发生 / 最近逝世」
- `#mp-2012-column-dyk-block`：你知道吗？

网络失败按「拿不到数据」抛 ParamError，保留异常类型与原始信息，便于排障。
"""
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from modules.errors.errors import ParamError

DEFAULT_PAGE_URL = 'https://zh.wikipedia.org/zh-cn/Wikipedia:%E9%A6%96%E9%A1%B5'
_TIMEOUT_SECONDS = 15.0
_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def _validate_page_url(page_url):
    url = (page_url or DEFAULT_PAGE_URL).strip()
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ParamError('page_url 必须是 http(s) 地址')
    return url


def _clean(text):
    """压缩空白、去掉引用角标与「（图）」标记，并整理中文标点两侧的空格。"""
    text = (text or '').replace('\u00a0', ' ')
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'（图）|\(图\)', '', text)
    text = re.sub(r'\s+', ' ', text)
    # 中文与中文之间的空格是 HTML 里链接边界带出来的，不是原文的一部分
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'\s+([，。、；：？！）】》」』%,.;:?!])', r'\1', text)
    text = re.sub(r'([（【《「『(])\s+', r'\1', text)
    return text.strip(' ：:')


def _extract_list(block):
    """取区块正文里的列表项（新闻动态 / 你知道吗）。"""
    if not block:
        return []
    main = block.find('div', class_='mp-2012-text')
    if not main:
        return []
    return [item for item in (_clean(li.get_text('')) for li in main.find_all('li')) if item]


def _featured_from_block(block):
    heading = block.find('h2')
    label = _clean(heading.get_text('')) if heading else '特色内容'
    main = block.find('div', class_='mp-2012-text')
    if not main:
        return None

    paragraph = main.find('p') or main
    title = ''
    bold = paragraph.find('b')
    if bold:
        title = _clean(bold.get_text(''))

    body = _clean(paragraph.get_text(''))
    if title and body.startswith(title):
        body = body[len(title):].lstrip('，,。 ')
    if not body and not title:
        return None
    return {'label': label, 'title': title, 'text': body}


def _extract_featured(soup):
    """典范条目 / 特色列表：标题取正文第一段的加粗词，正文去掉开头重复的标题。

    首页偶尔把当天内容换成「优良条目」，此时退回该区块，避免整段缺失。
    """
    for block_id in ('mp-2012-column-feature-block', 'mp-2012-column-good-block'):
        block = soup.find('div', id=block_id)
        if not block:
            continue
        item = _featured_from_block(block)
        if item:
            return item
    return None


def _extract_ticker(soup):
    """「正在发生 / 最近逝世」：取 id=column-feature-more 的行，拆成条目数组。

    行内形如 `正在发生：俄乌战争（过程·谈判）－伊朗战争－…`，括号里是附属链接，
    在窄屏快讯条里只会挤占宽度，一并去掉；条目之间按全角连字符拆分。
    """
    result = {'ongoing': [], 'deaths': []}
    for row in soup.find_all('div', id='column-feature-more'):
        header = row.find('span', class_='column-feature-more-header')
        item = row.find('li')
        if not header or not item:
            continue
        head = _clean(header.get_text(''))
        text = _clean(item.get_text(''))
        if head and text.startswith(head):
            text = text[len(head):]
        text = text.lstrip('：: ')
        parts = []
        for part in re.split(r'[－—]', text):
            part = _clean(re.sub(r'（[^）]*）', '', part))
            if part:
                parts.append(part)
        if '正在发生' in head:
            result['ongoing'] = parts
        elif '最近逝世' in head:
            result['deaths'] = parts
    return result


def parse_wikipedia_main_page(html, source_url=''):
    """把首页 HTML 解析成视图直接消费的结构。"""
    soup = BeautifulSoup(html, 'html.parser')

    featured = _extract_featured(soup)
    news = _extract_list(soup.find('div', id='mp-2012-column-itn-block'))
    dyk = _extract_list(soup.find('div', id='mp-2012-column-dyk-block'))
    ticker = _extract_ticker(soup)

    if not featured and not news and not dyk:
        raise ParamError('维基百科首页解析失败：未找到首页内容区块')

    return {
        'featured': featured,
        'news': news,
        'dyk': dyk,
        'ongoing': ticker['ongoing'],
        'deaths': ticker['deaths'],
        'source': source_url,
    }


async def fetch_wikipedia_daily(page_url=None):
    """异步取数：视图链路。"""
    url = _validate_page_url(page_url)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT, 'Accept-Language': 'zh-CN,zh;q=0.9'},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise ParamError(f'维基百科首页获取失败: {type(exc).__name__}: {exc}')
    if response.status_code != 200:
        raise ParamError(f'维基百科首页获取失败: HTTP {response.status_code}')
    html = response.content.decode('utf-8', errors='replace')
    return parse_wikipedia_main_page(html, source_url=url)


def fetch_wikipedia_daily_sync(page_url=None):
    """同步取数：JSON 链路（auto_json_routes 以同步方式调用 to_json）。"""
    url = _validate_page_url(page_url)
    try:
        with httpx.Client(
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            headers={'User-Agent': _USER_AGENT, 'Accept-Language': 'zh-CN,zh;q=0.9'},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        raise ParamError(f'维基百科首页获取失败: {type(exc).__name__}: {exc}')
    if response.status_code != 200:
        raise ParamError(f'维基百科首页获取失败: HTTP {response.status_code}')
    html = response.content.decode('utf-8', errors='replace')
    return parse_wikipedia_main_page(html, source_url=url)
