# Deploy Scripts

All scripts are expected to run from anywhere and will auto-resolve project root.

## Docker Commands

- `./bin/deploy.sh` - build image and start service
- `./bin/restart.sh` - restart running service
- `./bin/stop.sh` - stop and remove containers
- `./bin/update.sh` - git pull (ff-only) and redeploy
- `./bin/status.sh` - show compose status
- `./bin/logs.sh [N]` - follow logs, default tail is 200 lines

## Local Commands (No Docker)

- `./bin/deploy-local.sh` - local deploy (uv sync + frontend build + start)
- `./bin/restart-local.sh` - local restart
- `./bin/stop-local.sh` - stop local process
- `./bin/update-local.sh` - git pull (ff-only) + local redeploy
- `./bin/status-local.sh` - show local process and health status
- `./bin/logs-local.sh [N]` - follow local backend logs (default 200 lines)

## Notes

- Docker scripts use `docker compose` first, and fallback to `docker-compose`.
- Local scripts manage a background process with PID file `run/market-reporter.pid` and logs in `logs/market-reporter.log`.
- `update.sh` and `update-local.sh` require a clean git working tree.
- Runtime directories `config/`, `data/`, `output/` are auto-created.
