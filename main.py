import customtkinter as ctk
import json
import os
import sys
from PIL import Image, ImageTk
from versions import get_version_groups, refresh_version_groups_async
from tkinter import filedialog, messagebox
import shlex
from portablemc.standard import (
    Version, Context, Watcher,
    VersionLoadingEvent, VersionFetchingEvent, VersionLoadedEvent,
    FeaturesEvent, JarFoundEvent, 
    AssetsResolveEvent, 
    LibrariesResolvingEvent, LibrariesResolvedEvent,
    LoggerFoundEvent,
    JvmLoadingEvent, JvmLoadedEvent,
    DownloadStartEvent, DownloadProgressEvent, DownloadCompleteEvent,
    XmlStreamEvent
)
from portablemc.auth import (
    AuthDatabase, AuthSession, OfflineAuthSession, 
    MicrosoftAuthSession, AuthError
)
from portablemc.forge import ForgeVersion, _NeoForgeVersion
from portablemc.fabric import FabricVersion
import pathlib
import logging
from datetime import datetime
import webbrowser
import urllib.parse
import urllib.error
from uuid import uuid4
import struct
import threading
from addons_manager import AddonsManager, AddonNotFoundError
from typing import Optional
import sys
import platform

# Configuration
def _default_config_dir() -> pathlib.Path:
    system = platform.system().lower()
    home = pathlib.Path.home()
    if system == "windows":
        return home / "AppData/Local/palgania_launcher"
    if system == "darwin":
        return home / "Library/Application Support/palgania_launcher"
    return home / ".palgania_launcher"

def _parse_config_dir_arg(argv: list[str]) -> Optional[pathlib.Path]:
    for arg in argv:
        if arg.startswith("--config-dir="):
            path_str = arg.split("=", 1)[1]
            if path_str:
                return pathlib.Path(os.path.expanduser(path_str))
    return None


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_DIR = _parse_config_dir_arg(sys.argv) or _default_config_dir()
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ["PALGANIA_LAUNCHER_CONFIG_DIR"] = str(CONFIG_DIR)

PROFILES_FILE = str(CONFIG_DIR / "profiles.json")
LOGO_FILE = resource_path("logo128x128.png")
LOG_FILE = str(CONFIG_DIR / "palgania-launcher.latest.log")
AUTH_DATABASE_FILE = str(CONFIG_DIR / "portablemc_auth.json")
LAST_ACCOUNT_FILE = str(CONFIG_DIR / "last_account.txt")
LAST_PROFILE_FILE = str(CONFIG_DIR / "last_profile.txt")
MICROSOFT_AZURE_APP_ID = "708e91b5-99f8-4a1d-80ec-e746cbb24771"  # App ID du CLI portablemc

# Loader mapping for version groups
LOADER_MAP = {
    "Vanilla": "vanilla",
    "Fabric": "fabric",
    "Forge": "forge",
    "Neoforge": "neoforge"
}

VERSION_GROUPS = get_version_groups("vanilla")

# Configuration du logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filemode='w'  # Écrase le fichier à chaque démarrage
)
logger = logging.getLogger(__name__)

class InstallWatcher(Watcher):
    """Moniteur d'installation pour afficher la progression dans l'UI et le log."""
    
    def __init__(self, app):
        super().__init__()
        self.app = app  # Référence à l'application pour mettre à jour l'UI
        self.download_size = 0
        self.download_total = 0
        self.entries_count = 0
        
    def handle(self, event):
        """Gère les événements d'installation avec affichage adapté et journalisation."""
        
        # === Version Events ===
        if isinstance(event, VersionLoadingEvent):
            msg = f"Chargement de la version {event.version}..."
            logger.info(f"VersionLoadingEvent: {event.version}")
            self._update_status(msg)
            
        elif isinstance(event, VersionFetchingEvent):
            msg = f"Téléchargement des métadonnées de {event.version}..."
            logger.info(f"VersionFetchingEvent: {event.version}")
            self._update_status(msg)
            
        elif isinstance(event, VersionLoadedEvent):
            msg = f"Version {event.version} {'téléchargée' if event.fetched else 'chargée'}"
            logger.info(f"VersionLoadedEvent: {event.version} (fetched={event.fetched})")
            self._update_status(msg, success=True)
            
        # === Features Event ===
        elif isinstance(event, FeaturesEvent):
            msg = f"Fonctionnalités: {', '.join(event.features) if event.features else 'aucune'}"
            logger.info(f"FeaturesEvent: {event.features}")
            self._update_status(msg, info=True)
            
        # === JAR Event ===
        elif isinstance(event, JarFoundEvent):
            msg = "Fichier JAR du jeu trouvé"
            logger.info("JarFoundEvent")
            self._update_status(msg, success=True)
            
        # === Assets Events ===
        elif isinstance(event, AssetsResolveEvent):
            if event.count is None:
                msg = f"Vérification des assets (index {event.index_version})..."
                logger.info(f"AssetsResolveEvent: resolving index {event.index_version}")
            else:
                msg = f"Assets vérifiés: {event.count} fichiers (index {event.index_version})"
                logger.info(f"AssetsResolveEvent: resolved {event.count} assets (index {event.index_version})")
            self._update_status(msg, success=(event.count is not None))
            
        # === Libraries Events ===
        elif isinstance(event, LibrariesResolvingEvent):
            msg = "Vérification des bibliothèques..."
            logger.info("LibrariesResolvingEvent")
            self._update_status(msg)
            
        elif isinstance(event, LibrariesResolvedEvent):
            msg = f"Bibliothèques vérifiées: {event.class_libs_count} classpath, {event.native_libs_count} natives"
            logger.info(f"LibrariesResolvedEvent: {event.class_libs_count} class libs, {event.native_libs_count} native libs")
            self._update_status(msg, success=True)
            
        # === Logger Event ===
        elif isinstance(event, LoggerFoundEvent):
            msg = f"Logger configuré: {event.version}"
            logger.info(f"LoggerFoundEvent: {event.version}")
            self._update_status(msg, info=True)
            
        # === JVM Events ===
        elif isinstance(event, JvmLoadingEvent):
            msg = "Chargement de la JVM..."
            logger.info("JvmLoadingEvent")
            self._update_status(msg)
            
        elif isinstance(event, JvmLoadedEvent):
            kind_label = {
                JvmLoadedEvent.MOJANG: "Mojang",
                JvmLoadedEvent.BUILTIN: "système",
                JvmLoadedEvent.CUSTOM: "personnalisée"
            }.get(event.kind, event.kind)
            version_str = f" {event.version}" if event.version else ""
            msg = f"JVM chargée: {kind_label}{version_str}"
            logger.info(f"JvmLoadedEvent: kind={event.kind}, version={event.version}")
            self._update_status(msg, success=True)
            
        # === Download Events ===
        elif isinstance(event, DownloadStartEvent):
            self.download_total = event.size
            self.entries_count = event.entries_count
            self.download_size = 0
            msg = f"Téléchargement de {event.entries_count} fichiers ({self._format_size(event.size)})..."
            logger.info(f"DownloadStartEvent: {event.entries_count} entries, {event.size} bytes, {event.threads_count} threads")
            self._update_status(msg)
            self._show_progress_bar()
            self._update_progress(0)
            
        elif isinstance(event, DownloadProgressEvent):
            # Mise à jour de la barre de progression
            if event.done:
                self.download_size += event.size
            
            progress = (self.download_size / self.download_total * 100) if self.download_total > 0 else 0
            msg = f"Téléchargement: {event.count}/{self.entries_count} ({self._format_size(self.download_size)}/{self._format_size(self.download_total)}) - {self._format_size(event.speed)}/s"
            
            # Log périodiquement (tous les 10 fichiers pour éviter de saturer)
            if event.done and event.count % 10 == 0:
                logger.info(f"DownloadProgressEvent: {event.count}/{self.entries_count} files, {event.speed:.1f} B/s")
            
            self._update_status(msg, progress=True)
            self._update_progress(progress)
            
        elif isinstance(event, DownloadCompleteEvent):
            msg = f"Téléchargement terminé: {self.entries_count} fichiers ({self._format_size(self.download_size)})"
            logger.info("DownloadCompleteEvent")
            self._update_status(msg, success=True)
            self._update_progress(100)
            # Masquer la barre après un court délai pour voir la complétion
            self.app.after(1500, self._hide_progress_bar)
            
        # === Game Stream Event (logs du jeu) ===
        elif isinstance(event, XmlStreamEvent):
            # Log uniquement les événements importants (warnings/errors)
            if event.level in ("WARN", "ERROR", "FATAL"):
                logger.warning(f"GameLog [{event.level}] {event.logger}: {event.message}")
            # Info optionnel (décommentez si vous voulez tous les logs du jeu)
            # else:
            #     logger.debug(f"GameLog [{event.level}] {event.logger}: {event.message}")
        
        # === Unknown Event ===
        else:
            logger.debug(f"Unknown event: {type(event).__name__}")
    
    def _update_status(self, message, success=False, info=False, progress=False):
        """Met à jour le message de statut dans l'UI (thread-safe)."""
        def _do_update():
            if hasattr(self.app, 'status_label'):
                # Choisir la couleur selon le type de message
                if success:
                    color = "#4CAF50"  # Vert
                elif info:
                    color = "#2196F3"  # Bleu
                elif progress:
                    color = "#FF9800"  # Orange
                else:
                    color = "gray"  # Gris par défaut
                
                self.app.status_label.configure(text=message, text_color=color)
                # update_idletasks non nécessaire si appelé via after
        
        self.app.after(0, _do_update)
    
    def _update_progress(self, percent):
        """Met à jour la barre de progression (thread-safe)."""
        def _do_update():
            if hasattr(self.app, 'progress_bar'):
                self.app.progress_bar.set(percent / 100)
        
        self.app.after(0, _do_update)
    
    def _show_progress_bar(self):
        """Affiche la barre de progression (thread-safe)."""
        def _do_show():
            if hasattr(self.app, 'progress_bar'):
                self.app.progress_bar.pack(fill="x", padx=10, pady=5)
        
        self.app.after(0, _do_show)
    
    def _hide_progress_bar(self):
        """Masque la barre de progression (thread-safe)."""
        def _do_hide():
            if hasattr(self.app, 'progress_bar'):
                self.app.progress_bar.pack_forget()
        
        self.app.after(0, _do_hide)
    
    def _format_size(self, bytes_size):
        """Formate une taille en bytes en unités lisibles."""
        for unit in ['o', 'Ko', 'Mo', 'Go']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} To"

class AdvancedSettingsWindow(ctk.CTkToplevel):
    """
    Fenêtre pour les paramètres avancés"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Paramètres Avancés")
        self.resizable(True, True)
        
        # Chemin vers Java
        ctk.CTkLabel(self, text="Chemin vers Java (optionnel):", font=("Arial", 12, "bold")).pack(padx=20, pady=(20, 5))
        java_frame = ctk.CTkFrame(self)
        java_frame.pack(padx=20, pady=5, fill="x")
        self.java_path = ctk.CTkEntry(java_frame, placeholder_text="Chemin vers l'exécutable Java...")
        self.java_path.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(java_frame, text="Parcourir", command=self.browse_java_path, width=100).pack(side="left")

        # Répertoire Minecraft (optionnel)
        ctk.CTkLabel(self, text="Répertoire Minecraft (optionnel):", font=("Arial", 12, "bold")).pack(padx=20, pady=(10, 5))
        mc_frame = ctk.CTkFrame(self)
        mc_frame.pack(padx=20, pady=5, fill="x")
        self.mc_data_dir = ctk.CTkEntry(mc_frame, placeholder_text="Chemin du répertoire Minecraft...")
        self.mc_data_dir.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(mc_frame, text="Parcourir", command=self.browse_mc_data_dir, width=100).pack(side="left")
        
        # JVM Arguments
        ctk.CTkLabel(self, text="Arguments JVM:", font=("Arial", 12, "bold")).pack(padx=20, pady=(15, 5))
        self.jvm_args = ctk.CTkTextbox(self, height=80)
        self.jvm_args.pack(padx=20, pady=5, fill="both", expand=False)
        
        # Quickplay - Serveur et Port
        ctk.CTkLabel(self, text="Quickplay - Serveur:", font=("Arial", 12, "bold")).pack(padx=20, pady=(15, 5))
        server_frame = ctk.CTkFrame(self)
        server_frame.pack(padx=20, pady=5, fill="x")
        self.quickplay_server = ctk.CTkEntry(server_frame, placeholder_text="Adresse du serveur (optionnel)")
        self.quickplay_server.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(server_frame, text="Port:", width=50).pack(side="left", padx=(0, 5))
        self.quickplay_port = ctk.CTkEntry(server_frame, placeholder_text="25565", width=80)
        self.quickplay_port.pack(side="left")
        self.quickplay_port.insert(0, "25565")
        
        # Quickplay - Monde solo
        ctk.CTkLabel(self, text="Quickplay - Monde Solo:", font=("Arial", 12, "bold")).pack(padx=20, pady=(15, 5))
        self.quickplay_world = ctk.CTkEntry(self, placeholder_text="Nom du monde (optionnel)")
        self.quickplay_world.pack(padx=20, pady=5, fill="x")
        
        # Ajouter automatiquement Palgania
        ctk.CTkLabel(self, text="Serveur Palgania:", font=("Arial", 12, "bold")).pack(padx=20, pady=(15, 5))
        self.auto_add_palgania = ctk.CTkCheckBox(self, text="Ajouter automatiquement Palgania à la liste des serveurs")
        self.auto_add_palgania.pack(padx=20, pady=5, anchor="w")
        
        # Boutons
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(padx=20, pady=20, fill="x")
        ctk.CTkButton(button_frame, text="Fermer", command=self.destroy).pack(side="right", padx=5)
        
        # Charger les paramètres existants
        self.load_settings()
        self._setup_auto_save()
        self.after(50, self._fit_to_content)
    
    def browse_java_path(self):
        """Ouvrir un explorateur de fichiers pour sélectionner Java"""
        self.lift()  # Mettre la fenêtre au premier plan
        self.attributes('-topmost', True)  # Forcer au premier plan temporairement
        self.after(100, lambda: self.attributes('-topmost', False))  # Désactiver après 100ms
        
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Sélectionner l'exécutable Java",
            filetypes=[
                ("Tous les fichiers", "*.*"),
                ("Exécutables", "*.exe" if os.name == 'nt' else "*")
            ]
        )
        if file_path:
            self.java_path.delete(0, "end")
            self.java_path.insert(0, file_path)
            self.save_settings()
    
    def browse_mc_data_dir(self):
        """Ouvrir un explorateur de fichiers pour sélectionner le répertoire Minecraft"""
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))

        mc_dir = filedialog.askdirectory(
            parent=self,
            title="Sélectionner le répertoire Minecraft"
        )
        if mc_dir:
            self.mc_data_dir.delete(0, "end")
            self.mc_data_dir.insert(0, mc_dir)
            self.save_settings()
    
    def save_settings(self):
        """Sauvegarder les paramètres avancés"""
        self.parent.advanced_settings = {
            "java_path": self.java_path.get(),
            "mc_data_dir": self.mc_data_dir.get(),
            "jvm_args": self.jvm_args.get("1.0", "end-1c"),
            "quickplay_server": self.quickplay_server.get(),
            "quickplay_port": self.quickplay_port.get(),
            "quickplay_world": self.quickplay_world.get(),
            "auto_add_palgania": self.auto_add_palgania.get()
        }
        # Sauvegarde automatique sans fermer la fenêtre
    
    def load_settings(self):
        """Charger les paramètres avancés depuis le parent"""
        if hasattr(self.parent, 'advanced_settings'):
            settings = self.parent.advanced_settings
            self.java_path.insert(0, settings.get("java_path", ""))
            self.mc_data_dir.insert(0, settings.get("mc_data_dir", ""))
            self.jvm_args.insert("1.0", settings.get("jvm_args", ""))
            self.quickplay_server.insert(0, settings.get("quickplay_server", ""))
            
            port = settings.get("quickplay_port", "25565")
            self.quickplay_port.delete(0, "end")
            self.quickplay_port.insert(0, port)
            
            self.quickplay_world.insert(0, settings.get("quickplay_world", ""))
            
            # Cocher par défaut
            if settings.get("auto_add_palgania", True):
                self.auto_add_palgania.select()
            else:
                self.auto_add_palgania.deselect()

    def _setup_auto_save(self):
        """Enregistrer automatiquement à chaque saisie"""
        entries = [
            self.java_path,
            self.mc_data_dir,
            self.quickplay_server,
            self.quickplay_port,
            self.quickplay_world,
        ]
        for widget in entries:
            widget.bind("<KeyRelease>", lambda _evt: self.save_settings())

        # Le Text nécessite un handler dédié
        self.jvm_args.bind("<<Modified>>", self._on_jvm_modified)
        
        # Checkbox auto-save
        self.auto_add_palgania.configure(command=self.save_settings)

    def _on_jvm_modified(self, event):
        """Déclenche l'auto-save quand le texte JVM change"""
        if self.jvm_args.edit_modified():
            self.jvm_args.edit_modified(False)
            self.save_settings()

    def _fit_to_content(self):
        """Adapter la taille de la fenêtre au contenu"""
        self.update_idletasks()
        padding_w = 40
        padding_h = 40
        w = max(self.winfo_reqwidth() + padding_w, 480)
        h = max(self.winfo_reqheight() + padding_h, 360)
        self.minsize(w, h)
        self.geometry(f"{w}x{h}")

class VersionSelectDialog(ctk.CTkToplevel):
    """Fenêtre de sélection de version avec scroll pour les longues listes (ex: Snapshots)."""
    def __init__(self, parent, title, versions, current, on_select_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.resizable(True, True)
        self.minsize(480, 420)
        self.selection = current
        self.on_select_callback = on_select_callback

        ctk.CTkLabel(self, text=title, font=("Arial", 14, "bold")).pack(padx=16, pady=(16, 8), anchor="w")
        # Message de chargement
        self.loading_label = ctk.CTkLabel(self, text="Veuillez patienter…", font=("Arial", 12))
        self.loading_label.pack(padx=16, pady=(4, 8), anchor="w")
        # Cadre scrollable
        self.scroll = ctk.CTkScrollableFrame(self, width=420, height=320)
        self.scroll.pack(padx=16, pady=8, fill="both", expand=True)

        # Remplir après un court délai pour laisser l'UI respirer
        self.after(100, lambda: self._populate(versions))

        # Boutons d'action (Annuler uniquement)
        action = ctk.CTkFrame(self)
        action.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(action, text="Annuler", command=self._cancel).pack(side="right", padx=6)

        self.after(50, self._fit)

    def _populate(self, versions):
        for v in versions:
            btn = ctk.CTkButton(self.scroll, text=v, width=360,
                                command=lambda vv=v: self._choose_and_close(vv))
            btn.pack(pady=4)
        # Retirer le message de chargement
        try:
            self.loading_label.pack_forget()
        except Exception:
            pass

    def _choose_and_close(self, value):
        # Sélectionner et fermer immédiatement
        self.selection = value
        if self.selection:
            self.parent.version.set(self.selection)
            try:
                self.parent.version_combo.set(self.selection)
            except Exception:
                pass
        # Appeler le callback pour mettre à jour le label
        if self.on_select_callback:
            self.on_select_callback()
        self.destroy()

    def _cancel(self):
        self.destroy()

    def _fit(self):
        self.update_idletasks()
        w = max(self.winfo_reqwidth() + 24, 480)
        h = max(self.winfo_reqheight() + 24, 420)
        self.minsize(w, h)
        self.geometry(f"{w}x{h}")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Palgania's launcher")
        self.resizable(True, True)
        self._set_window_icon()
        
        # Base de données d'authentification
        self.auth_db = AuthDatabase(pathlib.Path(AUTH_DATABASE_FILE))
        self.auth_db.load()
        self.auth_session = None  # Session d'authentification active
        self.logged_email = ctk.StringVar(value="")  # Email du compte connecté
        
        # Variables
        self.online_mode = ctk.BooleanVar(value=True)
        self.loader = ctk.StringVar(value="Vanilla")
        
        # Load initial version groups for vanilla loader
        self.version_groups = get_version_groups("vanilla")
        
        # Choisir une famille et version par défaut depuis les groupes dynamiques
        default_group = next(iter(self.version_groups.keys()))
        default_versions = self.version_groups.get(default_group, ["1.21.2"])
        self.version_group = ctk.StringVar(value=default_group)
        self.version = ctk.StringVar(value=default_versions[0] if default_versions else "")
        self.profile_name = ctk.StringVar(value="Défaut")
        self.pseudo = ctk.StringVar(value="")
        self.uuid = ctk.StringVar(value="")
        # Auto-save guard for assets text updates
        self._suspend_assets_autosave = False
        # Champs pour packs/mods/shaders (mots-clés séparés par des virgules)
        self.resource_packs_keywords = ctk.StringVar(value="")
        self.mods_keywords = ctk.StringVar(value="")
        self.shader_packs_keywords = ctk.StringVar(value="")
        # État de la section extensible
        self.assets_section_expanded = False
        # Références UI pour la section extensible
        self.assets_toggle_btn = None
        self.assets_frame = None
        self.resource_packs_frame = None
        self.resource_packs_text = None
        self.mods_frame = None
        self.mods_text = None
        self.shader_frame = None
        self.shader_text = None
        
        # Versions dynamiques (cache d'abord, puis rafraîchissement asynchrone)

        # Paramètres avancés
        self.advanced_settings = {
            "java_path": "",
            "mc_data_dir": "",
            "jvm_args": "",
            "quickplay_server": "",
            "quickplay_port": "25565",
            "quickplay_world": "",
            "auto_add_palgania": True
        }
        
        self.profiles = self.load_profiles()
        
        # Télécharger et afficher le logo
        self.setup_ui()
        self.after(50, self._fit_main_to_content)
        # Charger le dernier profil utilisé si ce n'est pas "Défaut"
        self._load_last_profile()
        # Connexion automatique au dernier compte utilisé
        self.after(100, self._auto_connect_last_account)
        # Rafraîchir la liste des versions en arrière-plan et mettre à jour l'UI
        self._refresh_versions_async()
        
    def _set_window_icon(self):
        """Définir l'icône de la fenêtre à partir du logo."""
        try:
            if os.path.exists(LOGO_FILE):
                img = Image.open(LOGO_FILE)
                icon = ImageTk.PhotoImage(img)
                # Conserver une référence pour éviter la collecte
                self._icon_image_ref = icon
                self.iconphoto(False, icon)
            else:
                logger.warning("Logo introuvable pour l'icône: %s", LOGO_FILE)
        except Exception as exc:
            logger.warning("Impossible de définir l'icône de fenêtre: %s", exc)

    def setup_ui(self):
        """Configurer l'interface utilisateur"""
        # Frame principal avec logo et contenu
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Header avec logo et titre
        header_frame = ctk.CTkFrame(main_frame)
        header_frame.pack(fill="x", padx=10, pady=(10, 20))
        
        # Logo (charger depuis le fichier local)
        logo_frame = ctk.CTkFrame(header_frame)
        logo_frame.pack(side="left", padx=(0, 20))
        
        try:
            # Charger le logo local
            if os.path.exists(LOGO_FILE):
                image_data = Image.open(LOGO_FILE)
                
                # Redimensionner le logo
                image_data = image_data.resize((100, 100), Image.Resampling.LANCZOS)
                self.logo_image = ctk.CTkImage(light_image=image_data, size=(100, 100))
                
                logo_label = ctk.CTkLabel(logo_frame, image=self.logo_image, text="")
                logo_label.pack()
            else:
                print(f"Erreur : Fichier de logo introuvable à l'emplacement {LOGO_FILE}")
                ctk.CTkLabel(logo_frame, text="Logo", font=("Arial", 20)).pack()
        except Exception as e:
            print(f"Impossible de charger le logo: {e}")
            ctk.CTkLabel(logo_frame, text="Logo", font=("Arial", 20)).pack()
        
        # Titre
        title_frame = ctk.CTkFrame(header_frame)
        title_frame.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(title_frame, text="Palgania's Launcher", font=("Arial", 28, "bold")).pack(anchor="w")
        ctk.CTkLabel(title_frame, text="Lancez l'aventure", font=("Arial", 12, "bold")).pack(anchor="w")
        
        # Bouton paramètres avancés (roue)
        settings_btn = ctk.CTkButton(header_frame, text="⚙️", width=50, height=50, 
                                     command=self.open_advanced_settings, font=("Arial", 20))
        settings_btn.pack(side="right", padx=10)
        
        # Contenu principal (deux colonnes)
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill="both", expand=True)
        # Colonnes gauche et droite
        left_column = ctk.CTkFrame(content_frame)
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right_column = ctk.CTkFrame(content_frame)
        right_column.pack(side="left", fill="both", expand=True)
        
        # Section 1: Mode de jeu
        section1 = ctk.CTkFrame(left_column)
        section1.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(section1, text="Mode de Jeu", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))
        
        mode_frame = ctk.CTkFrame(section1)
        mode_frame.pack(fill="x")
        
        ctk.CTkRadioButton(mode_frame, text="Mode Hors Ligne (Compte Cracké)", 
                          variable=self.online_mode, value=False,
                          command=self.update_ui).pack(anchor="w", padx=10)
        
        online_radio = ctk.CTkRadioButton(mode_frame, text="Mode En Ligne", 
                                         variable=self.online_mode, value=True,
                                         command=self.update_ui)
        online_radio.pack(anchor="w", padx=10)
        
        # Bouton de connexion avec label dynamique
        connect_frame = ctk.CTkFrame(mode_frame)
        connect_frame.pack(anchor="w", padx=30, pady=(5, 0), fill="x")
        
        self.connect_btn = ctk.CTkButton(connect_frame, text="Se Connecter", 
                                        command=self.connect_account, width=150)
        self.connect_btn.pack(side="left")
        
        self.connect_status_label = ctk.CTkLabel(
            connect_frame,
            textvariable=self.logged_email,
            text_color="#4CAF50",
            font=("Arial", 11)
        )
        self.connect_status_label.pack(side="left", padx=10)
        
        # Champs pour mode hors ligne
        self.offline_frame = ctk.CTkFrame(mode_frame)
        
        # Pseudo
        pseudo_subframe = ctk.CTkFrame(self.offline_frame)
        pseudo_subframe.pack(fill="x", pady=5)
        ctk.CTkLabel(pseudo_subframe, text="Pseudo:", width=120, anchor="w").pack(side="left")
        self.pseudo_entry = ctk.CTkEntry(pseudo_subframe, textvariable=self.pseudo, placeholder_text="Entrez votre pseudo", width=200)
        self.pseudo_entry.pack(side="left", padx=10)
        
        # UUID
        uuid_subframe = ctk.CTkFrame(self.offline_frame)
        uuid_subframe.pack(fill="x", pady=5)
        ctk.CTkLabel(uuid_subframe, text="UUID:", width=120, anchor="w").pack(side="left")
        self.uuid_entry = ctk.CTkEntry(uuid_subframe, textvariable=self.uuid, placeholder_text="Entrez votre UUID (optionnel)", width=200)
        self.uuid_entry.pack(side="left", padx=10)
        
        # Section 2: Loader et Version
        section2 = ctk.CTkFrame(left_column)
        section2.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(section2, text="Configuration du Jeu", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))
        
        config_frame = ctk.CTkFrame(section2)
        config_frame.pack(fill="x")
        
        # Loader
        loader_subframe = ctk.CTkFrame(config_frame)
        loader_subframe.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(loader_subframe, text="Type de Loader:", width=120, anchor="w").pack(side="left")
        loader_combo = ctk.CTkComboBox(loader_subframe, variable=self.loader,
                                       values=["Vanilla", "Fabric", "Forge", "Neoforge"],
                                       state="readonly", width=200,
                                       command=self.on_loader_change)
        loader_combo.pack(side="left", padx=10)
        
        # Version
        version_subframe = ctk.CTkFrame(config_frame)
        version_subframe.pack(fill="x", padx=10, pady=5)

        # Niveau 1 : groupe
        ctk.CTkLabel(version_subframe, text="Famille:", width=120, anchor="w").pack(side="left")
        self.version_group_combo = ctk.CTkComboBox(
            version_subframe,
            variable=self.version_group,
            values=list(self.version_groups.keys()),
            state="readonly",
            width=180,
            command=self.on_version_group_change,
        )
        self.version_group_combo.pack(side="left", padx=10)

        # Niveau 2 : version précise
        ctk.CTkLabel(version_subframe, text="Version:", width=80, anchor="w").pack(side="left")
        self.version_combo = ctk.CTkComboBox(
            version_subframe,
            variable=self.version,
            values=self.version_groups.get(self.version_group.get(), []),
            state="readonly",
            width=160,
        )
        self.version_combo.pack(side="left", padx=10)
        # Bouton alternatif pour Snapshots (liste très longue)
        self.version_select_btn = ctk.CTkButton(
            version_subframe,
            text="Choisir…",
            width=100,
            command=self._open_version_dialog
        )
        # non packé par défaut; affiché dynamiquement pour Snapshots
        # Label pour afficher la version snapshot sélectionnée
        self.version_select_label = ctk.CTkLabel(
            version_subframe,
            text="",
            text_color="gray",
            font=("Arial", 11)
        )
        # non packé par défaut; affiché dynamiquement pour Snapshots
        
        # Bouton pour sélectionner la dernière version disponible
        self.latest_version_btn = ctk.CTkButton(
            version_subframe,
            text="🆕 Dernière version",
            width=140,
            command=self.select_latest_version,
            fg_color="#2196F3",
            hover_color="#1976D2"
        )
        self.latest_version_btn.pack(side="left", padx=10)
        
        # Section 3: Profils
        section3 = ctk.CTkFrame(left_column)
        section3.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(section3, text="Profils de Configuration", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))
        
        profiles_frame = ctk.CTkFrame(section3)
        profiles_frame.pack(fill="x")
        
        profiles_subframe1 = ctk.CTkFrame(profiles_frame)
        profiles_subframe1.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(profiles_subframe1, text="Profil:", width=120, anchor="w").pack(side="left")
        self.profile_combo = ctk.CTkComboBox(profiles_subframe1, variable=self.profile_name,
                                        values=list(self.profiles.keys()),
                                        state="readonly", width=200,
                                        command=self.on_profile_select)
        self.profile_combo.pack(side="left", padx=10)
        
        # Champ pour nouveau profil
        profiles_subframe_new = ctk.CTkFrame(profiles_frame)
        profiles_subframe_new.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(profiles_subframe_new, text="Nouveau:", width=120, anchor="w").pack(side="left")
        self.new_profile_entry = ctk.CTkEntry(profiles_subframe_new, placeholder_text="Entrez un nouveau nom de profil", width=200)
        self.new_profile_entry.pack(side="left", padx=10)
        self.new_profile_entry.bind("<KeyRelease>", lambda _e: self.update_profile_buttons())
        
        profiles_subframe2 = ctk.CTkFrame(profiles_frame)
        profiles_subframe2.pack(fill="x", padx=10, pady=5)
        self.save_profile_btn = ctk.CTkButton(profiles_subframe2, text="Sauvegarder Profil", command=self.save_profile, width=120)
        self.save_profile_btn.pack(side="left", padx=5)
        self.delete_profile_btn = ctk.CTkButton(profiles_subframe2, text="Supprimer Profil", command=self.delete_profile, width=120)
        self.delete_profile_btn.pack(side="left", padx=5)

        # Section 3.5: Mods / Resource Packs / Shader Packs (extensible)
        assets_section = ctk.CTkFrame(right_column)
        assets_section.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(assets_section, text="Contenu additionnel", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))

        # Bouton de bascule pour étendre/rabattre
        toggle_frame = ctk.CTkFrame(assets_section)
        toggle_frame.pack(fill="x", padx=10, pady=5)
        self.assets_toggle_btn = ctk.CTkButton(
            toggle_frame,
            text="Mods/Packs de ressources/Packs de shaders ▼",
            width=250,
            command=self._toggle_assets_section,
        )
        self.assets_toggle_btn.pack(side="left")

        # Conteneur extensible (non packé par défaut)
        self.assets_frame = ctk.CTkFrame(assets_section)
        # self.assets_frame.pack(fill="x", padx=10, pady=5)  # packé via toggle

        # Texte d'explication
        help_label = ctk.CTkLabel(
            self.assets_frame,
            text="💡 Séparez les add-ons par des virgules",
            font=("Arial", 11),
            text_color="gray"
        )
        help_label.pack(anchor="w", padx=10, pady=(5, 10))

        # Champ Resource Packs (toujours affiché quand section étendue)
        self.resource_packs_frame = ctk.CTkFrame(self.assets_frame)
        ctk.CTkLabel(self.resource_packs_frame, text="Packs de ressources:", width=150, anchor="w").pack(anchor="w")
        self.resource_packs_text = ctk.CTkTextbox(
            self.resource_packs_frame,
            width=350,
            height=80,
        )
        self.resource_packs_text.pack(fill="x", expand=True, padx=10)
        self.resource_packs_text.bind("<KeyRelease>", self._on_assets_text_change)

        # Champ Mods (affiché uniquement pour loader moddé)
        self.mods_frame = ctk.CTkFrame(self.assets_frame)
        ctk.CTkLabel(self.mods_frame, text="Mods:", width=150, anchor="w").pack(anchor="w")
        self.mods_text = ctk.CTkTextbox(
            self.mods_frame,
            width=350,
            height=80,
        )
        self.mods_text.pack(fill="x", expand=True, padx=10)
        self.mods_text.bind("<KeyRelease>", self._on_assets_text_change)

        # Champ Shader Packs (affiché uniquement pour loader moddé)
        self.shader_frame = ctk.CTkFrame(self.assets_frame)
        ctk.CTkLabel(self.shader_frame, text="Packs de shaders:", width=150, anchor="w").pack(anchor="w")
        self.shader_text = ctk.CTkTextbox(
            self.shader_frame,
            width=350,
            height=80,
        )
        self.shader_text.pack(fill="x", expand=True, padx=10)
        self.shader_text.bind("<KeyRelease>", self._on_assets_text_change)
        
        # Section 4: Statut et Progression
        status_section = ctk.CTkFrame(left_column)
        status_section.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(status_section, text="Statut", font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 10))
        
        status_frame = ctk.CTkFrame(status_section)
        status_frame.pack(fill="x", padx=10, pady=5)
        
        # Label de statut
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Prêt à lancer le jeu",
            font=("Arial", 12),
            text_color="gray",
            anchor="w"
        )
        self.status_label.pack(fill="x", padx=10, pady=5)
        
        # Barre de progression (masquée par défaut)
        self.progress_bar = ctk.CTkProgressBar(status_frame, height=20)
        self.progress_bar.set(0)  # Initialiser à 0%
        # Ne pas pack() la barre - elle sera affichée uniquement lors des téléchargements
        
        # Section 5: Bouton Jouer
        button_frame = ctk.CTkFrame(left_column)
        button_frame.pack(fill="x", padx=10, pady=20)
        
        self.play_btn = ctk.CTkButton(button_frame, text="🎮 JOUER", 
                                command=self.play_game, 
                                font=("Arial", 16, "bold"),
                                height=50, fg_color="#4CAF50", hover_color="#45a049")
        self.play_btn.pack(fill="x")

        
        # Initialiser l'état des boutons
        self.update_ui()
        self.update_profile_buttons()
        self.update_version_options()
        # Initialiser la visibilité des champs extensibles
        self._update_assets_fields_visibility()

    def on_profile_select(self, value):
        """Callback lors de la sélection d'un profil dans la liste"""
        self.profile_name.set(value)
        # Charger immédiatement le profil sélectionné
        self.load_profile()

    def _fit_main_to_content(self):
        """Adapter la fenêtre principale au contenu"""
        self.update_idletasks()
        padding_w = 40
        padding_h = 40
        w = self.winfo_reqwidth() + padding_w
        h = self.winfo_reqheight() + padding_h
        self.minsize(w, h)
        self.geometry(f"{w}x{h}")
    
    def update_ui(self):
        """Mettre à jour l'UI en fonction du mode"""
        if self.online_mode.get():
            self.connect_btn.configure(state="normal")
            self.offline_frame.pack_forget()
        else:
            self.connect_btn.configure(state="disabled")
            self.offline_frame.pack(fill="x", padx=30, pady=10)
    
    def open_advanced_settings(self):
        """Ouvrir la fenêtre des paramètres avancés"""
        AdvancedSettingsWindow(self)
    
    def connect_account(self):
        """Se connecter à un compte Microsoft (ouvre le navigateur)"""
        # Si déjà connecté, proposer de se déconnecter
        if self.auth_session:
            # Déconnexion
            self.auth_session = None
            self.logged_email.set("")
            self.connect_btn.configure(text="Se Connecter")
            logger.info("Déconnexion")
            return
        
        # Charger le dernier email utilisé pour pré-remplir le dialogue
        last_email = self._load_last_account() or ""
        
        # Demander l'email dans une boîte de dialogue simple
        dialog = ctk.CTkInputDialog(
            text="Entrez votre adresse email Microsoft:",
            title="Connexion Microsoft"
        )
        
        email = dialog.get_input() or last_email
        
        if not email:
            return
        
        # Vérifier si une session existe déjà
        existing_session = self.auth_db.get(email, MicrosoftAuthSession)
        if existing_session:
            try:
                # Valider la session existante
                if existing_session.validate():
                    self.auth_session = existing_session
                    self.logged_email.set(f"✓ Connecté: {email}")
                    self.connect_btn.configure(text="Déconnexion")
                    logger.info(f"Session validée pour {email}")
                    self._save_last_account(email)  # Sauvegarder l'email
                    return
                else:
                    # Tenter de rafraîchir la session
                    existing_session.refresh()
                    self.auth_db.save()
                    self.auth_session = existing_session
                    self.logged_email.set(f"✓ Connecté: {email}")
                    self.connect_btn.configure(text="Déconnexion")
                    logger.info(f"Session rafraîchie pour {email}")
                    self._save_last_account(email)  # Sauvegarder l'email
                    return
            except AuthError as e:
                logger.warning(f"Erreur lors de la validation: {e}")
                # Continuer vers nouvelle authentification
        
        # Nouvelle authentification
        self._authenticate_microsoft(email)
    
    def _authenticate_microsoft(self, email):
        """Authentification Microsoft via navigateur web"""
        nonce = uuid4().hex
        app_id = MICROSOFT_AZURE_APP_ID
        # URL de redirection enregistrée dans l'App Azure du CLI portablemc
        redirect_uri = "https://www.theorozier.fr/portablemc/auth"
        
        # Générer l'URL d'authentification
        auth_url = "https://login.live.com/oauth20_authorize.srf?{}".format(
            urllib.parse.urlencode({
                "client_id": app_id,
                "redirect_uri": redirect_uri,
                "response_type": "code id_token",
                "scope": "xboxlive.signin offline_access openid email",
                "login_hint": email,
                "nonce": nonce,
                "prompt": "select_account",
                "response_mode": "fragment"
            })
        )
        
        # Ouvrir le navigateur
        logger.info(f"Ouverture de la page d'authentification pour {email}")
        webbrowser.open(auth_url)
        
        # Afficher un dialogue pour coller le code
        dialog = ctk.CTkInputDialog(
            text=(
                "Après la connexion, copiez l'URL complète de redirection\n"
                "(https://www.theorozier.fr/portablemc/auth#...) ou\n"
                "collez uniquement le fragment commençant par 'id_token=...'\n"
                "puis collez-le ici :"
            ),
            title="Code d'authentification"
        )
        redirect_url = dialog.get_input()
        
        if not redirect_url:
            logger.info("Authentification annulée")
            return
        
        # Extraire code et id_token depuis URL complète ou fragment seul
        try:
            raw = (redirect_url or "").strip()
            if raw.startswith("#"):
                raw = raw[1:]
            code = None
            id_token = None
            
            if raw.startswith("http://") or raw.startswith("https://"):
                parsed = urllib.parse.urlparse(raw)
                # Essayer d'abord le fragment (response_mode=fragment)
                params = urllib.parse.parse_qs(parsed.fragment)
                # Si vide, tenter la query au cas où
                if not params:
                    params = urllib.parse.parse_qs(parsed.query)
                code = (params.get("code") or [None])[0]
                id_token = (params.get("id_token") or [None])[0]
            else:
                # Traiter comme un fragment ou une query brute 'id_token=...&code=...'
                if raw.startswith("?"):
                    raw = raw[1:]
                params = urllib.parse.parse_qs(raw)
                code = (params.get("code") or [None])[0]
                id_token = (params.get("id_token") or [None])[0]
            
            if not code:
                raise ValueError("Code d'authentification non trouvé")
            if not id_token:
                raise ValueError("Token ID non trouvé")
            
            # Vérifier la cohérence des données
            if not MicrosoftAuthSession.check_token_id(id_token, email, nonce):
                raise ValueError("Données d'authentification incohérentes")
            
            # Authentifier avec le code
            logger.info("Authentification en cours...")
            self.status_label.configure(text="Authentification en cours...", text_color="orange")
            self.update_idletasks()
            
            # Exécuter l'authentification dans un thread pour ne pas bloquer l'UI
            def auth_thread():
                try:
                    session = MicrosoftAuthSession.authenticate(
                        self.auth_db.get_client_id(),
                        app_id,
                        code,
                        redirect_uri
                    )
                    
                    # Sauvegarder la session
                    self.auth_db.put(email, session)
                    self.auth_db.save()
                    
                    # Mettre à jour l'UI dans le thread principal
                    self.after(0, lambda: self._on_auth_success(email, session))
                    
                except AuthError as e:
                    logger.error(f"Erreur d'authentification: {e}")
                    self.after(0, lambda: self._on_auth_error(str(e)))
            
            threading.Thread(target=auth_thread, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing de l'URL: {e}")
            self.status_label.configure(
                text=f"Erreur: {str(e)}",
                text_color="red"
            )
    
    def _on_auth_success(self, email, session):
        """Callback après authentification réussie"""
        self.auth_session = session
        self.logged_email.set(f"✓ Connecté: {email}")
        self.connect_btn.configure(text="Déconnexion")
        self.status_label.configure(
            text=f"Connecté en tant que {session.username}",
            text_color="#4CAF50"
        )
        logger.info(f"Authentification réussie: {session.username} ({email})")
        # Sauvegarder le dernier compte utilisé
        self._save_last_account(email)
    
    def _on_auth_error(self, error_msg):
        """Callback après erreur d'authentification"""
        self.status_label.configure(
            text=f"Erreur d'authentification: {error_msg}",
            text_color="red"
        )
        logger.error(f"Erreur d'authentification: {error_msg}")
    
    def _save_last_account(self, email):
        """Sauvegarder le dernier compte utilisé"""
        try:
            with open(LAST_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
                f.write(email)
            logger.info(f"Dernier compte sauvegardé: {email}")
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder le dernier compte: {e}")
    
    def _load_last_account(self):
        """Charger le dernier compte utilisé"""
        try:
            if os.path.exists(LAST_ACCOUNT_FILE):
                with open(LAST_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except Exception as e:
            logger.warning(f"Impossible de charger le dernier compte: {e}")
        return None
    
    def _auto_connect_last_account(self):
        """Connexion automatique au dernier compte utilisé"""
        email = self._load_last_account()
        if not email:
            return
        
        # Vérifier si une session existe pour ce compte
        existing_session = self.auth_db.get(email, MicrosoftAuthSession)
        if not existing_session:
            logger.info(f"Aucune session trouvée pour {email}")
            return
        
        try:
            # Valider la session
            if existing_session.validate():
                self.auth_session = existing_session
                self.logged_email.set(f"✓ Connecté: {email}")
                self.connect_btn.configure(text="Déconnexion")
                logger.info(f"Connexion automatique réussie pour {email}")
            else:
                # Tenter de rafraîchir la session
                logger.info(f"Rafraîchissement de la session pour {email}")
                existing_session.refresh()
                self.auth_db.save()
                self.auth_session = existing_session
                self.logged_email.set(f"✓ Connecté: {email}")
                self.connect_btn.configure(text="Déconnexion")
                logger.info(f"Session rafraîchie automatiquement pour {email}")
        except AuthError as e:
            logger.warning(f"Échec de la connexion automatique pour {email}: {e}")
            # Ne pas afficher d'erreur à l'utilisateur, juste ne pas se connecter

    def _show_progress_bar(self):
        """Affiche la barre de progression."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.pack(fill="x", padx=10, pady=5)
            self.update_idletasks()
    
    def _hide_progress_bar(self):
        """Masque la barre de progression."""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.pack_forget()
            self.update_idletasks()
    
    def _add_palgania_server(self, game_dir):
        """Ajoute Palgania à la liste des serveurs si absent"""
        try:
            servers_dat = os.path.join(game_dir, "servers.dat")
            
            # Structures NBT simplifiées
            def read_nbt_string(f):
                length = struct.unpack('>H', f.read(2))[0]
                return f.read(length).decode('utf-8')
            
            def write_nbt_string(f, s):
                encoded = s.encode('utf-8')
                f.write(struct.pack('>H', len(encoded)))
                f.write(encoded)
            
            servers = []
            has_palgania = False
            
            # Lire servers.dat existant
            if os.path.exists(servers_dat):
                try:
                    with open(servers_dat, 'rb') as f:
                        # TAG_Compound (type 10)
                        tag_type = f.read(1)[0]
                        if tag_type != 10:
                            raise ValueError("Format NBT invalide")
                        
                        root_name = read_nbt_string(f)
                        
                        # Chercher TAG_List "servers" (type 9)
                        while True:
                            tag_type = f.read(1)
                            if not tag_type or tag_type[0] == 0:  # TAG_End
                                break
                            
                            tag_name = read_nbt_string(f)
                            
                            if tag_name == "servers" and tag_type[0] == 9:  # TAG_List
                                list_type = f.read(1)[0]  # Type des éléments (10 = Compound)
                                list_length = struct.unpack('>i', f.read(4))[0]
                                
                                for _ in range(list_length):
                                    server = {}
                                    # Lire chaque serveur (TAG_Compound)
                                    while True:
                                        inner_type = f.read(1)
                                        if not inner_type or inner_type[0] == 0:  # TAG_End
                                            break
                                        
                                        inner_name = read_nbt_string(f)
                                        
                                        if inner_type[0] == 8:  # TAG_String
                                            value = read_nbt_string(f)
                                            server[inner_name] = value
                                            if inner_name == "ip" and value == "palgania.ovh":
                                                has_palgania = True
                                        elif inner_type[0] == 1:  # TAG_Byte
                                            server[inner_name] = f.read(1)[0]
                                        else:
                                            # Ignorer les autres types
                                            break
                                    
                                    servers.append(server)
                                break
                            else:
                                # Ignorer ce tag
                                break
                except Exception as e:
                    logger.warning(f"Impossible de lire servers.dat: {e}")
                    servers = []
            
            # Ajouter Palgania si absent
            if not has_palgania:
                servers.append({
                    "name": "Palgania",
                    "ip": "palgania.ovh",
                    "acceptTextures": 1
                })
                logger.info("Ajout de Palgania à la liste des serveurs")
                
                # Écrire le nouveau servers.dat
                with open(servers_dat, 'wb') as f:
                    # TAG_Compound root
                    f.write(b'\x0a')  # Type 10
                    write_nbt_string(f, "")  # Nom vide
                    
                    # TAG_List "servers"
                    f.write(b'\x09')  # Type 9
                    write_nbt_string(f, "servers")
                    f.write(b'\x0a')  # Type liste = Compound
                    f.write(struct.pack('>i', len(servers)))  # Nombre d'éléments
                    
                    # Écrire chaque serveur
                    for server in servers:
                        # TAG_String "name"
                        f.write(b'\x08')
                        write_nbt_string(f, "name")
                        write_nbt_string(f, server.get("name", "Serveur"))
                        
                        # TAG_String "ip"
                        f.write(b'\x08')
                        write_nbt_string(f, "ip")
                        write_nbt_string(f, server.get("ip", ""))
                        
                        # TAG_Byte "acceptTextures" (optionnel)
                        if "acceptTextures" in server:
                            f.write(b'\x01')
                            write_nbt_string(f, "acceptTextures")
                            f.write(bytes([server["acceptTextures"]]))
                        
                        # TAG_End du serveur
                        f.write(b'\x00')
                    
                    # TAG_End du root
                    f.write(b'\x00')
            else:
                logger.info("Palgania déjà présent dans la liste des serveurs")
                
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de Palgania: {e}")

    def _find_installed_fabric_version_id(self, game_dir: str, mc_version: str) -> Optional[str]:
        """Recherche une version Fabric déjà installée correspondant à la version Minecraft.

        Parcourt `.minecraft/versions/*/*.json` et détecte une version contenant
        le loader Fabric et héritant (inheritsFrom) de la version cible, ou dont l'id
        contient la version cible. Retourne l'identifiant de version (nom du dossier)
        si trouvée, sinon None.
        """
        try:
            versions_dir = os.path.join(game_dir, "versions")
            if not os.path.isdir(versions_dir):
                return None
            for name in os.listdir(versions_dir):
                vdir = os.path.join(versions_dir, name)
                json_path = os.path.join(vdir, f"{name}.json")
                if not os.path.isfile(json_path):
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                libs = data.get("libraries", [])
                is_fabric = any("net.fabricmc:fabric-loader" in (lib.get("name") or "") for lib in libs)
                if not is_fabric:
                    continue
                inherits = data.get("inheritsFrom") or data.get("inherits_from")
                version_id = str(data.get("id") or name)
                # Correspondance par héritage exact ou présence de la version MC dans l'id
                if (inherits and str(inherits) == str(mc_version)) or (str(mc_version) in version_id):
                    return name
        except Exception as e:
            logger.warning(f"Recherche Fabric locale échouée: {e}")
        return None

    def play_game(self):
        """Lancer le jeu avec les options choisies (démarre un thread pour ne pas bloquer l'UI)"""
        # Désactiver le bouton pour éviter les clics multiples
        self.play_btn.configure(state="disabled", fg_color="gray")
        
        # Démarrer le processus complet dans un thread séparé
        threading.Thread(target=self._launch_game_task, daemon=True).start()

    def _launch_game_task(self):
        """Tâche de fond: téléchargement, installation et lancement du jeu"""
        print(f"Lancement du jeu avec les options:")
        print(f"  Mode en ligne: {self.online_mode.get()}")
        if not self.online_mode.get():
            print(f"  Pseudo: {self.pseudo.get()}")
            print(f"  UUID: {self.uuid.get()}")
        print(f"  Loader: {self.loader.get()}")
        print(f"  Version: {self.version.get()} ({self.version_group.get()})")
        print(f"  Profil: {self.profile_name.get()}")

        try:
            # Préparer le contexte de lancement
            game_dir = self.advanced_settings.get("mc_data_dir", "")
            if game_dir == "":
                game_dir = os.path.join(os.path.expanduser("~"), ".minecraft")
            
            # Utiliser expanduser si nécessaire pour les chemins relatifs ~
            if game_dir.startswith("~"):
                game_dir = os.path.expanduser(game_dir)
                
            context = Context(main_dir=pathlib.Path(game_dir))

            # Préparer / télécharger / installer les addons déclarés
            # Note: _prepare_all_addons doit être sécurisé s'il modifie l'UI, ce qui semble être le cas via status_label
            # Mais ici c'est synchronisé dans ce thread. Il faudra vérifier que _prepare_all_addons utilise aussi self.after
            # pour toucher à l'UI.
            # Pour l'instant on suppose que _prepare_all_addons est modifié ou qu'on va le modifier ensuite.
            # (Dans l'état actuel il est probablement bloquant et unsafe si non modifié)
            if not self._prepare_all_addons_safe():
                 # Annulé par l'utilisateur après une erreur d'addon ou échec
                self.app_safe_ui_update(lambda: self.play_btn.configure(state="normal", fg_color="#4CAF50"))
                return

            # Préparer la version
            loader_val = self.loader.get()
            version_val = self.version.get()
            
            if loader_val == "Vanilla":
                version = Version(version_val, context=context)
            elif loader_val == "Fabric":
                # Priorité: utiliser une version Fabric locale si déjà installée
                local_id = self._find_installed_fabric_version_id(game_dir, version_val)
                if local_id:
                    version = Version(local_id, context=context)
                    self.app_safe_ui_update(lambda: self.status_label.configure(
                        text=f"Utilisation de Fabric local '{local_id}' (aucun appel réseau)",
                        text_color="#FF9800"
                    ))
                else:
                    # Sinon, tenter l'initialisation en ligne
                    try:
                        version = FabricVersion.with_fabric(version_val, context=context)
                    except Exception as e:
                        # Fallback hors ligne: erreurs réseau/HTTP typiques
                        if isinstance(e, (urllib.error.URLError, urllib.error.HTTPError, TimeoutError)):
                            msg = (
                                "Mode hors ligne: Fabric non installé localement et métadonnées inaccessibles.\n"
                                f"Version Minecraft: {version_val}\n\n"
                                "Astuce: lancez une fois en ligne pour installer Fabric pour cette version."
                            )
                            logger.error(f"Fabric init failed offline: {e}")
                            self.app_safe_ui_update(lambda: self.status_label.configure(text=msg, text_color="red"))
                            watcher = InstallWatcher(self) # Juste pour avoir accès aux méthodes hide thread-safe si besoin
                            watcher._hide_progress_bar()
                            self.app_safe_ui_update(lambda: self.play_btn.configure(state="normal", fg_color="#4CAF50"))
                            return
                        else:
                            raise
            elif loader_val == "Forge":
                version = ForgeVersion(version_val, context=context)
            elif loader_val == "Neoforge":
                version = _NeoForgeVersion(version_val, context=context)

            # Appliquer Java/JVM personnalisés avant l'installation
            custom_java_path = (self.advanced_settings.get("java_path", "") or "").strip()
            java_applied = False
            resolved_java = None
            if custom_java_path:
                resolved_java = os.path.expanduser(custom_java_path)
                if os.path.isfile(resolved_java):
                    version.jvm_path = pathlib.Path(resolved_java)
                    java_applied = True
                    logger.info(f"Java personnalisé défini: {resolved_java}")
                else:
                    warn = f"Chemin Java introuvable, Java par défaut utilisé: {resolved_java}"
                    logger.warning(warn)
                    self.app_safe_ui_update(lambda: self.status_label.configure(text=warn, text_color="#FF9800"))

            custom_jvm_args_raw = (self.advanced_settings.get("jvm_args", "") or "").strip()
            custom_jvm_args = []
            if custom_jvm_args_raw:
                try:
                    custom_jvm_args = shlex.split(custom_jvm_args_raw)
                except ValueError:
                    custom_jvm_args = custom_jvm_args_raw.split()
                logger.info(f"Arguments JVM personnalisés saisis: {custom_jvm_args}")
            
            # Configurer l'authentification
            if self.online_mode.get():
                # Mode en ligne: utiliser la session Microsoft si disponible
                if self.auth_session:
                    version.auth_session = self.auth_session
                    logger.info(f"Lancement avec authentification: {self.auth_session.username}")
                else:
                    logger.warning("Mode en ligne activé mais aucune session - lancement en mode hors ligne")
                    version.set_auth_offline(
                        self.pseudo.get() or None,
                        self.uuid.get() or None
                    )
            else:
                # Mode hors ligne: utiliser pseudo/UUID
                version.set_auth_offline(
                    self.pseudo.get() or None,
                    self.uuid.get() or None
                )
                logger.info(f"Lancement en mode hors ligne: {self.pseudo.get() or 'pseudo aléatoire'}")
            
            watcher = InstallWatcher(self)
            
            try:
                env = version.install(watcher=watcher)
            except KeyError as e:
                # Problème avec les variables de processus (souvent avec Neoforge)
                loader_name = loader_val
                version_name = version_val
                
                error_msg = f"⚠️ Erreur d'installation: variable manquante '{e}'\n\n"
                
                if loader_name == "Neoforge" and version_name.startswith("1.21"):
                    error_msg += "Neoforge 1.21+ a des problèmes de compatibilité.\n\n"
                    error_msg += "Solutions suggérées:\n"
                    error_msg += "1. Essayer avec Forge (même version)\n"
                    error_msg += "2. Utiliser Vanilla (pas de mod loader)\n"
                    error_msg += "3. Essayer une version antérieure\n"
                else:
                    error_msg += "Cela peut être dû à:\n"
                    error_msg += "• Une incompatibilité avec la version du loader\n"
                    error_msg += "• Un problème avec portablemc\n\n"
                    error_msg += f"Détails: {str(e)}"
                
                logger.error(f"Installation error for {loader_name} {version_name}: {e}")
                self.app_safe_ui_update(lambda: self.status_label.configure(text=error_msg, text_color="red"))
                watcher._hide_progress_bar()
                self.app_safe_ui_update(lambda: self.play_btn.configure(state="normal", fg_color="#4CAF50"))
                return
            except Exception as e:
                # Autres erreurs d'installation
                error_msg = f"❌ Erreur lors de l'installation:\n{type(e).__name__}: {str(e)[:100]}"
                logger.error(f"Installation error: {e}", exc_info=True)
                self.app_safe_ui_update(lambda: self.status_label.configure(text=error_msg, text_color="red"))
                watcher._hide_progress_bar()
                self.app_safe_ui_update(lambda: self.play_btn.configure(state="normal", fg_color="#4CAF50"))
                return
            
            # Injecter Java personnalisé et arguments JVM après installation
            if java_applied and resolved_java:
                env.jvm_args[0] = resolved_java
            if custom_jvm_args:
                env.jvm_args = env.jvm_args[:1] + custom_jvm_args + env.jvm_args[1:]
            logger.info(f"JVM utilisée: {env.jvm_args[0]}")
            if custom_jvm_args:
                logger.info(f"JVM args finaux: {env.jvm_args}")

            # Ajouter Palgania à la liste des serveurs si demandé
            if self.advanced_settings.get("auto_add_palgania", True):
                self._add_palgania_server(game_dir)

            # Appliquer les paramètres quickplay si configurés
            quickplay_server = self.advanced_settings.get("quickplay_server", "").strip()
            quickplay_port = self.advanced_settings.get("quickplay_port", "").strip()
            quickplay_world = self.advanced_settings.get("quickplay_world", "").strip()
            
            if quickplay_server:
                # Connexion à un serveur multijoueur
                host = quickplay_server
                port = quickplay_port or "25565"
                # Normaliser et extraire host/port si saisi au format host:port ou avec schéma
                try:
                    s = host
                    if "://" in s:
                        s = s.split("://", 1)[1]
                    if s.startswith("[") and "]:" in s:
                        h, p = s.split("]:", 1)
                        host = h.strip("[]")
                        port = p
                    elif ":" in s:
                        parts = s.rsplit(":", 1)
                        host = parts[0]
                        port = parts[1]
                    else:
                        host = s
                except Exception:
                    host = quickplay_server

                try:
                    port_int = int(str(port))
                    if not (1 <= port_int <= 65535):
                        port_int = 25565
                except Exception:
                    port_int = 25565
                port = str(port_int)

                addr = f"{host}:{port}" if port else host
                # PortableMC doc: versions modernes utilisent quick play args
                env.game_args.extend(["--quickPlayMultiplayer", addr])
                # Legacy fallback
                env.game_args.extend(["--server", host])
                if port != "25565":
                    env.game_args.extend(["--port", port])
                logger.info(f"Quickplay: connexion au serveur {addr}")
            elif quickplay_world:
                # Lancement d'un monde solo
                env.game_args.extend(["--quickPlaySingleplayer", quickplay_world])
                logger.info(f"Quickplay: lancement du monde solo '{quickplay_world}'")
            
            # Masquer le launcher avant de lancer le jeu
            self.app_safe_ui_update(self.withdraw)
            
            # Lancer le jeu (bloque le thread jusqu'à la fin du jeu)
            env.run()
            
            # Fin du processus, on ferme l'appli python
            # Note: sys.exit(0) ne tuerait que le thread, os._exit termine durement
            os._exit(0)
            
        except Exception as global_e:
             logger.error(f"Fatal launch error: {global_e}", exc_info=True)
             self.app_safe_ui_update(lambda: self.status_label.configure(text=f"Fatal Error: {global_e}", text_color="red"))
             self.app_safe_ui_update(lambda: self.play_btn.configure(state="normal", fg_color="#4CAF50"))

    def app_safe_ui_update(self, func):
        """Helper pour exécuter des mises à jour UI depuis un thread"""
        self.after(0, func)
    
    def _prepare_all_addons_safe(self) -> bool:
        """Wrapper thread-safe pour _prepare_all_addons"""
        # Comme _prepare_all_addons contient beaucoup de logique qui pourrait interagir avec l'UI (print, updates)
        # Il faut que _prepare_all_addons soit soit rewritten, soit on redirige les appels UI.
        # Dans ce code, _prepare_all_addons n'est pas montré mais supposé exister.
        # Je vais ajouter une implémentation locale inline si elle n'existe pas ou assumer qu'il faut la créer.
        # L'ancienne play_game l'appelait : if not self._prepare_all_addons():
        
        # Vu que je n'ai pas vu la définition de _prepare_all_addons dans les vues précédentes,
        # je dois la recréer ou la trouver.
        # En fait, elle n'était PAS dans le fichier précédemment lu intégralement (mais il y avait des troncatures).
        # Je vais supposer qu'elle utilise self.status_label pour le feedback.
        # Pour le moment, je vais l'implémenter ici ou appeler l'existante en espérant qu'elle ne touche pas l'UI directement.
        # MAIS ATTENTION: Si elle appelle self.status_label.configure direct, ça crash.
        # Je vais devoir la wrapper ou la réécrire.
        
        # Pour être sûr, je la réimplémente complètement ici en version Thread-Safe
        return self._prepare_all_addons_impl()

    def _prepare_all_addons_impl(self) -> bool:
         # Logique d'installation des addons
         # Récupérer les mots clés (thread safe car lecture de variables)
         loader = self.loader.get().lower()
         version = self.version.get()
         
         # Pas d'addons en Vanilla pur (sauf resource packs)
         # On va simplifier : on installe si des keywords sont présents
         
         rp_keys = [k.strip() for k in self.resource_packs_keywords.get().split(',') if k.strip()]
         mod_keys = [k.strip() for k in self.mods_keywords.get().split(',') if k.strip()]
         sh_keys = [k.strip() for k in self.shader_packs_keywords.get().split(',') if k.strip()]
         
         total = len(rp_keys) + len(mod_keys) + len(sh_keys)
         if total == 0:
             return True

         self.app_safe_ui_update(lambda: self.status_label.configure(text=f"Vérification des {total} addons...", text_color="orange"))
         
         # Managers
         try:
             # Attention: AddonsManager utilise requests/urllib qui est bloquant (c'est ce qu'on veut ici)
             # Il faut juste ne pas toucher à l'UI
             from addons_manager import AddonsManager, AddonNotFoundError
             
             game_dir = self.advanced_settings.get("mc_data_dir", "") or None
             
             # Resource Packs
             if rp_keys:
                 mgr = AddonsManager("resourcepacks", game_dir=game_dir, loader=loader, version=version)
                 try:
                     self.app_safe_ui_update(lambda: self.status_label.configure(text="Installation des Resource Packs...", text_color="orange"))
                     mgr.install_addons(rp_keys)
                 except Exception as e:
                     logger.error(f"Erreur RP: {e}")
                     formatted = f"Erreur Resource Packs: {e}"
                     self.app_safe_ui_update(lambda: messagebox.showerror("Erreur Addons", formatted))
                     return False

             # Mods (seulement si non vanilla)
             if mod_keys and loader != "vanilla":
                 mgr = AddonsManager("mods", game_dir=game_dir, loader=loader, version=version)
                 try:
                     self.app_safe_ui_update(lambda: self.status_label.configure(text="Installation des Mods...", text_color="orange"))
                     mgr.install_addons(mod_keys)
                 except Exception as e:
                     logger.error(f"Erreur Mods: {e}")
                     self.app_safe_ui_update(lambda: messagebox.showerror("Erreur Addons", f"Erreur Mods: {e}"))
                     return False
             
             # Shaders (seulement si Iris/Optifine présent, on suppose Iris sur Fabric/Neo)
             if sh_keys:
                 # Force Iris loader handling in manager
                 mgr = AddonsManager("shaderpacks", game_dir=game_dir, loader=loader, version=version)
                 try:
                     self.app_safe_ui_update(lambda: self.status_label.configure(text="Installation des Shaders...", text_color="orange"))
                     mgr.install_addons(sh_keys)
                 except Exception as e:
                     logger.error(f"Erreur Shaders: {e}")
                     self.app_safe_ui_update(lambda: messagebox.showerror("Erreur Addons", f"Erreur Shaders: {e}"))
                     return False
                     
             return True
             
         except Exception as e:
             logger.error(f"Erreur globale addons: {e}")
             self.app_safe_ui_update(lambda: messagebox.showerror("Erreur critique", f"Impossible de gérer les addons: {e}"))
             return False

    def load_profiles(self):
        """Charger les profils depuis le fichier JSON"""
        if os.path.exists(PROFILES_FILE):
            try:
                with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Peut être un dict simple {profil_name: profil_data, ...}
                    # ou un dict avec metadata: {"_metadata": {...}, profil_name: profil_data, ...}
                    if isinstance(data, dict) and "_metadata" not in data:
                        # Format ancien, juste les profils
                        return data
                    elif isinstance(data, dict):
                        return data
                    return {"Défaut": {}}
            except:
                return {"Défaut": {}}
        return {"Défaut": {}}
    
    def save_profiles(self):
        """Sauvegarder les profils dans le fichier JSON"""
        with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.profiles, f, indent=2, ensure_ascii=False)
    
    def load_profile(self):
        """Charger un profil existant"""
        profile_name = self.profile_name.get()
        if profile_name in self.profiles:
            profile_data = self.profiles[profile_name]
            self.online_mode.set(profile_data.get("online_mode", True))
            self.pseudo.set(profile_data.get("pseudo", ""))
            self.uuid.set(profile_data.get("uuid", ""))
            loaded_loader = profile_data.get("loader", "Vanilla")
            self.loader.set(loaded_loader)
            # Rafraîchir immédiatement les familles/versions selon le loader du profil
            self.on_loader_change(loaded_loader)
            # Charger les champs de mots-clés (peuvent être absents sur anciens profils)
            r = profile_data.get("resource_packs_keywords", "")
            m = profile_data.get("mods_keywords", "")
            s = profile_data.get("shader_packs_keywords", "")
            self._set_assets_keywords_to_ui(r, m, s)

            # Vérifier si le profil utilise "latest"
            saved_version = profile_data.get("version", "")
            if saved_version == "latest" or profile_name == "Défaut":
                # Charger la toute dernière version disponible (famille + version)
                families = list(self.version_groups.keys())
                if families:
                    latest_family = families[0]
                    self.version_group.set(latest_family)
                    versions = self.version_groups.get(latest_family, [])
                    self.update_version_options(latest_family)
                    if versions:
                        self.version.set(versions[0])
                else:
                    self.update_version_options()
            else:
                # Charger la famille et la version stockées
                self.version_group.set(profile_data.get("version_group", self.version_group.get()))
                self.update_version_options()
                self.version.set(saved_version)
            
            # Charger les paramètres avancés
            if "advanced_settings" in profile_data:
                self.advanced_settings = profile_data["advanced_settings"]
            else:
                # Réinitialiser aux valeurs par défaut
                self.advanced_settings = {
                    "java_path": "",
                    "mc_data_dir": "",
                    "jvm_args": "",
                    "quickplay_server": "",
                    "quickplay_port": "25565",
                    "quickplay_world": ""
                }
            
            print(f"Profil '{profile_name}' chargé")
            self.update_ui()
            self.update_profile_buttons()
            # Mettre à jour la visibilité de la section assets selon le loader
            self._update_assets_fields_visibility()
            # Enregistrer comme dernier profil utilisé (y compris Défaut)
            self._save_last_profile(profile_name)
    
    def save_profile(self):
        """Sauvegarder le profil actuel"""
        profile_name = self.new_profile_entry.get().strip()
        if not profile_name:
            profile_name = self.profile_name.get()
        
        if profile_name:
            # Déterminer si on doit sauvegarder "latest" ou la version actuelle
            # Le profil Défaut ne sauvegarde jamais rien (profil spécial)
            if profile_name == "Défaut":
                # Ne rien sauvegarder pour le profil Défaut (profil spécial en lecture seule)
                return
            
            # Pour les autres profils, vérifier s'ils ont "latest" déjà
            current_profile_data = self.profiles.get(profile_name, {})
            saved_version = current_profile_data.get("version", "")
            
            # Si le profil avait "latest", le conserver (sauf si une version spécifique est maintenant sélectionnée manuellement)
            # On considère que si saved_version == "latest", on le garde "latest"
            version_to_save = saved_version if saved_version == "latest" else self.version.get()
            
            # Récupérer contenus UI des zones de texte
            r_kw, m_kw, s_kw = self._get_assets_keywords_from_ui()

            self.profiles[profile_name] = {
                "online_mode": self.online_mode.get(),
                "pseudo": self.pseudo.get(),
                "uuid": self.uuid.get(),
                "loader": self.loader.get(),
                "version_group": self.version_group.get(),
                "version": version_to_save,
                "advanced_settings": self.advanced_settings,
                # Champs de mots-clés pour contenu additionnel
                "resource_packs_keywords": r_kw,
                "mods_keywords": m_kw,
                "shader_packs_keywords": s_kw,
            }
            self.save_profiles()
            # Enregistrer comme dernier profil utilisé (y compris "Défaut")
            self._save_last_profile(profile_name)
            self.profile_name.set(profile_name)
            self.new_profile_entry.delete(0, "end")
            
            # Mettre à jour le menu déroulant
            self.profile_combo.configure(values=list(self.profiles.keys()))
            self.update_profile_buttons()
            
            print(f"Profil '{profile_name}' sauvegardé")
    
    def delete_profile(self):
        """Supprimer un profil"""
        profile_name = self.profile_name.get()
        if profile_name != "Défaut" and profile_name in self.profiles:
            del self.profiles[profile_name]
            self.save_profiles()
            self.profile_name.set("Défaut")
            
            # Mettre à jour le menu déroulant
            self.profile_combo.configure(values=list(self.profiles.keys()))
            
            self.update_profile_buttons()
            
            print(f"Profil '{profile_name}' supprimé")
    
    def select_latest_version(self):
        """Sélectionner la dernière version disponible et marquer le profil comme 'latest'"""
        # Charger la dernière version
        families = list(self.version_groups.keys())
        if families:
            latest_family = families[0]
            self.version_group.set(latest_family)
            versions = self.version_groups.get(latest_family, [])
            self.update_version_options(latest_family)
            if versions:
                self.version.set(versions[0])
        
        # Marquer le profil actuel avec version="latest" (sauf pour Défaut)
        profile_name = self.profile_name.get()
        if profile_name != "Défaut" and profile_name in self.profiles:
            self.profiles[profile_name]["version"] = "latest"
            self.profiles[profile_name]["version_group"] = self.version_group.get()
            self.save_profiles()
            print(f"Profil '{profile_name}' configuré pour utiliser toujours la dernière version")
            logger.info(f"Profil '{profile_name}' marqué avec version='latest'")

    def update_profile_buttons(self):
        """Activer/désactiver le bouton de sauvegarde selon le profil"""
        current_profile = self.profile_name.get()
        new_name = self.new_profile_entry.get().strip()
        disable_save = (current_profile == "Défaut" and not new_name)
        disable_delete = (current_profile == "Défaut")
        save_state = "disabled" if disable_save else "normal"
        delete_state = "disabled" if disable_delete else "normal"
        if hasattr(self, "save_profile_btn"):
            self.save_profile_btn.configure(state=save_state)
        if hasattr(self, "delete_profile_btn"):
            self.delete_profile_btn.configure(state=delete_state)

    def update_version_options(self, group=None):
        """Mettre à jour la liste des versions selon la famille"""
        if group:
            self.version_group.set(group)
        group_key = self.version_group.get()
        versions = self.version_groups.get(group_key, [])
        self.version_combo.configure(values=versions if versions else [""])
        # Assurer que la version sélectionnée est valide pour ce groupe
        if versions:
            if self.version.get() not in versions:
                self.version.set(versions[0])
        else:
            self.version.set("")
        # Basculer vers un sélecteur scrollable pour Snapshots (meilleure ergonomie)
        if group_key == "Snapshots":
            # Afficher le bouton et masquer la combo pour éviter une liste trop grande
            self.version_select_btn.pack(side="left", padx=10)
            self.version_select_label.pack(side="left", padx=(5, 0))
            if self.version_combo.winfo_ismapped():
                self.version_combo.pack_forget()
            # Mettre à jour le label avec la version actuelle (après avoir assuré sa validité)
            self._update_version_select_label()
        else:
            # Afficher la combo normale
            if not self.version_combo.winfo_ismapped():
                self.version_combo.pack(side="left", padx=10)
            # Masquer le bouton et label si visibles
            if self.version_select_btn.winfo_ismapped():
                self.version_select_btn.pack_forget()
            if self.version_select_label.winfo_ismapped():
                self.version_select_label.pack_forget()

    def _open_version_dialog(self):
        """Ouvrir le sélecteur scrollable pour choisir une version (utilisé pour Snapshots)."""
        group_key = self.version_group.get()
        versions = self.version_groups.get(group_key, [])
        dlg = VersionSelectDialog(self, f"Sélectionner une version ({group_key})", versions, self.version.get(), self._update_version_select_label)
        # Elever la fenêtre
        dlg.lift()
        dlg.attributes('-topmost', True)
        self.after(200, lambda: dlg.attributes('-topmost', False))

    def _update_version_select_label(self):
        """Mettre à jour le label affichant la version snapshot sélectionnée"""
        version = self.version.get()
        if version:
            self.version_select_label.configure(text=version)
        else:
            self.version_select_label.configure(text="")

    def on_version_group_change(self, value):
        """Callback quand on change de famille de version"""
        self.update_version_options(value)

    def on_loader_change(self, value):
        """Callback quand on change de loader"""
        # Map UI label to internal loader name
        internal_loader = LOADER_MAP.get(value, "vanilla")
        
        # Load versions for the selected loader
        new_groups = get_version_groups(internal_loader)
        if not new_groups:
            new_groups = get_version_groups(internal_loader)  # Retry with fallback
        
        self.version_groups = new_groups
        
        # Update version group combo with new families
        families = list(self.version_groups.keys())
        self.version_group_combo.configure(values=families)
        
        # Select first family
        if families:
            first_family = families[0]
            self.version_group.set(first_family)
            # Update version options for first family
            self.update_version_options(first_family)
        
        # Async refresh in background
        refresh_version_groups_async(internal_loader, self._on_loader_refresh_complete)
        # Mettre à jour la visibilité des champs mods/shaders
        self._update_assets_fields_visibility()
    
    def _on_loader_refresh_complete(self, groups):
        """Called when async loader version refresh completes"""
        if not groups:
            return
        # Update cache and UI if groups changed
        self.version_groups = groups
        families = list(self.version_groups.keys())
        self.version_group_combo.configure(values=families)
        # Refresh current selection
        cur_family = self.version_group.get()
        if cur_family in self.version_groups:
            self.update_version_options(cur_family)

    def _refresh_versions_async(self):
        """Rafraîchir les versions en arrière-plan sans bloquer l'UI."""
        import threading

        def worker():
            new_groups = refresh_version_groups_async()
            # Appliquer sur le thread UI
            self.after(0, lambda: self._apply_new_version_groups(new_groups))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_new_version_groups(self, new_groups):
        """Mettre à jour les combobox si des nouvelles versions sont disponibles."""
        if not isinstance(new_groups, dict) or not new_groups:
            return
        old_groups = self.version_groups
        # Si identiques, ne rien faire
        if old_groups == new_groups:
            return
        self.version_groups = new_groups
        # Mettre à jour la combo des familles
        families = list(self.version_groups.keys())
        self.version_group_combo.configure(values=families)
        # Préserver sélection si possible
        cur_family = self.version_group.get()
        if cur_family not in self.version_groups:
            cur_family = families[0]
            self.version_group.set(cur_family)
        # Mettre à jour versions détaillées et préserver la sélection
        cur_version = self.version.get()
        self.update_version_options(cur_family)
        if cur_version in self.version_groups.get(cur_family, []):
            self.version.set(cur_version)

    def _set_assets_keywords_to_ui(self, resource_packs: str, mods: str, shaders: str):
        """Définir le contenu des zones de texte des mots-clés et synchroniser les StringVars."""
        prev = self._suspend_assets_autosave
        self._suspend_assets_autosave = True
        # Mettre à jour les StringVars
        self.resource_packs_keywords.set(resource_packs or "")
        self.mods_keywords.set(mods or "")
        self.shader_packs_keywords.set(shaders or "")
        # Remplir les zones de texte si disponibles
        if self.resource_packs_text:
            self.resource_packs_text.delete("1.0", "end")
            self.resource_packs_text.insert("1.0", self.resource_packs_keywords.get())
        if self.mods_text:
            self.mods_text.delete("1.0", "end")
            self.mods_text.insert("1.0", self.mods_keywords.get())
        if self.shader_text:
            self.shader_text.delete("1.0", "end")
            self.shader_text.insert("1.0", self.shader_packs_keywords.get())
        self._suspend_assets_autosave = prev

    def _get_assets_keywords_from_ui(self):
        """Récupérer le contenu des zones de texte des mots-clés et synchroniser les StringVars."""
        resource = self.resource_packs_text.get("1.0", "end").strip() if self.resource_packs_text else self.resource_packs_keywords.get()
        mods = self.mods_text.get("1.0", "end").strip() if self.mods_text else self.mods_keywords.get()
        shaders = self.shader_text.get("1.0", "end").strip() if self.shader_text else self.shader_packs_keywords.get()
        # Synchroniser les StringVars
        self.resource_packs_keywords.set(resource)
        self.mods_keywords.set(mods)
        self.shader_packs_keywords.set(shaders)
        return resource, mods, shaders

    def _split_keywords(self, text: str):
        """Découpe une chaîne en mots-clés par virgule ou retour ligne, en filtrant les vides."""
        if not text:
            return []
        raw = text.replace("\n", ",").split(",")
        return [w.strip() for w in raw if w.strip()]

    def _prepare_addons_for_type(self, addon_type: str, keywords):
        """Préparer/fetch/installer les addons pour un type donné.

        Retourne True si OK ou ignoré, False si l'utilisateur annule.
        """
        if not keywords:
            return True
        loader_internal = LOADER_MAP.get(self.loader.get(), self.loader.get().lower())
        version_name = self.version.get()
        game_dir = self.advanced_settings.get("mc_data_dir", "")
        if game_dir == "":
            game_dir = os.path.join(os.path.expanduser("~"), ".minecraft")

        mgr = AddonsManager(
            addon_type=addon_type,
            game_dir=game_dir,
            loader=loader_internal,
            version=version_name,
            config_dir=str(CONFIG_DIR),
        )

        total = len(keywords)
        # Afficher progression dans la zone de statut principale
        self._show_progress_bar()
        self.progress_bar.set(0)
        self.status_label.configure(text=f"[Addons] {addon_type}: 0/{total}", text_color="#FF9800")
        self.update_idletasks()
        successful = []
        for idx, kw in enumerate(keywords, 1):
            self.status_label.configure(text=f"[Addons] {addon_type} {idx-1}/{total} | Vérification: {kw}", text_color="#FF9800")
            if total:
                self.progress_bar.set((idx-1)/total)
            self.update_idletasks()
            try:
                # Fetch addon (will use local exact-compatible version if offline, otherwise download)
                mgr.fetch_keyword(kw)
                successful.append(kw)
                status_msg = f"[Addons] {addon_type} {idx}/{total} | Addon: {kw}"
                self.status_label.configure(text=status_msg, text_color="#FF9800")
                if total:
                    self.progress_bar.set(idx/total)
                self.update_idletasks()
            except AddonNotFoundError as e:
                error_message = str(e)
                # Message plus clair pour le mode hors ligne
                if "pas d'accès internet" in error_message.lower():
                    msg = (
                        f"Mode hors ligne: '{kw}' n'est pas disponible localement\n"
                        f"L'addon doit être téléchargé mais il n'y a pas de connexion.\n\n"
                        f"Astuce: Lancez une fois avec une connexion internet pour\n"
                        f"télécharger l'addon dans {addon_type}_available\n\n"
                        "Continuer le lancement sans cet addon ?"
                    )
                else:
                    msg = (
                        f"Impossible de récupérer '{kw}' pour {addon_type}\n"
                        f"{error_message}\n\n"
                        "Continuer le lancement sans cet addon ?"
                    )
                if not messagebox.askyesno("Addon introuvable", msg):
                    return False
                # Avancer tout de même la progression
                status_text = "Ignoré (hors ligne)" if "pas d'accès internet" in error_message.lower() else "Ignoré (introuvable)"
                self.status_label.configure(text=f"[Addons] {addon_type} {idx}/{total} | {status_text}: {kw}", text_color="#FF9800")
                if total:
                    self.progress_bar.set(idx/total)
                self.update_idletasks()
            except Exception as e:
                msg = (
                    f"Erreur lors du téléchargement de '{kw}' ({addon_type})\n"
                    f"{type(e).__name__}: {e}\n\n"
                    "Continuer le lancement sans cet addon ?"
                )
                if not messagebox.askyesno("Erreur addon", msg):
                    return False
                self.status_label.configure(text=f"[Addons] {addon_type} {idx}/{total} | Erreur, ignoré: {kw}", text_color="#FF9800")
                if total:
                    self.progress_bar.set(idx/total)
                self.update_idletasks()
        if successful:
            try:
                installed = mgr.install_addons(successful)
                self.status_label.configure(text=f"[Addons] {addon_type} | Installés: {len(installed)} fichier(s)", text_color="#4CAF50")
                self.update_idletasks()
            except Exception as e:
                msg = (
                    f"Erreur lors de l'installation des addons {addon_type}\n"
                    f"{type(e).__name__}: {e}\n\n"
                    "Continuer le lancement sans ces addons ?"
                )
                if not messagebox.askyesno("Erreur installation addons", msg):
                    return False
                self.status_label.configure(text=f"[Addons] {addon_type} | Installation partielle/échouée", text_color="#FF9800")
                self.update_idletasks()
        return True

    def _prepare_all_addons(self):
        """Préparer/fetch/installer tous les addons selon les champs UI.

        Retourne True si on peut lancer, False si annulé par l'utilisateur.
        """
        r_text, m_text, s_text = self._get_assets_keywords_from_ui()
        r_list = self._split_keywords(r_text)
        m_list = self._split_keywords(m_text) if self._is_modded_loader() else []
        s_list = self._split_keywords(s_text) if self._is_modded_loader() else []

        if not self._prepare_addons_for_type("resourcepacks", r_list):
            return False
        if not self._prepare_addons_for_type("mods", m_list):
            return False
        if not self._prepare_addons_for_type("shaderpacks", s_list):
            return False
        return True

    def _on_assets_text_change(self, *_args):
        """Autosauvegarde des champs contenus additionnels vers le profil courant."""
        if self._suspend_assets_autosave:
            return
        r_kw, m_kw, s_kw = self._get_assets_keywords_from_ui()
        profile_name = self.profile_name.get()
        if profile_name == "Défaut" or profile_name not in self.profiles:
            return
        # Mettre à jour uniquement les champs concernés
        self.profiles[profile_name]["resource_packs_keywords"] = r_kw
        self.profiles[profile_name]["mods_keywords"] = m_kw
        self.profiles[profile_name]["shader_packs_keywords"] = s_kw
        self.save_profiles()


    def _is_modded_loader(self):
        """Retourne True si le loader sélectionné est moddé (Fabric/Forge/Neoforge)."""
        return self.loader.get() in ("Fabric", "Forge", "Neoforge")

    def _toggle_assets_section(self):
        """Étendre ou rabattre la section des champs mods/resources/shaders."""
        self.assets_section_expanded = not self.assets_section_expanded
        if self.assets_section_expanded:
            # Afficher le conteneur et les sous-champs selon le loader
            self.assets_frame.pack(fill="x", padx=10, pady=5)
            # Pack les sous-champs dans l'ordre
            self.resource_packs_frame.pack(fill="x", padx=10, pady=5)
            if self._is_modded_loader():
                self.mods_frame.pack(fill="x", padx=10, pady=5)
                self.shader_frame.pack(fill="x", padx=10, pady=5)
        else:
            # Masquer toute la section
            self.shader_frame.pack_forget()
            self.mods_frame.pack_forget()
            self.resource_packs_frame.pack_forget()
            self.assets_frame.pack_forget()

    def _update_assets_fields_visibility(self):
        """Met à jour la visibilité des champs internes selon le loader et l'état étendu."""
        # Ne rien faire si la section est rabattue
        if not self.assets_section_expanded:
            return
        # Toujours afficher le champ packs de ressources lorsque étendue
        if str(self.resource_packs_frame.winfo_manager()) == "":
            self.resource_packs_frame.pack(fill="x", padx=10, pady=5)
        # Afficher/masquer mods et shaders selon le loader
        if self._is_modded_loader():
            if str(self.mods_frame.winfo_manager()) == "":
                self.mods_frame.pack(fill="x", padx=10, pady=5)
            if str(self.shader_frame.winfo_manager()) == "":
                self.shader_frame.pack(fill="x", padx=10, pady=5)
        else:
            self.mods_frame.pack_forget()
            self.shader_frame.pack_forget()

    def _save_last_profile(self, profile_name):
        """Sauvegarder le nom du dernier profil utilisé dans un fichier dédié"""
        try:
            with open(LAST_PROFILE_FILE, 'w', encoding='utf-8') as f:
                f.write(profile_name)
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du dernier profil: {e}")

    def _load_last_profile(self):
        """Charger et appliquer le dernier profil utilisé au démarrage"""
        if not os.path.exists(LAST_PROFILE_FILE):
            # Aucun historique, charger Défaut avec dernière version disponible
            self._load_default_latest()
            return
        try:
            with open(LAST_PROFILE_FILE, 'r', encoding='utf-8') as f:
                last_profile = f.read().strip()
            # Charger le profil s'il existe, sinon fallback Défaut
            if last_profile and last_profile in self.profiles:
                self.profile_name.set(last_profile)
                if last_profile == "Défaut":
                    self._load_default_latest()
                else:
                    self.load_profile()
            else:
                self.profile_name.set("Défaut")
                self._load_default_latest()
        except Exception as e:
            print(f"Erreur lors du chargement du dernier profil: {e}")

    def _load_default_latest(self):
        """Charger le profil Défaut en forçant la dernière version disponible."""
        profile_data = self.profiles.get("Défaut", {})
        self.online_mode.set(profile_data.get("online_mode", True))
        self.pseudo.set(profile_data.get("pseudo", ""))
        self.uuid.set(profile_data.get("uuid", ""))
        self.loader.set(profile_data.get("loader", "Vanilla"))

        families = list(self.version_groups.keys())
        if families:
            latest_family = families[0]
            self.version_group.set(latest_family)
            versions = self.version_groups.get(latest_family, [])
            self.update_version_options(latest_family)
            if versions:
                self.version.set(versions[0])
        else:
            self.update_version_options()

        # Charger les paramètres avancés
        if "advanced_settings" in profile_data:
            self.advanced_settings = profile_data["advanced_settings"]
        else:
            self.advanced_settings = {
                "java_path": "",
                "mc_data_dir": "",
                "jvm_args": "",
                "quickplay_server": "",
                "quickplay_port": "25565",
                "quickplay_world": ""
            }

        print("Profil 'Défaut' chargé avec la dernière version disponible")
        self.update_ui()

if __name__ == "__main__":
    app = App()
    app.mainloop()