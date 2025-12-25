# Palgania's Launcher 🎮

Un lanceur Minecraft moderne et léger avec gestion automatique des mods, resource packs et shaders via l'API Modrinth.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-GPL-green.svg)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)

## ✨ Fonctionnalités

### 🎯 Gestion des versions Minecraft
- **Vanilla** : Toutes les versions officielles (release, snapshots, old versions)
- **Loaders moddés** : Fabric, Forge, Neoforge
- Organisation par familles de versions (Latest, 1.21, 1.20, etc.)
- Sélection rapide de la dernière version disponible
- Installation automatique des loaders

### 🔐 Authentification
- **Mode en ligne** : Connexion Microsoft authentique
- **Mode hors ligne** : Comptes crackés avec pseudo/UUID personnalisables
- Gestion multi-comptes avec sauvegarde sécurisée
- Connexion automatique au dernier compte utilisé

### 📦 Gestion des Add-ons (Modrinth)
- **Mods** : Installation automatique compatible avec votre version et loader
- **Resource Packs** : Support complet pour toutes versions
- **Shader Packs** : Détection automatique d'Iris/Optifine
- **Système de cache** : Fonctionnement hors ligne après premier téléchargement
- **Vérification des versions** : Compatibilité automatique loader/version Minecraft
- Syntaxe simple : séparez les noms par des virgules (ex: `sodium, iris, complementary-shaders`)

### 💾 Profils de configuration
- Sauvegarde illimitée de profils personnalisés
- Chargement rapide entre différentes configurations
- Profil "Défaut" toujours à jour avec la dernière version
- Conservation des add-ons et paramètres avancés par profil

### ⚙️ Paramètres avancés
- **Java personnalisé** : Spécifiez votre propre installation Java
- **Arguments JVM** : Optimisez les performances (mémoire, GC, etc.)
- **Répertoire Minecraft** : Choisissez l'emplacement d'installation
- **Quick Play** : Connexion automatique à un serveur ou monde
- **Auto-ajout Palgania** : Ajout automatique du serveur Palgania.ovh

## 🚀 Installation

### Prérequis
- Python 3.11 ou supérieur
- pip (gestionnaire de paquets Python)

### Installation depuis les sources

1. **Cloner le dépôt**
   ```bash
   git clone https://github.com/votre-username/palganias-launcher.git
   cd palganias-launcher
   ```

2. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

3. **Lancer le launcher**
   ```bash
   python main.py
   ```

### Télécharger les binaires compilés

Rendez-vous dans la section [Releases](https://github.com/mcmatthevan/palganias-launcher/releases) pour télécharger l'exécutable correspondant à votre système :
- **Linux** : `PalganiasLauncher-linux`
- **Windows** : `PalganiasLauncher-windows.exe`
- **macOS** : `PalganiasLauncher-macos`

Aucune installation requise, lancez directement l'exécutable !

## 📖 Guide d'utilisation

### Premier lancement

1. **Choisir le mode de jeu**
   - **Mode Hors Ligne** : Saisissez un pseudo (UUID optionnel)
   - **Mode En Ligne** : Cliquez sur "Se Connecter" et suivez les instructions

2. **Configurer la version**
   - Sélectionnez un loader (Vanilla/Fabric/Forge/Neoforge)
   - Choisissez une famille de versions
   - Sélectionnez la version précise ou utilisez "Dernière version"

3. **Ajouter des add-ons** (optionnel)
   - Cliquez sur "Mods/Packs de ressources/Packs de shaders ▼"
   - Saisissez les noms des add-ons séparés par des virgules
   - Exemple : `sodium, iris` dans la section mods

4. **Lancer le jeu**
   - Cliquez sur "🎮 JOUER"
   - Le launcher télécharge et installe automatiquement tout le nécessaire

### Gestion des profils

- **Sauvegarder** : Entrez un nom dans "Nouveau" et cliquez "Sauvegarder Profil"
- **Charger** : Sélectionnez un profil dans le menu déroulant
- **Supprimer** : Sélectionnez un profil et cliquez "Supprimer Profil"

### Paramètres avancés

Cliquez sur ⚙️ pour accéder aux options avancées :

- **Chemin Java** : `/usr/lib/jvm/java-21-openjdk/bin/java` (sur Linux)
- **Répertoire Minecraft** : `~/.minecraft` (par défaut sur linux)
- **Arguments JVM** : `-Xmx4G -XX:+UseG1GC` (exemple pour 4 Go de RAM)
- **Quick Play Serveur** : `palgania.ovh:25565`
- **Quick Play Monde** : `Mon Monde` (nom du monde solo)

## 🛠️ Architecture technique

### Stack technologique
- **Interface** : [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - UI moderne
- **Launcher Core** : [PortableMC](https://github.com/mindstorm38/portablemc) - Gestion Minecraft
- **API Mods** : [Modrinth API v2](https://docs.modrinth.com/api-spec/) - Téléchargement add-ons
- **Authentification** : Microsoft Azure OAuth 2.0

### Modules principaux

```
palganias-launcher/
├── main.py                          # Interface graphique et logique principale
├── addons_manager.py                # Gestion des add-ons Modrinth
├── versions.py                      # Récupération des versions Minecraft
├── requirements.txt                 #  Configuration PyInstaller
└── .github/workflows/build.yml     # CI/CD automatique
```

### Système de cache add-ons

Le launcher utilise un système de cache intelligent :
- `local_addons.json` : Métadonnées des add-ons téléchargés
- Fonctionnement hors ligne après premier téléchargement
- Vérification automatique de compatibilité version/loader
- Préfixe `palgania_launcher_*` pour identification des fichiers

## 🔧 Développement

### Structure du code

**addons_manager.py**
- `ModRinthRequestWrapper` : Abstraction de l'API Modrinth
- `AddonsManager` : Gestion du téléchargement et installation
- Support du mode hors ligne avec cache local

**main.py**
- `App` : Classe principale de l'interface
- `InstallWatcher` : Suivi de progression des téléchargements
- `AdvancedSettingsWindow` : Fenêtre des paramètres avancés

**versions.py**
- `get_version_groups()` : Récupération dynamique des versions
- Support multi-loader (Vanilla, Fabric, Forge, Neoforge)

## 🐛 Problèmes connus

### Neoforge 1.21.x
Problème `KeyError: 'ROOT'` avec Neoforge sur versions 1.21+. Solutions :
- Utiliser Forge à la place
- Utiliser Fabric (recommandé pour mods récents)
- Utiliser une version antérieure (1.20.x)

### Rate limit Modrinth
L'API Modrinth limite à 300 requêtes/minute. En cas de dépassement :
- Le launcher utilise automatiquement le cache local
- Attendez 1 minute avant de réessayer
- Évitez de lancer plusieurs instances simultanément

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. Fork le projet
2. Créez une branche (`git checkout -b feature/amelioration`)
3. Committez vos changements (`git commit -m 'Ajout fonctionnalité'`)
4. Poussez vers la branche (`git push origin feature/amelioration`)
5. Ouvrez une Pull Request

## 📄 Licence

Ce projet est sous licence GPL. Voir [LICENSE](LICENSE) pour plus de détails.

## 🙏 Remerciements

- [PortableMC](https://github.com/mindstorm38/portablemc) - Core du launcher
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Interface moderne
- [Modrinth](https://modrinth.com/) - API des add-ons
- Communauté Minecraft pour le support

## 📧 Contact

- **Discord** : Rejoignez le serveur Palgania - `palgania.ovh`
- **Issues** : [GitHub Issues](https://github.com/mcmatthevan/palganias-launcher/issues)

---

**Fait avec ❤️ pour la communauté Palgania**
**et aussi pour les autres !**
