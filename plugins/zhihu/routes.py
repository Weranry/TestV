from fastapi import APIRouter
import os
from modules.register.auto_view_routes import register_view_routes

PLUGIN_NAME = "zhihu"
PLUGIN_DESCRIPTION = "知乎日报"

router = APIRouter()
plugin_dir = os.path.dirname(os.path.abspath(__file__))

register_view_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "view"))
