from fastapi import APIRouter
import os
from modules.register.auto_view_routes import register_view_routes
from modules.register.auto_page_routes import register_page_routes

PLUGIN_NAME = "schedule"
PLUGIN_DESCRIPTION = "课程表插件"

router = APIRouter()
plugin_dir = os.path.dirname(os.path.abspath(__file__))

register_view_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "view"))
register_page_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "page"))
