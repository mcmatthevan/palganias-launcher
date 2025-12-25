# Problème Neoforge 1.21.11 - Gestion d'Erreur

## Problème Identifié

**Version:** Neoforge 1.21.11  
**Erreur:** `KeyError: 'ROOT'` lors de l'installation  
**Portablemc:** 4.4.1 (dernière version)

### Cause

Neoforge 1.21.11 a un problème de compatibilité avec portablemc où une variable `ROOT` est manquante dans le processus d'installation. Cela cause une exception KeyError lors du formatage des arguments du processeur.

```python
File "/portablemc/forge.py", line 321, in replace_install_args
    txt = txt.format_map(info.variables)
KeyError: 'ROOT'
```

## Solution Implémentée

### 1. Gestion d'Erreur dans `play_game()`

Ajout d'une try-except spécifique pour capturer les erreurs KeyError lors de l'installation avec messages d'erreur détaillés :

```python
try:
    env = version.install(watcher=watcher)
except KeyError as e:
    # Message d'erreur avec suggestions spécifiques
    if loader_name == "Neoforge" and version_name.startswith("1.21"):
        error_msg = "Neoforge 1.21+ a des problèmes de compatibilité.\n"
        error_msg += "Solutions suggérées:\n"
        error_msg += "1. Essayer avec Forge (même version)\n"
        error_msg += "2. Utiliser Vanilla (pas de mod loader)\n"
        error_msg += "3. Essayer une version antérieure"
```

### 2. Affichage du Message

- Message affiché dans le label de statut (en rouge)
- Bouton Play réactivé pour permettre un nouvel essai
- Erreur loggée dans `palgania-launcher.latest.log`

### 3. Statut des Loaders

| Loader | Statut | Notes |
|--------|--------|-------|
| Vanilla | ✓ Stable | Fonctionne parfaitement |
| Fabric | ✓ Stable | Toutes versions testées OK |
| Forge | ✓ Stable | Inclus 1.21.11 |
| Neoforge | ⚠️ Problème | 1.21.x n'est pas stable |

## Alternatives Recommandées

### Pour Neoforge 1.21.x

1. **Essayer une version antérieure**: Neoforge 1.20.x fonctionne correctement
2. **Utiliser Forge à la place**: Forge 1.21.11 fonctionne sans problème
3. **Signaler le bug**: https://github.com/mindstorm38/portablemc/issues

### Configuration Testée et Confirmée Fonctionnelle

```
✓ Vanilla 1.21.11
✓ Fabric 1.21.11
✓ Forge 1.21.11
⚠️ Neoforge 1.21.11 → Erreur KeyError: 'ROOT'
✓ Neoforge 1.21.10
✓ Neoforge 1.20.6
```

## Informations Techniques

**Portablemc Version:** 4.4.1 (dernière disponible)
**Python:** 3.12
**Système:** Linux

Le problème a été rapporté dans portablemc mais aucune correction n'est disponible à ce jour dans la version 4.4.1.
