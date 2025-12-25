"""
Minecraft Addons management
Uses Modrinth API to fetch and install addons (mods, resource packs, shader packs)

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
    "iris": "iris"
}

class AddonNotFoundError(Exception):
    """Raised when an addon cannot be found by keyword"""
    pass

class ModRinthRequestWrapper:
    def search(self, query: str, facets: dict = {}, limit: int = 1, offset: int = 0, **kwargs) -> dict:
        """
        GET /search
        kwargs can contain additional facets such as 
        versions, categories (loader), project_type, etc.
        """
        url = "{}/search?{}".format(MODRINTH_BASE, urllib.parse.urlencode({
            'query': query,
            'facets': json.dumps([[f"{k}:{v}"] for k, v in facets.items()] + [[f"{k}:{v}"] for k, v in kwargs.items()]),
            'limit': limit,
            'offset': offset
        }))
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    
    def get_project(self, project_id: str):
        """
        GET /project/{project_id}
        """
        url = f"{MODRINTH_BASE}/project/{project_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    
    def get_versions(self, project_id: str, loaders : list, game_versions: list):
        """
        GET /project/{project_id}/version
        """
        url = "{}/project/{}/version?{}".format(MODRINTH_BASE, project_id, urllib.parse.urlencode({
            'loaders': json.dumps(loaders),
            'game_versions': json.dumps(game_versions)
        }))
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    
    def download_file(self, file : dict, dest_dir: pathlib.Path):
        """
        Download file from given file dict
        """
        if isinstance(dest_dir, str):
            dest_dir = pathlib.Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        url = file.get("url")
        filename = file.get("filename")
        if not url:
            raise ValueError("File URL not found")
        if not filename:
            raise ValueError("File name not found")
        req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest_dir / f"{PREFIX}_{filename}", "wb") as f:
            shutil.copyfileobj(resp, f)

class AddonsManager:
    def __init__(self, addon_type: str, game_dir=None, loader="vanilla", version=None, config_dir=None):
        if addon_type not in PROJECT_TYPE_MAP:
            raise ValueError(f"Unsupported addon_type: {addon_type}")
        self.addon_type = addon_type
        self.game_dir = pathlib.Path(game_dir or self._default_game_dir()).expanduser()
        self.loader = loader.lower()
        self.version = version
        env_cfg = os.environ.get("PALGANIA_LAUNCHER_CONFIG_DIR", "")
        self.config_dir = pathlib.Path(config_dir or env_cfg or self._default_config_dir()).expanduser()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.reqw = ModRinthRequestWrapper()
        self.local_addons_data = self._load_local_addons_data()
        self.local_slug_cache = self._load_local_slug_cache()
        if addon_type == "shaderpacks":
            self.loader = "iris" # force iris loader for shaderpacks
        if addon_type == "resourcepacks":
            self.loader = "vanilla" # force vanilla loader for resourcepacks

    def _load_local_data(self, file_name: str) -> Dict[str, str]:
        """
        Charger les données depuis un fichier JSON
        Retourner un dictionnaire avec les données
        """
        #créer le fichier s'il n'existe pas
        local_data_file = self.config_dir / file_name
        if not local_data_file.exists():
            local_data_file.write_text("{}")
            return {}
        try:
            with open(local_data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        return data
    
    def _load_local_addons_data(self) -> Dict[str, dict]:
        """Charger les données des addons locaux depuis un fichier JSON"""
        return self._load_local_data("local_addons.json")

    def _load_local_slug_cache(self) -> Dict[str, str]:
        """Charger les correspondances keyword/slug depuis un fichier JSON"""
        return self._load_local_data("local_slug_cache.json")

    def _save_local_data(self,data: Dict[str, str], file_name: str):
        """Sauvegarder les données dans un fichier JSON"""
        local_data_file = self.config_dir / file_name
        with open(local_data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _save_local_addons_data(self,data: Dict[str, dict]):
        """Sauvegarder les données des addons locaux dans un fichier JSON"""
        self._save_local_data(data, "local_addons.json")

    def _save_local_slug_cache(self,data: Dict[str, str]):
        """Sauvegarder les correspondances keyword/slug dans un fichier JSON"""
        self._save_local_data(data, "local_slug_cache.json")

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
    
    def _fetch_local_addon(self, slug_or_keyword: str) -> Optional[pathlib.Path]:
        """Fetch a local addon by keyword from the local addons data"""
        slug = self._load_local_slug_cache().get(slug_or_keyword, slug_or_keyword)
        category = LOADER_MAP.get(self.loader, "minecraft")
        for _, data in self.local_addons_data.items():
            if slug == data.get("slug") and self.version in data.get("game_versions", []) and category in data.get("loaders", []):
                file_path = pathlib.Path(data.get("file_path", ""))
                if file_path.exists():
                    return file_path
        return None
    
    def fetch_keyword(self, keyword: str) -> Optional[pathlib.Path]:
        # Retourner le chemin du fichier addon téléchargé/existant
        # ou lever AddonNotFoundError
        category = LOADER_MAP.get(self.loader, "minecraft")
        try: 
            hits = self.reqw.search(
                query=keyword,
                project_type=PROJECT_TYPE_MAP[self.addon_type],
                categories=category,
                facets={"versions": self.version} if self.version else {}
            ).get("hits", [])
            if len(hits) == 0:
                raise AddonNotFoundError(f"No addon found for keyword: {keyword}")
            project = hits[0]
            project_slug = project.get("slug")
            self.local_slug_cache[keyword] = project_slug
            self._save_local_slug_cache(self.local_slug_cache)

            versions = self.reqw.get_versions(
                project_id=project_slug,
                loaders=[category],
                game_versions=[self.version] if self.version else []
            )
            if len(versions) == 0:
                raise AddonNotFoundError(f"No compatible version found for addon: {keyword}")
            version = versions[0]

            files = version.get("files", [])
            if len(files) == 0:
                raise AddonNotFoundError(f"No files found for addon version: {keyword}")
            file = files[0]
            filename = file.get("filename")
            addons_dir = self.game_dir / (f"{self.addon_type}_available")
            addons_dir.mkdir(parents=True, exist_ok=True)
            if filename in self.local_addons_data:
                local_data = self.local_addons_data[filename]
                local_file_path = pathlib.Path(local_data.get("file_path", ""))
                if local_file_path.exists():
                    # Vérifier si la version locale correspond à la version demandée
                    if (local_data.get("version_number") == version.get("version_number") and
                        set(local_data.get("game_versions", [])) == set(version.get("game_versions", [])) and
                        set(local_data.get("loaders", [])) == set(version.get("loaders", []))):
                        return local_file_path

            self.reqw.download_file(file, f"{addons_dir}")
            downloaded_path = addons_dir / f"{PREFIX}_{filename}"
            # Mettre à jour les données locales
            if filename not in self.local_addons_data:
                self.local_addons_data[filename] = {}
            self.local_addons_data[filename] = {
                "file_path": str(downloaded_path),
                "slug": project_slug,
                "game_versions": version.get("game_versions", []),
                "loaders": version.get("loaders", []),
                "version_number": version.get("version_number", ""),
            }
            self._save_local_addons_data(self.local_addons_data)
            return downloaded_path
        except urllib.error.HTTPError as e:
            print(e)
            filename = self._fetch_local_addon(keyword)
            if filename:
                print(f"Using local addon for keyword '{keyword}': {filename}")
                return filename
            raise AddonNotFoundError(f"HTTP Error fetching addon: {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            filename = self._fetch_local_addon(keyword)
            if filename:
                print(f"Using local addon for keyword '{keyword}': {filename}")
                return filename
            raise AddonNotFoundError(f"URL Error fetching addon: {e.reason}")
    
    def install_addons(self, keywords: List[str]) -> List[pathlib.Path]:
        # Installer les addons depuis mods_available vers mods
        # ou lever AddonNotFoundError
        
        # Approche transactionnelle : on télécharge tout dans un dossier temporaire d'abord
        # Si tout réussit, alors on wipe le dossier réel et on déplace.
        
        import tempfile
        
        addons_dir = self.game_dir / self.addon_type
        addons_available_dir = self.game_dir / f"{self.addon_type}_available"
        addons_available_dir.mkdir(parents=True, exist_ok=True)
        addons_dir.mkdir(parents=True, exist_ok=True)

        temp_install_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"palgania_{self.addon_type}_"))
        
        try:
            installed_paths = []
            print(f"Préparation de l'installation des {self.addon_type}...")
            
            # 1. Télécharger ou récupérer tous les addons demandés dans le dossier unique disponible
            # Puis les copier dans le dossier temp
            for keyword in keywords:
                # fetch_keyword télécharge dans _available
                source_path = self.fetch_keyword(keyword)
                if source_path and source_path.exists():
                    dest_path = temp_install_dir / source_path.name
                    shutil.copy2(source_path, dest_path)
                    installed_paths.append(dest_path)
                else:
                    raise AddonNotFoundError(f"Addon not found/downloaded for keyword: {keyword}")
            
            # 2. Si on arrive ici, tous les addons sont prêts dans temp_install_dir.
            # On peut nettoyer le dossier cible (mods/resourcepacks)
            # En ne gardant que ce qu'on veut (ou tout supprimer ? La demande implique une installation propre)
            # Pour la sûreté, on déplace les anciens fichiers dans _available (backup) s'ils ont notre préfixe
            for item in addons_dir.iterdir():
                if item.is_file() and item.name.startswith(PREFIX):
                    try:
                        shutil.move(str(item), str(addons_available_dir / item.name))
                    except shutil.Error:
                        pass # Déjà existant
            
            # 3. Déplacer les nouveaux fichiers depuis temp vers cible
            final_paths = []
            for temp_file in installed_paths:
                final_dest = addons_dir / temp_file.name
                shutil.move(str(temp_file), str(final_dest))
                final_paths.append(final_dest)
                
            return final_paths

        except Exception as e:
            print(f"Abandon de l'installation des addons: {e}")
            raise e
        finally:
            # Nettoyage du dossier temporaire
            if temp_install_dir.exists():
                shutil.rmtree(temp_install_dir, ignore_errors=True)

# am = AddonsManager(addon_type="mods",loader="fabric",version="1.21.11")
# bm = AddonsManager(addon_type="resourcepacks",version="1.21.11")
# cm = AddonsManager(addon_type="shaderpacks",version="1.21.11")