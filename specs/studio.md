# Studio Spec

**Status**: Placeholder
**Date**: 2026-01-04
**Depends on**: `specs/observability.md`

## Overview

fasthooks-studio is a visual debugging UI for hooks. It reads from SQLiteObserver's database and provides a web interface for exploring hook executions.

## Prerequisites

Requires observability spec implementation first:
- SQLiteObserver must be implemented and writing to `~/.fasthooks/hooks.db`
- Schema defined in observability spec

## Inspiration

See ell-studio analysis (previously in observability.md, now archived):

**Clone**: `gh repo clone MadcowD/ell /tmp/ell -- --depth 1`

### Key ell-studio Files

| File | Purpose |
|------|---------|
| `src/ell/studio/server.py` | FastAPI backend |
| `src/ell/studio/connection_manager.py` | WebSocket broadcast |
| `ell-studio/src/App.js` | React routing |
| `ell-studio/src/hooks/useBackend.js` | React Query API hooks |
| `ell-studio/src/components/depgraph/DependencyGraph.js` | ReactFlow graph |
| `ell-studio/src/components/HierarchicalTable.js` | Tree table with SVG connectors |

### Patterns to Adopt

1. **Real-time updates**: File watcher + WebSocket broadcast
2. **React Query**: Auto-cache invalidation on WebSocket messages
3. **Hierarchical visualization**: Hook → Handler tree with timing
4. **Time-series**: Aggregated stats by day/hour

## TODO

- [ ] Design SQLite schema (extend observability spec)
- [ ] Define REST API endpoints
- [ ] Design React component structure
- [ ] Implement fasthooks-studio CLI (`fasthooks studio` command)

---

*This spec will be expanded after observability implementation is complete.*
