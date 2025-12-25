"""Addons management with strict version switching and Modrinth integration.

This module manages ONLY files prefixed by ``palgania_launcher`` to avoid
interfering with user-managed files. It enforces exact game version compatibility
for mods to ensure versions change correctly when switching Minecraft versions
(e.g., 1.21.11 -> 1.21.7).
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

MODRINTH_BASE = "https://api.modrinth.com/v2"
PREFIX = "palgania_launcher"

PROJECT_TYPE_MAP: Dict[str, str] = {
    "mods": "mod",
    "resourcepacks": "resourcepack",
    "shaderpacks": "shader",
}

LOADER_MAP: Dict[str, str] = {
    "vanilla": "minecraft",
    "fabric": "fabric",
    "forge": "forge",
    "neoforge": "neoforge",
}


class AddonNotFoundError(Exception):
    pass


class AddonsManager:
    def __init__(
        self,
        addon_type: str,
        game_dir: Optional[str] = None,
        loader: str = "vanilla",
        version: Optional[str] = None,
        config_dir: Optional[str] = None,
    ) -> None:
        if addon_type not in PROJECT_TYPE_MAP:
            raise ValueError(f"Unsupported addon_type: {addon_type}")
        self.addon_type = addon_type
        self.game_dir = pathlib.Path(game_dir or self._default_game_dir()).expanduser()
        self.loader = loader.lower()
        self.version = version
        env_cfg = os.environ.get("PALGANIA_LAUNCHER_CONFIG_DIR", "")
        self.config_dir = pathlib.Path(config_dir or env_cfg or self._default_config_dir()).expanduser()
        self.config_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------- path helpers -------------------------
    @staticmethod
    def _default_game_dir() -> str:
        system = platform.system().lower()
        home = pathlib.Path.home()
        if system == "windows":
            appdata = os.getenv("APPDATA")
            return str(pathlib.Path(appdata) / ".minecraft") if appdata else str(home / "AppData/Roaming/.minecraft")
        if system == "darwin":
            return str(home / "Library/Application Support/.minecraft")
        return str(home / ".minecraft")

    @staticmethod
    def _default_config_dir() -> str:
        system = platform.system().lower()
        home = pathlib.Path.home()
        if system == "windows":
            return str(home / "AppData/Local/palgania_launcher")
        if system == "darwin":
            return str(home / "Library/Application Support/palgania_launcher")
        return str(home / ".palgania_launcher")

    @staticmethod
    def _sanitize_keyword(keyword: str) -> str:
        allowed = []
        for ch in keyword.lower():
            if ch.isalnum():
                allowed.append(ch)
            elif ch in "-_ ":
                allowed.append("-")
        slug = "".join(allowed).strip("-")
        return slug or "addon"

    def _dirs(self) -> Tuple[pathlib.Path, pathlib.Path]:
        base = self.game_dir
        target_dir = base / self.addon_type
        available_dir = base / f"{self.addon_type}_available"
        target_dir.mkdir(parents=True, exist_ok=True)
        available_dir.mkdir(parents=True, exist_ok=True)
        return available_dir, target_dir

    # ------------------------- Registry -------------------------
    def _registry_path(self) -> pathlib.Path:
        return self.config_dir / "addons_metadata.json"

    def _load_registry(self) -> Dict:
        p = self._registry_path()
        if not p.exists():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_registry(self, reg: Dict) -> None:
        p = self._registry_path()
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(reg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _file_key(self, fp: pathlib.Path) -> str:
        return str(fp.resolve())

    def _store_metadata(self, fp: pathlib.Path, vobj: Dict, keyword: str) -> None:
        reg = self._load_registry()
        key = self._file_key(fp)
        reg[key] = {
            "keyword": keyword,
            "addon_type": self.addon_type,
            "project_id": vobj.get("project_id"),
            "version_id": vobj.get("id"),
            "version_number": vobj.get("version_number"),
            "loaders": vobj.get("loaders", []),
            "game_versions": vobj.get("game_versions", []),
        }
        self._save_registry(reg)

    def _get_metadata(self, fp: pathlib.Path) -> Optional[Dict]:
        reg = self._load_registry()
        return reg.get(self._file_key(fp))

    # ------------------------- Modrinth -------------------------
    def _search_project(self, keyword: str, with_version: bool = True) -> Optional[Dict]:
        facets = [[f"project_types:{PROJECT_TYPE_MAP[self.addon_type]}"]]
        if with_version and self.version:
            facets.append([f"game_versions:{self.version}"])
        params = {
            "query": keyword,
            "facets": json.dumps(facets),
            "limit": 5,
        }
        url = f"{MODRINTH_BASE}/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("hits", [])
            return hits[0] if hits else None

    def _get_project(self, id_or_slug: str) -> Optional[Dict]:
        url = f"{MODRINTH_BASE}/project/{id_or_slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def _fetch_versions(self, project_id: str, params: Dict[str, str]) -> List[Dict]:
        qs = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{MODRINTH_BASE}/project/{project_id}/version{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _select_version_exact(self, project_id: str) -> Optional[Dict]:
        """Select a version strictly compatible with loader + exact game version."""
        params: Dict[str, str] = {}
        loader_facet = LOADER_MAP.get(self.loader)
        if loader_facet:
            params["loaders"] = json.dumps([loader_facet])
        if self.version:
            params["game_versions"] = json.dumps([self.version])
        try:
            versions = self._fetch_versions(project_id, params)
        except Exception:
            versions = []
        if not versions:
            return None
        # Prefer release
        for v in versions:
            if v.get("version_type") == "release":
                return v
        return versions[0]

    # Backward-compat alias for existing tests/tools
    def _select_version(self, project_id: str) -> Optional[Dict]:
        return self._select_version_exact(project_id)

    def _download_file(self, url: str, dest: pathlib.Path) -> None:
        if dest.exists():
            return
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)

    # ------------------------- Compatibility -------------------------
    def _is_loader_compatible(self, fp: pathlib.Path) -> bool:
        if self.addon_type != "mods":
            return True
        meta = self._get_metadata(fp)
        if not meta:
            return False
        loaders = [str(x).lower() for x in meta.get("loaders", []) or []]
        return self.loader in loaders

    def _is_game_version_compatible(self, fp: pathlib.Path) -> bool:
        if not self.version:
            return True
        meta = self._get_metadata(fp)
        if not meta:
            return False
        gvs = meta.get("game_versions", []) or []
        return str(self.version) in [str(x) for x in gvs]

    # ------------------------- Public API -------------------------
    def fetch_keyword(self, keyword: str) -> Optional[pathlib.Path]:
        """Fetch the exact-compatible version into *_available (managed file)."""
        available_dir, target_dir = self._dirs()
        slug = self._sanitize_keyword(keyword)

        # Resolve project
        try:
            project = self._search_project(keyword, with_version=True) or self._search_project(keyword, with_version=False) or self._get_project(keyword)
            if not project:
                raise AddonNotFoundError(f"Aucun addon trouvé pour '{keyword}'")
            pid = project.get("project_id") or project.get("id") or project.get("slug")
            if not pid:
                raise AddonNotFoundError(f"Aucun addon trouvé pour '{keyword}'")

            vobj = self._select_version_exact(pid)
            if not vobj:
                raise AddonNotFoundError(f"Aucune version EXACTE compatible pour '{keyword}' avec {self.loader} {self.version}")

            files = vobj.get("files", [])
            if not files:
                raise AddonNotFoundError(f"Aucun fichier téléchargeable pour '{keyword}'")
            fobj = files[0]
            url = fobj.get("url") or fobj.get("download_url")
            fname = fobj.get("filename") or f"{slug}.jar"
            dest = available_dir / f"{PREFIX}_{slug}_{fname}"
            if url:
                self._download_file(url, dest)
                self._store_metadata(dest, vobj, keyword)
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
            # Offline: try local managed file that is EXACTLY compatible
            for path in (target_dir.iterdir() if target_dir.exists() else []):
                if path.name.startswith(f"{PREFIX}_{slug}_") and self._is_loader_compatible(path) and self._is_game_version_compatible(path):
                    return path
            for path in (available_dir.iterdir() if available_dir.exists() else []):
                if path.name.startswith(f"{PREFIX}_{slug}_") and self._is_loader_compatible(path) and self._is_game_version_compatible(path):
                    return path
            raise AddonNotFoundError(
                f"Impossible de télécharger '{keyword}' (pas d'accès internet) et aucune version locale EXACTE compatible"
            )

    def install_addons(self, keywords: List[str]) -> List[pathlib.Path]:
        """Install requested addons: ensure only exact-compatible managed files remain in target.

        - Move incompatible managed files from target to available
        - For each keyword, move the latest fetched managed file from available to target
        - Keep user unmanaged files untouched
        """
        available_dir, target_dir = self._dirs()
        installed: List[pathlib.Path] = []
        wanted_slugs = [self._sanitize_keyword(k) for k in keywords]

        # 1) Clean target: move incompatible managed files to available
        for path in target_dir.iterdir():
            if path.name.startswith(PREFIX):
                if not (self._is_loader_compatible(path) and self._is_game_version_compatible(path)):
                    dest = available_dir / path.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(path), dest)
                    reg = self._load_registry()
                    old_key = self._file_key(path)
                    if old_key in reg:
                        reg[self._file_key(dest)] = reg.pop(old_key)
                        self._save_registry(reg)

        # 2) For each keyword, remove previous managed file for same slug from target
        for slug in wanted_slugs:
            for path in list(target_dir.iterdir()):
                if path.name.startswith(f"{PREFIX}_{slug}_"):
                    dest = available_dir / path.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(path), dest)
                    reg = self._load_registry()
                    old_key = self._file_key(path)
                    if old_key in reg:
                        reg[self._file_key(dest)] = reg.pop(old_key)
                        self._save_registry(reg)

        # 3) Move exact-compatible managed files from available to target for requested keywords
        for path in available_dir.iterdir():
            if not path.name.startswith(PREFIX):
                continue
            if any(path.name.startswith(f"{PREFIX}_{slug}_") for slug in wanted_slugs):
                if self._is_loader_compatible(path) and self._is_game_version_compatible(path):
                    dest = target_dir / path.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(path), dest)
                    installed.append(dest)
                    reg = self._load_registry()
                    old_key = self._file_key(path)
                    if old_key in reg:
                        reg[self._file_key(dest)] = reg.pop(old_key)
                        self._save_registry(reg)
        return installed

    def fetch_install(self, keywords: List[str]) -> List[pathlib.Path]:
        missing: List[str] = []
        for kw in keywords:
            try:
                self.fetch_keyword(kw)
            except AddonNotFoundError:
                missing.append(kw)
            except Exception:
                missing.append(kw)
        if missing:
            raise AddonNotFoundError("Addons introuvables: " + ", ".join(missing))
        return self.install_addons(keywords)