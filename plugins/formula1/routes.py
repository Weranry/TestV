from fastapi import APIRouter
import os
from modules.register.auto_view_routes import register_view_routes
from modules.register.auto_json_routes import register_json_routes
from modules.register.auto_page_routes import register_page_routes

PLUGIN_NAME = "formula1"
PLUGIN_DESCRIPTION = "F1 下场比赛信息：时间、地点、赛道图与周末赛程"

router = APIRouter()
plugin_dir = os.path.dirname(os.path.abspath(__file__))

register_view_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "view"))
register_json_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "json_module"))
register_page_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "page"))
