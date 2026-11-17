"""维基百科首页摘要 JSON。"""
from modules.utils.timezone import now_in_timezone

from ..lib.fetcher import fetch_wikipedia_daily_sync


def to_json(**kwargs):
    data = fetch_wikipedia_daily_sync(page_url=kwargs.get('page_url'))
    now = now_in_timezone(kwargs.get('tz'))
    return {
        'generated_at': now.isoformat(timespec='seconds'),
        **data,
    }
