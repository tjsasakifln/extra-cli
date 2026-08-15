# Isolated Makefile so this stack does not collide with the repo root targets.

.PHONY: up down ps logs probe rollback

up:
	bash ./launch.sh

down:
	bash ./rollback.sh stop

ps:
	set -a && . ./PINNED.env && . ./.env && set +a && docker compose --env-file .env ps

logs:
	set -a && . ./PINNED.env && . ./.env && set +a && docker compose --env-file .env logs --tail 80

probe:
	bash ./launch.sh

rollback:
	bash ./rollback.sh
