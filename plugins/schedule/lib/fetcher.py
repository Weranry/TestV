import json
import os
import re
from datetime import datetime

from modules.errors.errors import ParamError
from modules.utils.timezone import now_in_timezone

# JSON 里没写 timeSlots 时的默认节次，保证旧课程表仍能直接用
DEFAULT_TIME_SLOTS = (
    {'label': 'M1', 'start': None, 'end': None},
    {'label': 'M2', 'start': None, 'end': None},
    {'label': 'A1', 'start': None, 'end': None},
    {'label': 'A2', 'start': None, 'end': None},
    {'label': 'EV', 'start': None, 'end': None},
)

_TIME_PATTERN = re.compile(r'^(\d{1,2}):(\d{2})$')


def _to_int(value):
    """把 week / lesson 这类字段安全转成整数；转不了就返回 None。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_time(value):
    """把 8:05 / 08:05 统一成 08:05；非法时间返回 None。"""
    match = _TIME_PATTERN.match(str(value or '').strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f'{hour:02d}:{minute:02d}'


def _normalize_slots(raw):
    """解析 timeSlots：支持 ['M1', ...] 与 [{'label', 'start', 'end'}, ...] 两种写法。

    数组长度就是当天的节次数量；缺失或格式异常时退回默认的 5 节。
    """
    if not isinstance(raw, list) or not raw:
        return [dict(slot) for slot in DEFAULT_TIME_SLOTS]

    slots = []
    for index, item in enumerate(raw, start=1):
        fallback = f'第{index}节'
        if isinstance(item, str):
            slots.append({'label': item.strip() or fallback, 'start': None, 'end': None})
            continue
        if not isinstance(item, dict):
            continue
        label = str(item.get('label') or fallback).strip() or fallback
        slots.append({
            'label': label,
            'start': _normalize_time(item.get('start')),
            'end': _normalize_time(item.get('end')),
        })
    return slots or [dict(slot) for slot in DEFAULT_TIME_SLOTS]


def _join_unique(values):
    """多个值去重后拼成一行，用于同一节次有多门课/多个教室的情况。"""
    seen, result = set(), []
    for value in values:
        text = str(value or '').strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return ' / '.join(result)


class ScheduleFetcher:
    """读取 assets/course/ 下的课程表 JSON，算出指定日期当天的课程列表。

    纯本地文件读取，不涉及网络，因此保持同步实现（视图直接同步调用即可）。
    """

    def __init__(self, json_name='course_schedule'):
        self.plugin_dir = os.path.dirname(os.path.dirname(__file__))
        self.json_path = os.path.join(self.plugin_dir, 'assets', 'course', f'{json_name}.json')

        if not os.path.exists(self.json_path):
            raise ParamError(f"课程表文件 {json_name}.json 不存在")

        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except Exception as e:
            raise ParamError(f"解析课程表失败: {str(e)}")

        if not isinstance(self.data, dict):
            raise ParamError("课程表格式错误: 顶层必须是对象")

        # 节次数量与上课时间全部来自 JSON，不再固定 5 节
        self.slots = _normalize_slots(self.data.get('timeSlots'))

    def fetch(self, tz=None):
        current_date = now_in_timezone(tz)

        try:
            semester_start = datetime.strptime(
                self.data['semesterStartDate'],
                '%Y-%m-%d'
            ).replace(tzinfo=current_date.tzinfo)
        except Exception as e:
            raise ParamError(f"学期日期格式错误: {str(e)}")

        # 计算周数（周一为一周开始）；开学前为 0 周，也照常显示，只是当天多半没课
        delta = current_date - semester_start
        week_number = (delta.days // 7) + 1
        day_of_week = current_date.isoweekday()  # 1-7

        courses = self.data.get('courses', [])
        lesson_count = len(self.slots)
        # 同一节次可能有多门课（如分班实验），这里按节次累积而不是后写覆盖前写
        buckets = [{'names': [], 'rooms': [], 'teachers': []} for _ in range(lesson_count)]

        for course in courses if isinstance(courses, list) else []:
            if not isinstance(course, dict):
                continue
            classrooms = course.get('classroom', [])
            for classroom in classrooms if isinstance(classrooms, list) else []:
                if not isinstance(classroom, dict):
                    continue
                if _to_int(classroom.get('dayOfWeek')) != day_of_week:
                    continue
                if week_number not in [_to_int(week) for week in classroom.get('week', []) or []]:
                    continue
                lesson = _to_int(classroom.get('lesson'))
                if lesson is None or not 1 <= lesson <= lesson_count:
                    continue

                bucket = buckets[lesson - 1]
                bucket['names'].append(course.get('courseName'))
                bucket['rooms'].append(classroom.get('room'))
                bucket['teachers'].append(course.get('teacher'))

        # 只输出当天真正有课的节次，空节次不占版面
        entries = []
        for index, bucket in enumerate(buckets):
            name = _join_unique(bucket['names'])
            if not name:
                continue
            slot = self.slots[index]
            entries.append({
                'name': name,
                'room': _join_unique(bucket['rooms']),
                'teacher': _join_unique(bucket['teachers']),
                'label': slot['label'],
                'start': slot['start'],
                'end': slot['end'],
            })

        date_info = {
            'todayDate': current_date.strftime('%Y-%m-%d'),
            'weekNumber': week_number,
            'dayOfWeek': ['一', '二', '三', '四', '五', '六', '日'][day_of_week - 1],
        }

        return {'dateInfo': date_info, 'entries': entries}
