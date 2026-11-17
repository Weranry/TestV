"""定时预渲染的调度循环。

调度只做两件事：判断哪些任务到期（next_run_at <= now），把到期任务串行交给 runner。
排期一律以「本次执行结束的当前时间」为锚，而不是以旧计划时间为锚——否则一次停机
积压出来的多个周期会在重启后被连续补跑，把刚省下来的算力又还回去。
"""
import asyncio
import datetime

import config
from modules.prerender import alerts
from modules.prerender import runner
from modules.prerender import store
from modules.utils import plog

# 内存防重入：任务行在库里是共享状态，同 id 同时跑两次会互相覆盖
_running_ids = set()


def running_ids():
    return set(_running_ids)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _as_naive_utc(dt):
    """aware datetime 归一到 naive UTC；naive 视为已经是 UTC（不做时区解释）"""
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def fmt_utc(dt):
    """落库统一成"秒精度 + Z 后缀"的 UTC ISO 字符串。

    格式必须固定：next_run_at 的比较是字符串字典序，`...T12:00:00Z` 与
    `...T12:00:00.123456+00:00` 混在一起时 'Z'(0x5A) 与 '.'(0x2E) 的先后会出错。

    naive datetime 一律**视为已经是 UTC**，绝不能交给 astimezone()：它会把 naive
    时间按系统本地时区解释，在 UTC+8 的机器上凭空多减 8 小时（daily 任务会早触发 8 小时）。
    """
    return _as_naive_utc(dt).replace(microsecond=0).isoformat() + 'Z'


# 一天的触发时刻上限：只是防呆，避免有人贴进来一整天的分钟数把候选集撑爆
MAX_DAILY_TIMES = 24


def parse_daily_times(text):
    """'10:00 12:00,15:00' → [(10,0), (12,0), (15,0)]（去重升序）

    分隔符接受空格（含全角）与中英文逗号。任一段不合法就整体判非法（返回 None），
    而不是忽略坏的那段：静默少排一个时刻比直接报错更难排查。
    """
    chunks = str(text or '').replace(',', ' ').replace('，', ' ').replace('、', ' ').split()
    if not chunks or len(chunks) > MAX_DAILY_TIMES:
        return None
    times = set()
    for chunk in chunks:
        parts = chunk.split(':')
        if len(parts) != 2:
            return None
        try:
            hh, mm = int(parts[0]), int(parts[1])
        except (TypeError, ValueError):
            return None
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
        times.add((hh, mm))
    return sorted(times)


def normalize_daily_times(text):
    """落库用的规范形式 'HH:MM,HH:MM'；非法或为空返回 ''"""
    times = parse_daily_times(text)
    if not times:
        return ''
    return ','.join(f'{hh:02d}:{mm:02d}' for hh, mm in times)


# ======================== Cron ========================

# 五段式 cron 的取值范围：分 时 日 月 周。周字段 0 与 7 都表示周日。
_CRON_FIELDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

# 向前搜索的上限（天）：防呆，避免一个永不命中的表达式（如 2 月 30 日）把循环跑成死循环。
# 366 天覆盖闰年整年，足以命中最长周期的合法表达式。
CRON_SEARCH_DAYS = 366


def _to_int(text):
    """严格整数：不接受 '1.0'、' 1 ' 之外的写法，失败返回 None"""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _cron_field_values(text, lo, hi):
    """单段 → 命中值集合；整段为 '*' 时返回 None（表示不限）；非法返回 False"""
    text = str(text).strip()
    if text == '*':
        return None
    values = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            return False
        has_step = '/' in part
        step = 1
        if has_step:
            part, _, step_text = part.partition('/')
            step = _to_int(step_text)
            if step is None or step <= 0:
                return False
        if part == '*':
            start, end = lo, hi
        elif '-' in part:
            low_text, _, high_text = part.partition('-')
            start, end = _to_int(low_text), _to_int(high_text)
            if start is None or end is None:
                return False
        else:
            start = _to_int(part)
            if start is None:
                return False
            # 单值带步长（'5/10'）按标准 cron 理解成「从 5 起到上限，每隔 10 个」
            end = hi if has_step else start
        if start < lo or end > hi or start > end:
            return False
        values.update(range(start, end + 1, step))
    if not values:
        return False
    return values


def parse_cron(expr):
    """五段 cron → (minute, hour, dom, month, dow) 的匹配集合（'*' 段为 None）

    支持 `*`、`n`、`a-b`、`*/n`、`a-b/n` 与逗号列表。任一段不合法（越界、步长非正、
    段数不是 5）就整体判非法返回 None——与 `parse_daily_times` 同一约定：静默少排一次
    比直接报错更难排查。不支持 `@daily` 这类别名，也不支持秒级 / 年份字段。
    """
    parts = str(expr or '').split()
    if len(parts) != 5:
        return None
    fields = []
    for text, (lo, hi) in zip(parts, _CRON_FIELDS):
        values = _cron_field_values(text, lo, hi)
        if values is False:
            return None
        fields.append(values)
    minute, hour, dom, month, dow = fields
    if dow is not None:
        dow = {0 if v == 7 else v for v in dow}
    return (minute, hour, dom, month, dow)


def normalize_cron(expr):
    """落库用的规范形式（段间单空格）；非法或为空返回 ''"""
    parts = str(expr or '').split()
    if len(parts) != 5 or parse_cron(expr) is None:
        return ''
    return ' '.join(parts)


def _cron_day_matches(cron, day):
    """某一天是否命中（月 + 日 / 星期）"""
    _, _, dom, month, dow = cron
    if month is not None and day.month not in month:
        return False
    dom_ok = dom is None or day.day in dom
    dow_ok = dow is None or (day.weekday() + 1) % 7 in dow
    # 标准 cron 语义：日与星期都限定时取「或」（任一命中即触发），只限定一个时那个说了算
    if dom is not None and dow is not None:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _cron_time_in_day(cron, floor):
    """floor 当天不早于 floor 的第一个命中时刻；当天无命中返回 None"""
    minute, hour, *_ = cron
    for hh in range(floor.hour, 24):
        if hour is not None and hh not in hour:
            continue
        start_mm = floor.minute if hh == floor.hour else 0
        for mm in range(start_mm, 60):
            if minute is not None and mm not in minute:
                continue
            return floor.replace(hour=hh, minute=mm)
    return None


def _next_cron_time(cron, local_now):
    """local_now 之后（不含）的第一个命中时刻（本地墙上时间）；找不到返回 None

    cron 最小粒度是分钟，所以先向下取整到分钟再 +1 分钟：与当前时刻相等必须顺延，
    否则任务会被立刻触发一次。逐天推进定位命中日，再在当天逐时逐分定位，避免
    「逐分钟扫 366 天」这种 50 万次的循环。
    """
    start = local_now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    day = start.date()
    for _ in range(CRON_SEARCH_DAYS):
        midnight = datetime.datetime.combine(day, datetime.time(0, 0))
        if _cron_day_matches(cron, midnight):
            hit = _cron_time_in_day(cron, start if day == start.date() else midnight)
            if hit is not None:
                return hit
        day += datetime.timedelta(days=1)
    return None


def _cron_expr_of(task):
    """任务行里的 cron 表达式；行对象缺列（旧库 / 手拼的 dict）时按空串处理"""
    try:
        return task['cron_expr']
    except (KeyError, IndexError, TypeError):
        return ''


def compute_next_run(task, now_utc=None):
    """算下一次执行时间（UTC ISO 字符串）；配置非法返回 None"""
    now = now_utc or _now_utc()
    schedule_type = str(task['schedule_type'] or 'interval').lower()

    if schedule_type in ('daily', 'cron'):
        cron = None
        if schedule_type == 'daily':
            times = parse_daily_times(task['daily_time'])
            if not times:
                return None
        else:
            times = None
            cron = parse_cron(_cron_expr_of(task))
            if cron is None:
                return None
        # daily_time / cron 表达式都是"配置时区里的墙上时间"，落库前换算回 UTC
        from modules.utils.timezone import get_timezone_offset
        offset = get_timezone_offset()
        offset = float(offset) if offset is not None else 0.0
        # 本地基准时刻必须由传入的 now 换算，不能另取墙上时钟：否则传进来的
        # now_utc 在 daily 分支被静默忽略，函数也就不再可测
        local_now = _as_naive_utc(now) + datetime.timedelta(hours=offset)
        if cron is not None:
            local_next = _next_cron_time(cron, local_now)
            if local_next is None:
                return None
            return fmt_utc(local_next - datetime.timedelta(hours=offset))
        candidates = []
        for hh, mm in times:
            cand = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            # 已过的时刻顺延到次日；多个时刻取最早的那个
            candidates.append(cand if cand > local_now else cand + datetime.timedelta(days=1))
        return fmt_utc(min(candidates) - datetime.timedelta(hours=offset))

    try:
        interval = int(task['interval_seconds'] or 0)
    except (TypeError, ValueError):
        return None
    if interval <= 0:
        return None
    return fmt_utc(now + datetime.timedelta(seconds=interval))


def _tick_seconds():
    try:
        return max(1, int(config.PRERENDER_TICK_SECONDS or 10))
    except (TypeError, ValueError):
        return 10


def last_daily_occurrence(daily_time, now_utc=None):
    """`daily_time` 里「最近一次已经到点」的时刻（UTC ISO 字符串）；无可用时刻返回 None。

    与 `compute_next_run` 的 daily 分支共用同一套口径：`daily_time` 是配置时区里的墙上
    时间，naive datetime 一律视为 UTC，落库统一成带 Z 的秒精度 ISO（字符串比较才成立）。
    今天还没到任何时刻时取**昨天最后一个**时刻——「最近一次该跑的点」一直在那儿，
    调用方拿它和上次执行记录比大小即可判断要不要补跑。
    """
    times = parse_daily_times(daily_time)
    if not times:
        return None
    from modules.utils.timezone import get_timezone_offset
    try:
        offset = float(get_timezone_offset() or 0)
    except (TypeError, ValueError):
        offset = 0.0
    local_now = _as_naive_utc(now_utc or _now_utc()) + datetime.timedelta(hours=offset)
    today = local_now.date()
    passed = [datetime.datetime.combine(today, datetime.time(hh, mm))
              for hh, mm in times
              if datetime.datetime.combine(today, datetime.time(hh, mm)) <= local_now]
    if not passed:
        hh, mm = times[-1]
        passed = [datetime.datetime.combine(today, datetime.time(hh, mm)) - datetime.timedelta(days=1)]
    return fmt_utc(max(passed) - datetime.timedelta(hours=offset))


async def run_one(app, task, semaphore):
    """执行单个任务并把结果写回任务行"""
    task_id = task['id']
    if task_id in _running_ids:
        return
    _running_ids.add(task_id)
    try:
        async with semaphore:
            result = await runner.run_task(app, task)
        store.mark_run(
            task_id, result['status'], result['error'], result['elapsed_ms'],
            compute_next_run(task, _now_utc()),
        )
        # 失败与「路由失效」才告警：skipped 是"暂时不做"，重启用就会恢复，不值得报警
        if result['status'] in (runner.STATUS_ERROR, runner.STATUS_INVALID):
            await alerts.notify_failure(task, result)
    except Exception:
        plog.exception(f'预渲染任务 {task_id} 执行异常')
    finally:
        _running_ids.discard(task_id)


async def run_due(app):
    """取一批到期任务执行。

    PRERENDER_MAX_CONCURRENCY <= 1 时逐条串行（默认，行为与改造前逐字节一致）；
    大于 1 时才真正并行——同一批任务用 gather 同时开跑，受同一个信号量约束，
    否则逐条 await 会让信号量永远只被一个协程持有，配置调大毫无效果。

    gather 是安全的：run_one 内部用 _running_ids 防同 id 重入，结果写回走
    store.mark_run / store.put_cache（SQLite + core._db_lock 全局线程锁），
    没有非线程安全的内存结构。
    """
    if not getattr(app.state, 'prerender_enabled', False):
        # 多实例下只有 leader 为真（见 lifecycle.start_shared_loop）：产物是全集群共用的，
        # 但"谁来生成"必须唯一，否则同一批任务会被每个实例各跑一遍
        return
    try:
        concurrency = max(1, int(config.PRERENDER_MAX_CONCURRENCY or 1))
    except (TypeError, ValueError):
        concurrency = 1
    semaphore = asyncio.Semaphore(concurrency)
    tasks = store.due_tasks(fmt_utc(_now_utc()))
    if concurrency <= 1:
        for task in tasks:
            await run_one(app, task, semaphore)
        return
    await asyncio.gather(*(run_one(app, task, semaphore) for task in tasks),
                         return_exceptions=True)


async def run_now(app, task):
    """面板「立即执行」：绕过 next_run_at，但同样串行、同样防重入"""
    try:
        concurrency = max(1, int(config.PRERENDER_MAX_CONCURRENCY or 1))
    except (TypeError, ValueError):
        concurrency = 1
    try:
        await asyncio.wait_for(
            run_one(app, task, asyncio.Semaphore(concurrency)), _render_timeout() + 60)
    except asyncio.TimeoutError:
        pass
    return store.get_task(task['id'])


def _render_timeout():
    try:
        return max(1, int(config.PRERENDER_TIMEOUT_SECONDS or 30))
    except (TypeError, ValueError):
        return 30


async def scheduler_loop(app):
    """调度主循环：每 PRERENDER_TICK_SECONDS 醒一次，在所有到期任务跑完后休眠"""
    try:
        grace = max(0, int(config.PRERENDER_STARTUP_GRACE_SECONDS or 0))
    except (TypeError, ValueError):
        grace = 30
    # 启动宽限：进程刚起来时还在建库 / 注册插件 / 应付首屏请求，先让它们稳定下来
    await asyncio.sleep(grace)
    while not app.state._shutdown:
        # 配置必须在循环内现取，面板改完才能立刻生效
        if getattr(app.state, 'prerender_enabled', False) and config.PRERENDER_ENABLE:
            try:
                await run_due(app)
            except Exception:
                plog.exception('预渲染调度循环执行失败')
        # 自动备份搭这一个循环：两者都是"到点做一次"的集群级任务，再起一个循环只是多一份
        # 启动宽限与休眠逻辑。它只看 leader（prerender_enabled），不看 PRERENDER_ENABLE——
        # 关掉预渲染不该把备份一起关掉。
        if getattr(app.state, 'prerender_enabled', False):
            try:
                from modules.admin.backup_routes import maybe_run_scheduled_backup
                await maybe_run_scheduled_backup()
            except Exception:
                plog.exception('定时备份执行失败')
            # 自动更新同样搭这个循环（band 相同：集群级「到点做一次」）。UPDATE_MODE=off 时
            # 第一行就直接返回，不产生任何 git 调用；更新模式改完不必重启即生效
            try:
                from modules.updater import maybe_run_scheduled_update
                await maybe_run_scheduled_update(app)
            except Exception:
                plog.exception('定时更新执行失败')
        await asyncio.sleep(_tick_seconds())