# @docker-clean - Complete Docker Cleanup

**PURPOSE**: Thoroughly clean all Docker resources including containers, images, volumes, networks, build cache, and Docker-in-Docker artifacts.

## IMMEDIATE ACTION

When invoked, immediately run:
```bash
docker ps -a
docker images -a
docker volume ls
docker system df
```

## WORKFLOW

### 1. Show Current State
Display:
- Running/stopped containers
- Total images (including intermediates)
- Volumes in use
- Disk usage breakdown (images, containers, volumes, cache)

### 2. Confirm Cleanup
Warn user:
```
⚠️  This will DELETE ALL:
- Containers (running and stopped)
- Images (all versions and intermediates)
- Volumes (including data!)
- Networks (custom)
- Build cache (all layers)
- Docker-in-Docker artifacts

Proceed? (y/n)
```

### 3. Execute Cleanup (if confirmed)

Run in sequence:
```bash
# Stop all running containers
docker stop $(docker ps -aq) 2>/dev/null || true

# Remove all containers
docker rm -f $(docker ps -aq) 2>/dev/null || true

# Remove all volumes (includes DinD volumes)
docker volume rm $(docker volume ls -q) 2>/dev/null || true

# Remove unused networks
docker network prune -f

# Remove all build cache
docker builder prune -af

# Remove everything else (final sweep)
docker system prune -af --volumes
```

### 4. Verify & Report

Show final state:
```bash
docker system df
docker images -a
docker ps -a
docker volume ls
```

Report:
```
✓ Cleanup complete
  - Containers removed: X
  - Images removed: X
  - Volumes removed: X
  - Space reclaimed: X.XXgb
```

## SAFETY CHECKS

Before cleanup:
- Check for running dev containers
- Warn if volumes contain data (like databases)
- List volumes by name to identify important ones

## ALTERNATIVE MODES

Support flags:
- `@docker-clean --soft`: Only unused resources (keep running containers)
- `@docker-clean --cache-only`: Only build cache
- `@docker-clean --images`: Only images and cache
- `@docker-clean --volumes`: Only volumes (dangerous!)

## WHAT GETS CLEANED

### Always Removed:
- All containers (stopped and running)
- All images (tagged and untagged)
- All custom networks
- All build cache layers
- All volumes (including named volumes)
- Docker-in-Docker storage volumes

### Preserved:
- Docker configuration (~/.docker/config.json)
- Docker contexts
- Docker daemon settings
- CLI plugins

## QUICK EXAMPLE

```
@docker-clean
→ Current state: 5 containers, 12 images, 3.2GB cache
→ ⚠️ This will delete ALL Docker resources
→ Proceed? (y/n): y
→ Stopping containers...
→ Removing containers...
→ Removing volumes...
→ Cleaning cache...
→ ✓ Complete: 5.5GB reclaimed
```
