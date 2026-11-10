from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

UI_PREFIX = "/ui"
TOKEN_PLACEHOLDER = "%WHAAT_TOKEN%"
ASSETS_DIR = "assets"
NOT_BUILT = "the UI is not built; run `pnpm --dir ui build` in the whaat repo"

router = APIRouter(include_in_schema=False)


@router.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(f"{UI_PREFIX}/")


@router.get(UI_PREFIX)
def redirect_to_ui_root() -> RedirectResponse:
    return RedirectResponse(f"{UI_PREFIX}/")


@router.get(UI_PREFIX + "/{path:path}")
def get_ui_file(path: str, request: Request) -> Response:
    """A built file when one matches; any other path is a route of the UI, so it gets index.html with the token."""
    ui_dir: Path | None = request.app.state.settings.ui_dir
    index = ui_dir / "index.html" if ui_dir else None
    if ui_dir is None or index is None or not index.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_BUILT)
    root = ui_dir.resolve()
    candidate = (root / path).resolve()
    if path and candidate.is_relative_to(root) and candidate.is_file() and candidate != index.resolve():
        return FileResponse(candidate)
    if path.split("/", 1)[0] == ASSETS_DIR:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no UI file {path!r}")
    html = index.read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, request.app.state.token)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
