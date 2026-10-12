from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from modules.admin import (
    announce_routes, api_docs_routes, auth_routes, backup_routes, config_routes, device_routes,
    log_routes, page_routes, plugin_routes, prerender_routes, status_routes, user_routes,
)

router = APIRouter(prefix='/admin', tags=['admin'])

router.include_router(status_routes.router)
router.include_router(plugin_routes.router)
router.include_router(api_docs_routes.router)
router.include_router(config_routes.router)
router.include_router(user_routes.router)
router.include_router(announce_routes.router)
router.include_router(log_routes.router)
router.include_router(prerender_routes.router)
router.include_router(backup_routes.router)
router.include_router(auth_routes.router)
router.include_router(device_routes.router)
router.include_router(page_routes.router)

# 空路径别名（注册出 /admin，无尾斜杠）。子路由不能声明空 path，
# 故这条只能留在聚合层，路由名与原文件保持一致。
@router.get('', response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return await page_routes.admin_dashboard(request)