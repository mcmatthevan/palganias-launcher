import json
import os
import urllib.request
import threading
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

MOJANG_MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
FABRIC_API_URL = "https://meta.fabricmc.net/v2/versions"
FORGE_MAVEN_URL = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
NEOFORGE_MAVEN_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"

CACHE_FILE = "versions_cache.json"

# Fallback versions per loader
FALLBACK_GROUPS = {
    "vanilla": {
        "1.21.x": ["1.21.2", "1.21.1", "1.21"],
        "1.20.x": ["1.20.4", "1.20.3", "1.20.2", "1.20.1", "1.20"],
        "1.19.x": ["1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19"],
        "1.18.x": ["1.18.2", "1.18.1", "1.18"],
        "1.17.x": ["1.17.1", "1.17"],
        "Snapshots": ["24w45a", "24w44a", "24w43a"],
        "Beta": ["b1.7.3", "b1.5_01", "b1.2_02"],
        "Alpha": ["a1.2.6", "a1.1.2_01", "a1.0.17_04"],
    },
    "fabric": {
        "1.21.x": ["1.21.2", "1.21.1", "1.21"],
        "1.20.x": ["1.20.4", "1.20.3", "1.20.2", "1.20.1", "1.20"],
        "1.19.x": ["1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19"],
        "1.18.x": ["1.18.2", "1.18.1", "1.18"],
    },
    "forge": {
        "1.21.x": ["1.21.1"],
        "1.20.x": ["1.20.4", "1.20.3", "1.20.2", "1.20.1"],
        "1.19.x": ["1.19.4", "1.19.3", "1.19.2", "1.19.1"],
        "1.18.x": ["1.18.2", "1.18.1"],
        "1.17.x": ["1.17.1"],
    },
    "neoforge": {
        "1.21.x": ["1.21.1"],
        "1.20.x": ["1.20.4", "1.20.3", "1.20.2", "1.20.1"],
    },
}



def _group_release_version(id_str: str) -> str:
    """Group a version ID into a family like '1.21.x'"""
    parts = id_str.split('.')
    if len(parts) >= 2:
        major = parts[0]
        minor = parts[1]
        return f"{major}.{minor}.x"
    return id_str


def build_groups_vanilla(manifest: Dict) -> Dict[str, List[str]]:
    """Build version groups from Mojang manifest (Vanilla only)"""
    versions = manifest.get("versions", [])
    specials: Dict[str, List[str]] = {
        "Snapshots": [],
        "Beta": [],
        "Alpha": [],
    }
    release_groups: Dict[str, List[str]] = {}
    times: Dict[str, str] = {}

    for v in versions:
        vid = v.get("id", "")
        vtype = v.get("type", "")
        rtime = v.get("releaseTime") or v.get("time") or ""
        if not vid:
            continue
        times[vid] = rtime
        if vtype == "release":
            group = _group_release_version(vid)
            release_groups.setdefault(group, []).append(vid)
        elif vtype == "snapshot":
            specials["Snapshots"].append(vid)
        elif vtype == "old_beta":
            specials["Beta"].append(vid)
        elif vtype == "old_alpha":
            specials["Alpha"].append(vid)

    def sort_by_time(ids: List[str]) -> List[str]:
        return sorted(set(ids), key=lambda i: times.get(i, ""), reverse=True)
    
    def sort_by_version(ids: List[str]) -> List[str]:
        return sorted(set(ids), key=_parse_version_tuple, reverse=True)

    for key in release_groups:
        release_groups[key] = sort_by_version(release_groups[key])
    for key in ["Snapshots", "Beta", "Alpha"]:
        specials[key] = sort_by_time(specials[key])

    def latest_time_for_group(k: str) -> str:
        lst = release_groups.get(k, [])
        return times.get(lst[0], "") if lst else ""

    ordered: Dict[str, List[str]] = {}
    for k in sorted(release_groups.keys(), key=latest_time_for_group, reverse=True):
        ordered[k] = release_groups[k]
    ordered["Snapshots"] = specials["Snapshots"]
    ordered["Beta"] = specials["Beta"]
    ordered["Alpha"] = specials["Alpha"]

    return ordered


def fetch_fabric_versions() -> Dict[str, List[str]]:
    """Fetch Fabric-supported vanilla versions from Fabric API (stable + snapshots)"""
    try:
        with urllib.request.urlopen(f"{FABRIC_API_URL}/game", timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            # The API returns a list of versions with 'version' and 'stable' fields
            versions = data if isinstance(data, list) else data.get("versions", [])
            # Group by version family (both stable and snapshots)
            groups: Dict[str, List[str]] = {}
            snapshots: List[str] = []
            
            for version_data in versions:
                if isinstance(version_data, dict):
                    version_id = version_data.get("version", "")
                    is_stable = version_data.get("stable", False)
                else:
                    continue
                
                if not version_id:
                    continue
                
                # Include both stable and unstable versions
                if is_stable:
                    group = _group_release_version(version_id)
                    groups.setdefault(group, []).append(version_id)
                else:
                    # Collect unstable versions for Snapshots
                    snapshots.append(version_id)
            
            # Sort each group by version number
            for key in groups:
                groups[key] = sorted(set(groups[key]), key=_parse_version_tuple, reverse=True)
            
            # Add snapshots if any exist
            if snapshots:
                groups["Snapshots"] = sorted(set(snapshots), key=_parse_version_tuple, reverse=True)
            
            return groups
    except Exception as e:
        print(f"Failed to fetch Fabric versions: {e}")
        return {}


def fetch_forge_versions(manifest: Dict) -> Dict[str, List[str]]:
    """Extract Forge-supported versions from Mojang manifest (releases + snapshots)"""
    try:
        # Forge works with vanilla versions, so we fetch the Minecraft versions from manifest
        # and filter those that Forge supports
        versions = manifest.get("versions", [])
        supported: Dict[str, List[str]] = {}
        snapshots: List[str] = []
        
        for v in versions:
            vid = v.get("id", "")
            vtype = v.get("type", "")
            
            if not vid:
                continue
            
            if vtype == "release":
                group = _group_release_version(vid)
                supported.setdefault(group, []).append(vid)
            elif vtype == "snapshot":
                # Collect snapshots
                snapshots.append(vid)
        
        for key in supported:
            supported[key] = sorted(set(supported[key]), key=_parse_version_tuple, reverse=True)
        
        # Add snapshots if any exist
        if snapshots:
            supported["Snapshots"] = sorted(set(snapshots), key=_parse_version_tuple, reverse=True)
        
        return supported
    except Exception as e:
        print(f"Failed to fetch Forge versions: {e}")
        return {}


def fetch_neoforge_versions(manifest: Dict) -> Dict[str, List[str]]:
    """NeoForge supports 1.20.1+, filter from Mojang manifest (releases + snapshots)"""
    try:
        versions = manifest.get("versions", [])
        supported: Dict[str, List[str]] = {}
        snapshots: List[str] = []
        
        for v in versions:
            vid = v.get("id", "")
            vtype = v.get("type", "")
            # NeoForge only supports 1.20.1 and later
            vid_tuple = _parse_version_tuple(vid)
            
            if not vid or vid_tuple < (1, 20, 1):
                continue
            
            if vtype == "release":
                group = _group_release_version(vid)
                supported.setdefault(group, []).append(vid)
            elif vtype == "snapshot":
                # Collect snapshots
                snapshots.append(vid)
        
        for key in supported:
            supported[key] = sorted(set(supported[key]), key=_parse_version_tuple, reverse=True)
        
        # Add snapshots if any exist
        if snapshots:
            supported["Snapshots"] = sorted(set(snapshots), key=_parse_version_tuple, reverse=True)
        
        return supported
    except Exception as e:
        print(f"Failed to fetch NeoForge versions: {e}")
        return {}


def _parse_version_tuple(version_str: str) -> Tuple[int, int, int]:
    """Parse a version string like '1.21.11' into a comparable tuple (1, 21, 11)"""
    try:
        # Remove any suffixes like '-pre', '-rc', etc. and just get the numeric parts
        parts = version_str.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2].split('-')[0]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        # Fallback for non-standard versions
        return (0, 0, 0)


def fetch_manifest() -> Dict:
    """Fetch Mojang version manifest"""
    with urllib.request.urlopen(MOJANG_MANIFEST_URL, timeout=10) as resp:
        data = resp.read()
        return json.loads(data.decode('utf-8'))


def load_cache() -> Dict[str, Any]:
    """Load cached versions for all loaders"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict[str, Any]):
    """Save versions cache to file"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_version_groups(loader: str = "vanilla") -> Dict[str, List[str]]:
    """Get version groups for a specific loader, cache-first approach"""
    cache = load_cache()
    
    # If we have cached data for this loader, return it
    if loader in cache:
        cached_loader = cache.get(loader, {})
        if cached_loader and isinstance(cached_loader, dict):
            return cached_loader
    
    # Try to fetch fresh data
    try:
        manifest = fetch_manifest()
        
        if loader == "vanilla":
            groups = build_groups_vanilla(manifest)
        elif loader == "fabric":
            groups = fetch_fabric_versions()
        elif loader == "forge":
            groups = fetch_forge_versions(manifest)
        elif loader == "neoforge":
            groups = fetch_neoforge_versions(manifest)
        else:
            groups = {}
        
        if groups:
            # Update cache and save
            cache[loader] = groups
            save_cache(cache)
            return groups
    except Exception as e:
        print(f"Failed to fetch {loader} versions: {e}")
    
    # Fallback to hardcoded groups
    return FALLBACK_GROUPS.get(loader, {}).copy()


def refresh_version_groups_async(loader: str = "vanilla", callback=None):
    """Async refresh of version groups in background"""
    def _refresh():
        try:
            manifest = fetch_manifest()
            
            if loader == "vanilla":
                groups = build_groups_vanilla(manifest)
            elif loader == "fabric":
                groups = fetch_fabric_versions()
            elif loader == "forge":
                groups = fetch_forge_versions(manifest)
            elif loader == "neoforge":
                groups = fetch_neoforge_versions(manifest)
            else:
                groups = {}
            
            if groups:
                cache = load_cache()
                cache[loader] = groups
                save_cache(cache)
                if callback:
                    callback(groups)
        except Exception as e:
            print(f"Async refresh failed for {loader}: {e}")
    
    thread = threading.Thread(target=_refresh, daemon=True)
    thread.start()

