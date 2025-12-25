# Gestion locale des addons (Mode hors ligne)

## Fonctionnement

Le launcher gère maintenant automatiquement les addons en mode hors ligne grâce à un système de cache local dans les dossiers `*_available` (mods_available, resourcepacks_available, shaderpacks_available).

### Processus de résolution d'un addon

Quand `fetch_keyword("sodium")` est appelé :

1. **Vérification locale** : Cherche d'abord si `sodium` existe dans le dossier `*_available/` avec :
   - Le bon loader (fabric/forge/neoforge)
   - La bonne version de Minecraft
   - Les métadonnées de compatibilité

2. **Si trouvé localement** : Retourne directement le fichier (pas de téléchargement)

3. **Si absent localement** : Tente de télécharger depuis Modrinth

4. **En cas d'erreur réseau** : Lève `AddonNotFoundError` avec un message explicite

### Messages utilisateur

- **Cache local** : `"Cache local: sodium"` → L'addon était déjà disponible
- **Téléchargé** : `"Téléchargé: lithium"` → L'addon a été récupéré depuis Modrinth
- **Mode hors ligne** : `"Mode hors ligne: 'iris' n'est pas disponible localement"` → Connexion requise

## Scénarios d'utilisation

### Scénario 1 - Mode connecté (téléchargement mixte)
```
Mods demandés: sodium, lithium
• sodium existe localement → utilisé directement (pas de téléchargement)
• lithium n'existe pas → téléchargé depuis Modrinth
Résultat: Les deux mods sont installés
```

### Scénario 2 - Mode hors ligne (tous locaux)
```
Mods demandés: sodium, lithium
• sodium existe localement → utilisé
• lithium existe localement → utilisé
Résultat: Les deux mods sont installés, aucune connexion requise
```

### Scénario 3 - Mode hors ligne (addon manquant)
```
Mods demandés: sodium, iris
• sodium existe localement → utilisé
• iris n'existe pas localement → échec réseau
Résultat: Erreur "Mode hors ligne: 'iris' n'est pas disponible localement"
→ Proposition de continuer sans iris ou d'annuler le lancement
```

## Préparation pour le mode hors ligne

Pour pouvoir jouer sans connexion :

1. **Lancer une fois en mode connecté** avec tous les addons souhaités
2. Les fichiers sont téléchargés dans `mods_available/`, `resourcepacks_available/`, etc.
3. Les métadonnées de compatibilité sont stockées dans `addons_metadata.json`
4. Lors des prochains lancements, même hors ligne, ces addons seront disponibles

## Avantages

- ✅ **Pas de re-téléchargement** : Les addons en cache sont réutilisés automatiquement
- ✅ **Mode hors ligne fonctionnel** : Jouer sans connexion si les addons sont en cache
- ✅ **Messages clairs** : Distinction entre "introuvable" et "hors ligne"
- ✅ **Optimisation réseau** : Télécharge uniquement ce qui manque
- ✅ **Compatibilité stricte** : Vérifie loader + version avant utilisation

## Architecture technique

```
.minecraft/
├── mods/                    # Mods actifs pour le profil actuel
├── mods_available/          # Cache de tous les mods téléchargés
│   └── palgania_launcher_sodium_sodium-fabric-0.6.8+mc1.21.11.jar
├── resourcepacks/
├── resourcepacks_available/
├── shaderpacks/
└── shaderpacks_available/

addons_metadata.json         # Registre central des métadonnées
```

Le fichier `addons_metadata.json` contient pour chaque addon :
- Le keyword original
- Les loaders compatibles (fabric, forge, neoforge)
- Les versions de Minecraft compatibles
- L'ID de version et de projet Modrinth
