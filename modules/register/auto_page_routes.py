import os
from fastapi.responses import FileResponse


def register_page_routes(router, plugin_name, page_dir):
    if not os.path.exists(page_dir):
        return
    for fname in os.listdir(page_dir):
        if not fname.endswith('.html'):
            continue
        page_name = fname[:-5]
        file_path = os.path.join(page_dir, fname)

        async def make_page_endpoint(_file_path=file_path):
            return FileResponse(_file_path)

        endpoint_name = f'page_{plugin_name}_{page_name}'
        make_page_endpoint.__name__ = endpoint_name

        router.add_api_route(
            f'/{plugin_name}/page/{page_name}',
            endpoint=make_page_endpoint,
            methods=['GET'],
            name=endpoint_name,
        )