"""Addons management for mods/resourcepacks/shaderpacks via Modrinth.

This module only manages files prefixed by ``palgania_launcher`` to avoid
interfering with user-managed files.
"""

from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple


MODRINTH_BASE = "https://api.modrinth.com/v2"
PREFIX = "palgania_launcher"

# Map addon type to Modrinth project_type facet
PROJECT_TYPE_MAP: Dict[str, str] = {
    "mods": "mod",
    "resourcepacks": "resourcepack",
    "shaderpacks": "shader",
}

# Map launcher loader to modrinth loader facet value (used in version selection only)
LOADER_MAP: Dict[str, str] = {
    "vanilla": "minecraft",  # Modrinth uses "minecraft" for vanilla packs
    "fabric": "fabric",
    "forge": "forge",
    "neoforge": "neoforge",
}


class AddonNotFoundError(Exception):
    """Raised when no addon can be found for a given keyword."""



class AddonsManager:
    def __init__(
        self,
        addon_type: str,
        game_dir: Optional[str] = None,
        loader: str = "vanilla",
        version: Optional[str] = None,
    ) -> None:
        if addon_type not in PROJECT_TYPE_MAP:
            raise ValueError(f"Unsupported addon_type: {addon_type}")
        self.addon_type = addon_type
        self.game_dir = pathlib.Path(game_dir or self._default_game_dir()).expanduser()
        self.loader = loader.lower()
        self.version = version

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
    def _sanitize_keyword(keyword: str) -> str:
        # Simple slug: lowercase, alnum and dashes/underscores
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

    # ------------------------- Modrinth helpers -------------------------
    def _search_project(self, keyword: str, with_version: bool = True) -> Optional[Dict]:
        project_type = PROJECT_TYPE_MAP[self.addon_type]
        # Modrinth MeiliSearch filterable attributes include project_types and game_versions
        facets = [
            [f"project_types:{project_type}"]
        ]
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

    def _get_project(self, project_id_or_slug: str) -> Optional[Dict]:
        url = f"{MODRINTH_BASE}/project/{project_id_or_slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def _select_version(self, project_id: str) -> Optional[Dict]:
        """Select a compatible version with progressive fallback.

        Tries: loader+game_version -> game_version only -> unfiltered.
        Prefers release types.
        """

        def fetch(params: Dict[str, str]) -> List[Dict]:
            query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
            url = f"{MODRINTH_BASE}/project/{project_id}/version{query_str}"
            req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))

        loader_facet = LOADER_MAP.get(self.loader)
        attempts = []
        # 1) loader + game_version
        params = {}
        if loader_facet:
            params["loaders"] = json.dumps([loader_facet])
        if self.version:
            params["game_versions"] = json.dumps([self.version])
        attempts.append(params)
        # 2) game_version only
        if self.version:
            attempts.append({"game_versions": json.dumps([self.version])})
        # 3) unfiltered
        attempts.append({})

        versions: List[Dict] = []
        for p in attempts:
            try:
                versions = fetch(p)
            except Exception:
                versions = []
            if versions:
                break

        if not versions:
            return None
        for v in versions:
            if v.get("version_type") == "release":
                return v
        return versions[0]

    def _download_file(self, url: str, dest: pathlib.Path) -> None:
        if dest.exists():
            return
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)

    def _get_metadata_registry_path(self) -> pathlib.Path:
        """Chemin du fichier JSON central stockant les métadonnées de tous les addons."""
        return pathlib.Path("addons_metadata.json")

    def _load_metadata_registry(self) -> Dict:
        """Charge le registre central des métadonnées."""
        path = self._get_metadata_registry_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_metadata_registry(self, registry: Dict) -> None:
        """Sauvegarde le registre central des métadonnées."""
        path = self._get_metadata_registry_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _get_file_key(self, filepath: pathlib.Path) -> str:
        """Clé unique pour identifier un fichier dans le registre."""
        return str(filepath.resolve())

    def _store_addon_metadata(self, filepath: pathlib.Path, version_obj: Dict, keyword: str) -> None:
        """Stocke les métadonnées d'un addon dans le registre central."""
        registry = self._load_metadata_registry()
        key = self._get_file_key(filepath)
        registry[key] = {
            "keyword": keyword,
            "loaders": version_obj.get("loaders", []),
            "game_versions": version_obj.get("game_versions", []),
            "version_id": version_obj.get("id"),
            "project_id": version_obj.get("project_id"),
            "addon_type": self.addon_type,
        }
        self._save_metadata_registry(registry)

    def _get_addon_metadata(self, filepath: pathlib.Path) -> Optional[Dict]:
        """Récupère les métadonnées d'un addon depuis le registre central."""
        registry = self._load_metadata_registry()
        key = self._get_file_key(filepath)
        return registry.get(key)

    def _is_loader_compatible(self, filepath: pathlib.Path) -> bool:
        """Vérifie la compatibilité du loader en utilisant les métadonnées stockées."""
        # Resource packs / shaderpacks sont indépendants du mod loader
        if self.addon_type != "mods":
            return True
        
        desired = self.loader
        if desired not in ("fabric", "forge", "neoforge"):
            return False
        
        metadata = self._get_addon_metadata(filepath)
        if not metadata:
            # Pas de métadonnées = on ne peut pas déterminer, donc incompatible
            return False
        
        loaders = metadata.get("loaders", [])
        if isinstance(loaders, list):
            return desired in [str(x).lower() for x in loaders]
        
        return False

    def _is_game_version_compatible(self, filepath: pathlib.Path) -> bool:
        """Vérifie la compatibilité de la version à partir des métadonnées du registre.

        Règle stricte: exige une correspondance EXACTE de version lorsque des métadonnées existent.
        (Ne fait plus d'approximations par famille 1.21.x pour éviter les crashs.)
        """
        if not self.version:
            return True

        metadata = self._get_addon_metadata(filepath)
        if not metadata:
            # Pas de métadonnées connues
            return False

        target = str(self.version)
        game_versions = metadata.get("game_versions", [])
        if not isinstance(game_versions, list):
            return False

        return target in game_versions

    def _unmanaged_file_version_compatible(self, filepath: pathlib.Path) -> bool:
        """Heuristique minimale pour les fichiers non gérés (sans préfixe):
        - Si le nom de fichier indique explicitement une version (ex: mc1.21.11, 1.21.11),
          exiger une égalité exacte avec la version cible.
        - Sinon (pas d'indication explicite), considérer comme compatible (on ne sait pas).
        """
        if not self.version:
            return True
        name = filepath.name.lower()
        target = str(self.version)
        # Cherche des marqueurs explicites dans le nom
        markers = [f"mc{target}", f"-{target}-", f"_{target}_", f"+mc{target}", f"+{target}", f"-{target}.jar"]
        # Si on trouve la cible exacte, ok
        if any(m in name for m in markers):
            return True
        # Si le nom encode une autre version explicite 1.XX.YY différente -> incompatible
        # Détection grossière des versions sous forme 1.x.y (en cherchant 'mc1.' ou '-1.')
        # On compare simplement la présence d'une autre sous-chaîne '1.' suivie de chiffres
        # différente de la cible exacte.
        # Cas courants: 
        #   sodium-0.8.2+mc1.21.11.jar -> incompatible si target = 1.21.8
        family_token = target.rsplit('.', 1)[0]  # 1.21 pour 1.21.8
        # Si une autre version mc1.21.ZZ est présente mais != target, considérer incompatible
        # Recherche de 'mc1.21.' puis extraction de la suite
        if f"mc{family_token}." in name:
            # Il y a une version explicite de cette famille
            # Exige l'égalité exacte, sinon incompatible
            return f"mc{target}" in name
        # Autres formats possibles '-1.21.11-'
        if f"-{family_token}." in name or f"+{family_token}." in name or f"_{family_token}." in name:
            return (f"-{target}-" in name) or (f"+{target}" in name) or (f"_{target}_" in name) or name.endswith(f"-{target}.jar")
        # Pas d'indication explicite: ne pas toucher
        return True

    # ------------------------- Public API -------------------------
    def fetch_keyword(self, keyword: str) -> Optional[pathlib.Path]:
        """Download the newest matching addon for keyword into *_available with launcher prefix.

        Returns the downloaded (or existing) file path.
        Raises AddonNotFoundError if nothing matches.
        """
        available_dir, _ = self._dirs()
        slug = self._sanitize_keyword(keyword)

        # 1) Try search with game version
        project = self._search_project(keyword, with_version=True)
        # 2) Retry without version if nothing found
        if not project:
            project = self._search_project(keyword, with_version=False)
        # 3) Try direct project fetch by slug/id
        if not project:
            project = self._get_project(keyword)
        if not project:
            raise AddonNotFoundError(f"Aucun addon trouvé pour '{keyword}'")
        # Modrinth search returns "project_id" and "slug"; direct fetch returns "id" and "slug"
        project_id = project.get("project_id") or project.get("id") or project.get("slug")
        if not project_id:
            raise AddonNotFoundError(f"Aucun addon trouvé pour '{keyword}'")

        version_obj = self._select_version(project_id)
        if not version_obj:
            raise AddonNotFoundError(f"Aucune version compatible trouvée pour '{keyword}'")
        files = version_obj.get("files", [])
        if not files:
            raise AddonNotFoundError(f"Aucun fichier téléchargeable pour '{keyword}'")
        file_obj = files[0]
        download_url = file_obj.get("url") or file_obj.get("download_url")
        filename = file_obj.get("filename") or f"{slug}.jar"
        prefixed_name = f"{PREFIX}_{slug}_{filename}"
        dest_path = available_dir / prefixed_name
        if download_url:
            self._download_file(download_url, dest_path)
            # Stocker les métadonnées dans le registre central
            self._store_addon_metadata(dest_path, version_obj, keyword)
        return dest_path

    def install_addons(self, keywords: List[str]) -> List[pathlib.Path]:
        """Move prefixed files matching keywords from *_available to live dir; move others back.

        Only files starting with the launcher prefix are moved.
        Returns list of installed file paths in the target directory.
        """
        available_dir, target_dir = self._dirs()
        wanted = {self._sanitize_keyword(k) for k in keywords}
        installed: List[pathlib.Path] = []

        # ÉTAPE 1: Nettoyer d'abord le dossier target en déplaçant les fichiers incompatibles vers available
        # Cela évite les conflits de versions (ex: mods 1.21.11 restant quand on lance en 1.21.9)
        for path in target_dir.iterdir():
            if path.name.startswith(PREFIX):
                matched = any(path.name.startswith(f"{PREFIX}_{w}_") for w in wanted)
                compatible = self._is_loader_compatible(path) and self._is_game_version_compatible(path)
                if matched and compatible:
                    continue
                dest = available_dir / path.name
                if dest.exists():
                    dest.unlink()
                shutil.move(str(path), dest)
                registry = self._load_metadata_registry()
                old_key = self._get_file_key(path)
                if old_key in registry:
                    new_key = self._get_file_key(dest)
                    registry[new_key] = registry.pop(old_key)
                    self._save_metadata_registry(registry)
            else:
                # Fichier non géré (pas de préfixe). Si clairement incompatible (version explicite différente), on isole.
                if self.addon_type == "mods" and not self._unmanaged_file_version_compatible(path):
                    dest = available_dir / path.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(path), dest)

        # ÉTAPE 2: Installer les fichiers compatibles depuis available vers target
        for path in available_dir.iterdir():
            if not path.name.startswith(PREFIX):
                continue
            # Decide if this file corresponds to a requested keyword
            matched = any(path.name.startswith(f"{PREFIX}_{w}_") for w in wanted)
            if matched and self._is_loader_compatible(path) and self._is_game_version_compatible(path):
                dest = target_dir / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest.unlink()
                shutil.move(str(path), dest)
                installed.append(dest)
                # Mettre à jour le chemin dans le registre des métadonnées
                registry = self._load_metadata_registry()
                old_key = self._get_file_key(path)
                if old_key in registry:
                    new_key = self._get_file_key(dest)
                    registry[new_key] = registry.pop(old_key)
                    self._save_metadata_registry(registry)

        return installed

    def fetch_install(self, keywords: List[str]) -> List[pathlib.Path]:
        """Fetch (if missing) then install addons for the given keywords.

        Raises AddonNotFoundError if one or more keywords cannot be resolved.
        """
        missing: List[str] = []
        for kw in keywords:
            try:
                self.fetch_keyword(kw)
            except AddonNotFoundError:
                missing.append(kw)
            except Exception:
                # Swallow unexpected errors per keyword but record as missing
                missing.append(kw)
        if missing:
            raise AddonNotFoundError("Addons introuvables: " + ", ".join(missing))
        return self.install_addons(keywords)