from fastapi import APIRouter
import os
from modules.register.auto_view_routes import register_view_routes
from modules.register.auto_json_routes import register_json_routes
from modules.register.auto_page_routes import register_page_routes

PLUGIN_NAME = "weather_landscape2"
PLUGIN_DESCRIPTION = "Weather landscape view plugin"

router = APIRouter()
plugin_dir = os.path.dirname(os.path.abspath(__file__))

register_view_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "view"))
register_json_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "json_module"))
register_page_routes(router, PLUGIN_NAME, os.path.join(plugin_dir, "page"))