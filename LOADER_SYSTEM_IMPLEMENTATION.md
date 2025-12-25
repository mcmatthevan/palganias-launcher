# Loader-Aware Version System Implementation

## Summary

Modified the Minecraft launcher to support loader-specific version selection. When users select a different loader (Vanilla, Fabric, Forge, Neoforge), the application now displays only compatible versions for that loader.

## Problem Solved

Previously, the version list only showed Vanilla versions regardless of the selected loader. This caused issues like:
- Fabric didn't support Beta versions like b1.7.3
- Neoforge only supports 1.20.1 and later
- Forge has different version availability than Vanilla

## Changes Made

### 1. **versions.py** - Multi-Loader Version Fetching

Added functions to fetch versions from different sources:

- `fetch_fabric_versions()`: Queries Fabric API (`meta.fabricmc.net/v2/versions/game`) for stable versions only
- `fetch_forge_versions()`: Extracts Forge-compatible versions from Mojang manifest (filters release versions only)
- `fetch_neoforge_versions()`: Filters for Neoforge-compatible versions (1.20.1+)
- `get_version_groups(loader="vanilla")`: Cache-first approach, fetches loader-specific versions
- `refresh_version_groups_async(loader, callback)`: Background refresh for specified loader

**Cache Structure:**
```json
{
  "vanilla": { "1.21.x": [...], "1.20.x": [...], ... },
  "fabric": { "1.21.x": [...], "1.20.x": [...], ... },
  "forge": { "1.21.x": [...], "1.20.x": [...], ... },
  "neoforge": { "1.21.x": [...], "1.20.x": [...], ... }
}
```

**Fallback Groups:** Hardcoded version lists per loader for offline support

### 2. **main.py** - Loader Selection Integration

- Added `LOADER_MAP` constant: Maps UI labels ("Vanilla", "Fabric", etc.) to internal names
- Modified `__init__()`: Initializes with "vanilla" loader versions
- Added `on_loader_change(value)` callback:
  - Maps UI label to internal loader name
  - Calls `get_version_groups(internal_loader)` to fetch versions
  - Updates version family combo with new families
  - Triggers async refresh in background
- Added `_on_loader_refresh_complete(groups)` callback: Updates UI when background refresh completes
- Updated loader combo to call `on_loader_change` on selection

### 3. **Import Updates**

Changed import from `refresh_version_groups` to `refresh_version_groups_async` to support async per-loader refresh.

## Feature Details

### Loader-Specific Version Availability

| Loader | Families | Notes |
|--------|----------|-------|
| **Vanilla** | 25 | Includes releases, snapshots, beta, alpha |
| **Fabric** | 8 | Stable releases only (1.17.1+) |
| **Forge** | 22 | Release versions (1.5.2+) |
| **Neoforge** | 2 | Modern versions only (1.20.1+) |

### User Experience

1. User selects a loader (e.g., "Fabric")
2. Version families automatically update to show only compatible families
3. Version list shows only versions that loader supports
4. Background refresh updates cache asynchronously without blocking UI
5. If offline: Uses cached versions or fallback hardcoded list

## Testing

Run `test_versions.py` to verify:
- All loaders return appropriate version counts
- Cache is created with proper structure
- Version filtering works correctly

## Backward Compatibility

- Existing `profiles.json` files continue to work
- Cache migration happens automatically on first load
- Offline mode still works with fallback versions

## Technical Details

### APIs Used

- **Vanilla:** Mojang manifest (`launchermeta.mojang.com`)
- **Fabric:** Meta API (`meta.fabricmc.net/v2/versions/game`) - includes `stable` flag
- **Forge:** Maven metadata + Mojang manifest
- **Neoforge:** Maven metadata + version filtering (1.20.1+)

### Performance

- First load: Fetches from APIs, caches results (10-30 seconds)
- Subsequent loads: Uses cache (instant)
- Background refresh: Async, doesn't block UI
- Offline: Uses cache or fallback (instant)

## Files Modified

- `versions.py` (215 lines → 335 lines): Added multi-loader fetching
- `main.py` (1356 lines → 1407 lines): Added loader change handling
- `versions_cache.json` (new format): Multi-loader cache structure

## Example Usage

The launcher now handles this flow:

```
User clicks "Fabric" in loader combo
  ↓
on_loader_change("Fabric") triggered
  ↓
Maps to internal name "fabric"
  ↓
Calls get_version_groups("fabric")
  ↓
Returns Fabric-compatible versions (from cache or API)
  ↓
Updates version family combo
  ↓
User can now select from Fabric-compatible versions only
  ↓
Background refresh updates cache asynchronously
```
