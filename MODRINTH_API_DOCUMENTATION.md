# Documentation API Modrinth v2

## Vue d'ensemble

L'API Modrinth v2 permet de récupérer des informations sur les projets (mods, resourcepacks, shaderpacks) et leurs versions. L'API est gratuite et ne nécessite pas d'authentification pour les requêtes de lecture.

**Base URL:** `https://api.modrinth.com/v2`

**Rate limit:** 300 requêtes par minute par IP

**User-Agent obligatoire:** `palgania-launcher/1.0` ou similaire (requis pour ne pas être bloqué)

---

## 1. Rechercher un projet

### Endpoint
```
GET /search
```

### Paramètres de requête

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `query` | string | ✓ | Mot-clé de recherche (ex: "sodium") |
| `facets` | JSON array | ✗ | Filtres JSON encodés (voir ci-dessous) |
| `limit` | integer | ✗ | Nombre de résultats (défaut: 10, max: 100) |
| `offset` | integer | ✗ | Décalage pour pagination (défaut: 0) |

### Facets disponibles

Les facets permettent de filtrer les résultats avec la syntaxe `"attribut:valeur"` :

```json
[
  ["project_types:mod"],
  ["game_versions:1.21.11"],
  ["loaders:fabric"]
]
```

**Facets courants :**
- `project_types`: `"mod"`, `"resourcepack"`, `"shader"`
- `game_versions`: Version MC (ex: `"1.21.11"`, `"1.21.7"`)
- `loaders`: `"fabric"`, `"forge"`, `"neoforge"`, `"quilt"`, `"minecraft"` (vanilla)
- `environment`: `"client"`, `"server"`, `"both"`

### Exemple de requête

```python
import json
import urllib.parse
import urllib.request

base = "https://api.modrinth.com/v2"
facets = [
    ["project_types:mod"],
    ["game_versions:1.21.11"],
    ["loaders:fabric"]
]
params = {
    "query": "sodium",
    "facets": json.dumps(facets),
    "limit": 5
}
url = f"{base}/search?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(data)
```

### Structure de réponse

```json
{
  "hits": [
    {
      "slug": "sodium",
      "name": "Sodium",
      "description": "Modern rendering engine and client-side optimization mod",
      "project_id": "AANobbMI",
      "id": "AANobbMI",
      "project_type": "mod",
      "display_categories": ["optimization"],
      "downloads": 50000000,
      "follows": 100000,
      "date_created": "2020-08-02T00:00:00Z",
      "date_modified": "2024-12-20T12:00:00Z",
      "latest_version": "mc1.21.11-0.8.2-fabric",
      "color": 4281519,
      "featured_gallery": null,
      "versions": ["1.20.1", "1.21", "1.21.1", "1.21.11"],
      "gallery": [],
      "loaders": ["fabric"],
      "environments": ["client"],
      "created_timestamp": 1596412800000,
      "modified_timestamp": 1734686400000
    }
  ],
  "offset": 0,
  "limit": 5,
  "total_hits": 1
}
```

---

## 2. Obtenir les détails d'un projet

### Endpoint
```
GET /project/{id_or_slug}
```

où `{id_or_slug}` est soit:
- L'ID base62 du projet (ex: `"AANobbMI"`)
- Le slug du projet (ex: `"sodium"`)

### Exemple de requête

```python
url = "https://api.modrinth.com/v2/project/sodium"
req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    project = json.loads(resp.read().decode("utf-8"))
    print(project)
```

### Structure de réponse

```json
{
  "slug": "sodium",
  "id": "AANobbMI",
  "project_type": "mod",
  "name": "Sodium",
  "description": "Modern rendering engine and client-side optimization mod",
  "body": "Detailed markdown description...",
  "body_url": null,
  "published": "2020-08-02T00:00:00Z",
  "updated": "2024-12-20T12:00:00Z",
  "requested_status": null,
  "status": "approved",
  "moderator_message": null,
  "license": {
    "id": "LGPL-3.0-only",
    "name": "GNU Lesser General Public License v3 only",
    "url": "https://opensource.org/licenses/LGPL-3.0-only"
  },
  "client_side": "required",
  "server_side": "optional",
  "downloads": 50000000,
  "follows": 100000,
  "categories": ["optimization"],
  "display_categories": ["optimization"],
  "icon_url": "https://cdn-raw.modrinth.com/data/AANobbMI/icon.png",
  "color": 4281519,
  "organization": null,
  "donation_urls": [...],
  "team": "...",
  "body_url": null,
  "moderator_message": null,
  "source_url": "https://github.com/CaffeineMC/sodium-fabric",
  "wiki_url": null,
  "discord_url": null,
  "issues_url": null,
  "members": [...]
}
```

---

## 3. Lister les versions d'un projet

### Endpoint
```
GET /project/{id_or_slug}/version
```

### Paramètres de requête

| Paramètre | Type | Description |
|-----------|------|-------------|
| `loaders` | JSON array | Filtrer par loader (ex: `["fabric"]`) |
| `game_versions` | JSON array | Filtrer par version MC (ex: `["1.21.11"]`) |

### Exemple de requête avec filtres

```python
facets_params = {
    "loaders": json.dumps(["fabric"]),
    "game_versions": json.dumps(["1.21.11"])
}
qs = urllib.parse.urlencode(facets_params)
url = f"https://api.modrinth.com/v2/project/sodium/version?{qs}"
req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
with urllib.request.urlopen(req, timeout=15) as resp:
    versions = json.loads(resp.read().decode("utf-8"))
    print(versions)
```

### Structure de réponse

```json
[
  {
    "id": "59wygFUQ",
    "project_id": "AANobbMI",
    "author_id": "...",
    "featured": false,
    "name": "Sodium 0.8.2 for Minecraft 1.21.11",
    "version_number": "mc1.21.11-0.8.2-fabric",
    "changelog": "Bug fixes and improvements",
    "changelog_url": null,
    "date_published": "2024-12-15T10:30:00Z",
    "downloads": 500000,
    "version_type": "release",
    "status": "listed",
    "requested_status": null,
    "dependencies": [
      {
        "project_id": "api",
        "project_type": "mod",
        "version_id": null,
        "dependency_type": "required"
      }
    ],
    "loaders": ["fabric", "quilt"],
    "game_versions": ["1.21.11"],
    "files": [
      {
        "hashes": {
          "sha512": "abcd1234...",
          "sha1": "efgh5678..."
        },
        "url": "https://cdn-raw.modrinth.com/data/AANobbMI/versions/59wygFUQ/sodium-fabric-0.8.2%2Bmc1.21.11.jar",
        "filename": "sodium-fabric-0.8.2+mc1.21.11.jar",
        "primary": true,
        "size": 1234567,
        "file_type": null
      }
    ],
    "primary_file": null
  }
]
```

### Points importants

- **`game_versions`** : Array contenant les versions MC supportées par cette version
  - Exemple: `["1.21.11"]` ou `["1.21.6", "1.21.7", "1.21.8"]`
  - **Attention:** Certains mods publient pour `1.21.1` mais restent compatibles avec `1.21.11`
  
- **`loaders`** : Array contenant les mod loaders supportés
  - Exemple: `["fabric", "quilt"]` ou `["forge"]`
  
- **`files`** : Array contenant au minimum un fichier téléchargeable
  - `url`: Lien de téléchargement direct
  - `filename`: Nom du fichier
  - `primary`: `true` pour le fichier principal
  
- **`version_type`** : `"release"`, `"beta"`, ou `"alpha"`
  - Les versions de type "release" sont préférables

---

## 4. Télécharger un fichier

Le champ `files[0].url` contient l'URL de téléchargement direct.

```python
import shutil

url = "https://cdn-raw.modrinth.com/data/AANobbMI/versions/59wygFUQ/sodium-fabric-0.8.2%2Bmc1.21.11.jar"
dest_path = "/path/to/mods/sodium-fabric-0.8.2+mc1.21.11.jar"

req = urllib.request.Request(url, headers={"User-Agent": "palgania-launcher/1.0"})
with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
    shutil.copyfileobj(resp, f)
```

---

## 5. Gestion des erreurs

### Codes HTTP courants

| Code | Signification |
|------|---------------|
| 200 | Succès |
| 400 | Mauvaise requête (paramètres invalides) |
| 404 | Ressource non trouvée (projet inexistant) |
| 429 | Rate limit dépassé (trop de requêtes) |
| 500 | Erreur serveur Modrinth |

### Gestion en Python

```python
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("Projet non trouvé")
    elif e.code == 429:
        print("Rate limit atteint, attendre avant nouvelle requête")
    else:
        print(f"Erreur HTTP {e.code}")
except (urllib.error.URLError, TimeoutError) as e:
    print(f"Erreur réseau: {e}")
```

---

## 6. Cas d'usage courants

### Chercher un mod par keyword et récupérer sa version exacte

```python
def fetch_mod_version(keyword: str, loader: str, mc_version: str) -> dict:
    """Récupère la version exacte d'un mod pour un loader et version MC spécifiques."""
    
    # 1. Chercher le projet
    facets = [
        ["project_types:mod"],
        ["game_versions:" + mc_version],
        ["loaders:" + loader]
    ]
    search_url = f"https://api.modrinth.com/v2/search?{urllib.parse.urlencode({
        'query': keyword,
        'facets': json.dumps(facets),
        'limit': 5
    })}"
    req = urllib.request.Request(search_url, headers={"User-Agent": "palgania-launcher/1.0"})
    hits = json.loads(urllib.request.urlopen(req).read())["hits"]
    
    if not hits:
        raise Exception(f"Mod '{keyword}' non trouvé")
    
    project_id = hits[0]["id"]
    
    # 2. Lister les versions avec filtres
    versions_url = f"https://api.modrinth.com/v2/project/{project_id}/version?" + \
                   urllib.parse.urlencode({
                       "loaders": json.dumps([loader]),
                       "game_versions": json.dumps([mc_version])
                   })
    req = urllib.request.Request(versions_url, headers={"User-Agent": "palgania-launcher/1.0"})
    versions = json.loads(urllib.request.urlopen(req).read())
    
    if not versions:
        raise Exception(f"Aucune version de '{keyword}' pour {loader} {mc_version}")
    
    # 3. Préférer les releases
    for v in versions:
        if v.get("version_type") == "release":
            return v
    
    return versions[0]
```

### Exemple d'utilisation

```python
v = fetch_mod_version("sodium", "fabric", "1.21.11")
print(f"Version: {v['version_number']}")
print(f"MC: {v['game_versions']}")
print(f"Loader: {v['loaders']}")
print(f"URL: {v['files'][0]['url']}")
print(f"Filename: {v['files'][0]['filename']}")
```

---

## 7. Stratégies de sélection de version

### Matching exact (strict)
Télécharger uniquement si `game_versions` contient EXACTEMENT la version cible.
```python
if mc_version in v["game_versions"]:
    # Utiliser cette version
```

### Matching par famille (family)
Accepter les versions publiées pour la même famille majeure.mineure.
```python
def get_family(version: str) -> str:
    parts = version.split(".")
    return ".".join(parts[:2])  # 1.21 pour 1.21.11

target_family = get_family("1.21.11")  # "1.21"
for v in versions:
    for gv in v["game_versions"]:
        if get_family(gv) == target_family:
            # Utiliser cette version
```

**Note:** Le nouveau `addons_manager.py` utilise le matching **EXACT** pour garantir que les mods changent correctement lors d'un changement de version MC.

---

## 8. Structures de données importantes

### Objet Version

```python
Version = {
    "id": str,                          # ID base62 unique
    "project_id": str,                  # ID du projet parent
    "name": str,                        # Nom lisible
    "version_number": str,              # Ex: "mc1.21.11-0.8.2-fabric"
    "version_type": "release|beta|alpha",
    "loaders": List[str],               # Ex: ["fabric", "quilt"]
    "game_versions": List[str],         # Ex: ["1.21.11", "1.21.1"]
    "date_published": str,              # ISO 8601
    "files": List[File],
    "dependencies": List[Dependency]
}

File = {
    "url": str,                         # URL de téléchargement
    "filename": str,
    "size": int,
    "hashes": {
        "sha1": str,
        "sha512": str
    },
    "primary": bool
}
```

---

## 9. Limites et considérations

- **Rate limit:** 300 requêtes/minute par IP
- **Timeout:** Prévoir un timeout de 15s pour les recherches, 60s pour les téléchargements
- **Stabilité:** Prévoir des try/catch autour de toutes les requêtes réseau
- **Cache:** Stocker les métadonnées localement pour éviter les re-requêtes
- **Offline:** Prévoir un fallback vers les fichiers téléchargés précédemment en cas d'erreur réseau

---

## 10. Ressources

- **Docs officielles:** https://docs.modrinth.com/api
- **GitHub API:** https://github.com/modrinth/labrinth
- **Support:** support@modrinth.com
