"""Map root IDs to server paths only after per-user authorization."""

from pathlib import Path
from typing import Any

from app.core.config import settings


def authorized_roots(user_id: str) -> list[dict[str, Any]]:
    return [root for root in settings.source_repo_roots if user_id in root.get("user_ids", [])]


def local_repository(config: dict[str, Any], user_id: str) -> tuple[Path, list[Path]]:
    root = next((item for item in authorized_roots(user_id) if item.get("id") == config.get("root_id")), None)
    if root is None:
        raise ValueError("仓库根目录未授权")
    relative = config.get("relative_path", "")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("仓库路径必须位于授权根目录内")
    base = Path(root["path"])
    if not base.is_absolute():
        raise ValueError("仓库根目录配置必须为绝对路径")
    base = base.resolve()
    target = base / relative
    # Check unresolved ancestors too: resolving first would hide a junction.
    for part in (target, *target.parents):
        if part == base.parent:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("仓库路径不能经过链接目录")
    target = target.resolve()
    if not target.is_relative_to(base) or not target.is_dir():
        raise ValueError("仓库路径不存在或超出授权范围")
    return target, [base]


def source_config(kind: str, config: dict[str, Any], user_id: str) -> dict[str, Any]:
    if kind in {"document", "image"}:
        if config:
            raise ValueError("文档来源不接受仓库配置")
        return {}
    allowed = {"root_id", "relative_path", "include_paths"} if kind == "git_local" else {"url", "include_paths"}
    if set(config) - allowed:
        raise ValueError("不支持的仓库配置")
    includes = config.get("include_paths", [])
    if not isinstance(includes, list) or len(includes) > 100 or any(
        not isinstance(path, str) or not path or len(path) > 500 or ".." in path.split("/") or path.startswith(("/", "\\")) or ":" in path
        for path in includes
    ):
        raise ValueError("采集范围必须是仓库内相对路径列表")
    if kind == "git_local":
        if not isinstance(config.get("root_id"), str):
            raise ValueError("请选择授权根目录")
        local_repository(config, user_id)
        return {"root_id": config["root_id"], "relative_path": config.get("relative_path", ""), "include_paths": includes}
    url = config.get("url", "")
    if not isinstance(url, str):
        raise ValueError("仅支持公开 GitHub HTTPS 仓库链接")
    from app.services.connectors.git_public import canonical_public_url
    return {"url": canonical_public_url(url), "include_paths": includes}
