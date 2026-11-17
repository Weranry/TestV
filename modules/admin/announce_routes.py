from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from modules.admin.common import _body
from modules.i18n.registry import t_req
from modules.errors.errors import error_response

router = APIRouter()

# 站内信是"通知"性质，一屏看完即可，超过 5 条翻页
ANNOUNCE_PAGE_SIZE = 5


def _announcement_hidden(request):
    """该管理组是否把站内信卡片关掉了（user_groups.show_announcement = 0）。

    卡片在概览页，前后端都要挡：前端隐藏只防误触，真正的不变量在后端——
    关掉卡片的管理组不该还能调接口读或发站内信。内置管理组恒为可用的兜底入口。
    """
    user = getattr(request.state, 'user', None)
    if not user:
        return False
    try:
        from modules.database.groups import get_group, is_admin_category
        group = get_group(user.get('group_id'))
        if not group or not is_admin_category(group.get('category')):
            return False
        if group.get('builtin'):
            return False
        return not group.get('show_announcement', 1)
    except Exception:
        # 查不到就放行，交回给已有的分页权限校验（fail-open 在这里不放大权限：
        # 未映射路径的请求在中间件已 fail-closed）
        return False


@router.get('/api/announcements')
async def admin_list_announcements(request: Request):
    if _announcement_hidden(request):
        return error_response(t_req(request, 'announce.card_disabled'), 403)
    try:
        limit = min(int(request.query_params.get('limit', ANNOUNCE_PAGE_SIZE)), 100)
        offset = max(int(request.query_params.get('offset', 0)), 0)
        from modules.database.announcements import get_announcements, count_announcements
        return {'items': get_announcements(limit, offset), 'total': count_announcements()}
    except Exception as e:
        return error_response(str(e), 500)


@router.post('/api/announcements')
async def admin_create_announcement(request: Request):
    if _announcement_hidden(request):
        return error_response(t_req(request, 'announce.card_disabled'), 403)
    body = await _body(request)
    if body is None: return error_response(t_req(request, 'msg.bad_json'), 400)
    title = (body.get('title') or '').strip()
    if not title: return error_response(t_req(request, 'announce.title_required'), 400)
    content = (body.get('content') or '').strip()
    group_ids = body.get('group_ids')
    if group_ids is None: group_ids = []
    if not isinstance(group_ids, list): return error_response(t_req(request, 'announce.group_ids_not_list'), 400)
    try:
        group_ids = sorted({int(g) for g in group_ids})
    except (TypeError, ValueError):
        return error_response(t_req(request, 'announce.group_ids_invalid'), 400)
    # 空数组 = 全体可见，前端「全选」也走这条
    from modules.database.announcements import create_announcement
    user = getattr(request.state, 'user', None) or {}
    ann_id = create_announcement(title, content, group_ids, admin_name=user.get('name') or '')
    return JSONResponse({'success': True, 'id': ann_id})


@router.delete('/api/announcements/{ann_id}')
async def admin_delete_announcement(ann_id: int, request: Request):
    if _announcement_hidden(request):
        return error_response(t_req(request, 'announce.card_disabled'), 403)
    from modules.database.announcements import delete_announcement
    delete_announcement(ann_id)
    return JSONResponse({'success': True})