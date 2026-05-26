from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "app"

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def static_version(path: str) -> int:
    file_path = (STATIC_DIR / path.lstrip("/")).resolve()
    try:
        file_path.relative_to(STATIC_DIR.resolve())
        return int(file_path.stat().st_mtime)
    except (FileNotFoundError, ValueError):
        return 0


templates.env.globals["static_v"] = static_version
static_files = NoCacheStaticFiles(directory=STATIC_DIR)
