PYTEST ?= pytest

CPU_PERF_MARKER = perf_cpu
DB_PERF_MARKER  = perf_db

CPU_PERF_FILES = tests/perf/perf_cpu_only.py
DB_PERF_FILES  = tests/perf/perf_db_crud.py

PERF_DB_COMPOSE = docker compose -f docker-compose.perf-db.yml

PERF_RESULTS_DIR = tests/perf/results
PERF_REPORT_DIR  = tests/perf/report

GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null)

# Defaults
PERF_DB_KIND ?=
PERF_SQLITE_PATH ?= tests/perf/sqlite/perf.db

# Wait defaults
PERF_WAIT_TIMEOUT ?= 180

# ------------------------------------------------------------
# CPU-only
# ------------------------------------------------------------
perf-cpu:
	@echo "== Running CPU-bound performance tests =="
	PERF_RESULTS_DIR="$(PERF_RESULTS_DIR)" \
	PERF_RUN_ID="$$(date -u +%Y%m%dT%H%M%SZ)" \
	PERF_GIT_SHA="$(GIT_SHA)" \
	$(PYTEST) -m $(CPU_PERF_MARKER) -s $(CPU_PERF_FILES)

# ------------------------------------------------------------
# DB-bound selector
# ------------------------------------------------------------
perf-db:
	@echo "Select perf DB:"
	@echo "  1) mysql"
	@echo "  2) postgres"
	@echo "  3) sqlite"
	@printf "Enter number [1-3]: "
	@read choice; \
	case $$choice in \
		1) kind=mysql ;; \
		2) kind=postgres ;; \
		3) kind=sqlite ;; \
		*) echo "Invalid choice: $$choice"; exit 1 ;; \
	esac; \
	if [ "$$kind" = "sqlite" ]; then \
		printf "SQLite path [$(PERF_SQLITE_PATH)]: "; \
		read p; \
		p=$${p:-$(PERF_SQLITE_PATH)}; \
		$(MAKE) _perf-db-run PERF_DB_KIND=$$kind PERF_SQLITE_PATH=$$p; \
	else \
		$(MAKE) _perf-db-run PERF_DB_KIND=$$kind; \
	fi

# ------------------------------------------------------------
# DB-bound runner (up --wait + spinner)
# ------------------------------------------------------------
_perf-db-run:
ifeq ($(PERF_DB_KIND),mysql)
	@echo "== Starting perf MySQL =="
	@sh -c '\
		( $(PERF_DB_COMPOSE) up -d --build --wait --wait-timeout $(PERF_WAIT_TIMEOUT) perf-mysql >/dev/null 2>&1 ) & pid=$$!; \
		i=0; \
		while kill -0 $$pid 2>/dev/null; do \
			case $$i in 0) c="|" ;; 1) c="/" ;; 2) c="-" ;; 3) c="\\" ;; esac; \
			printf "\r[%s] waiting for perf MySQL to be running/healthy..." "$$c"; \
			i=$$(( (i+1) % 4 )); \
			sleep 1; \
		done; \
		wait $$pid; rc=$$?; \
		if [ $$rc -ne 0 ]; then printf "\n[!] perf MySQL did not become healthy (exit %s)\n" "$$rc"; exit $$rc; fi; \
		printf "\n[✓] perf MySQL is running/healthy\n"; \
	'
	@echo "== Running DB-bound performance tests (MySQL) =="
	PERF_DB_KIND="mysql" \
	PERF_DB_DSN="mysql+aiomysql://perf_user:perf_pass@127.0.0.1:3307/perf_db" \
	PERF_RESULTS_DIR="$(PERF_RESULTS_DIR)" \
	PERF_RUN_ID="$$(date -u +%Y%m%dT%H%M%SZ)" \
	PERF_GIT_SHA="$(GIT_SHA)" \
	$(PYTEST) -m $(DB_PERF_MARKER) -s $(DB_PERF_FILES)
	@echo "== Stopping perf MySQL =="
	@$(PERF_DB_COMPOSE) down -v

else ifeq ($(PERF_DB_KIND),postgres)
	@echo "== Starting perf Postgres =="
	@sh -c '\
		( $(PERF_DB_COMPOSE) up -d --build --wait --wait-timeout $(PERF_WAIT_TIMEOUT) perf-postgres >/dev/null 2>&1 ) & pid=$$!; \
		i=0; \
		while kill -0 $$pid 2>/dev/null; do \
			case $$i in 0) c="|" ;; 1) c="/" ;; 2) c="-" ;; 3) c="\\" ;; esac; \
			printf "\r[%s] waiting for perf Postgres to be running/healthy..." "$$c"; \
			i=$$(( (i+1) % 4 )); \
			sleep 1; \
		done; \
		wait $$pid; rc=$$?; \
		if [ $$rc -ne 0 ]; then printf "\n[!] perf Postgres did not become healthy (exit %s)\n" "$$rc"; exit $$rc; fi; \
		printf "\n[✓] perf Postgres is running/healthy\n"; \
	'
	@echo "== Running DB-bound performance tests (Postgres) =="
	PERF_DB_KIND="postgres" \
	PERF_DB_DSN="postgresql+asyncpg://perf_user:perf_pass@127.0.0.1:5433/perf_db" \
	PERF_RESULTS_DIR="$(PERF_RESULTS_DIR)" \
	PERF_RUN_ID="$$(date -u +%Y%m%dT%H%M%SZ)" \
	PERF_GIT_SHA="$(GIT_SHA)" \
	$(PYTEST) -m $(DB_PERF_MARKER) -s $(DB_PERF_FILES)
	@echo "== Stopping perf Postgres =="
	@$(PERF_DB_COMPOSE) down -v

else ifeq ($(PERF_DB_KIND),sqlite)
	@echo "== Running DB-bound performance tests (SQLite) =="
	@sh -c '\
		set -eu; \
		DB_PATH="$(abspath $(PERF_SQLITE_PATH))"; \
		DB_DIR="$$(dirname "$$DB_PATH")"; \
		rm -rf "$$DB_DIR"; \
		mkdir -p "$$DB_DIR"; \
		trap "rm -rf \"$$DB_DIR\"" EXIT INT TERM; \
		: > "$$DB_PATH"; \
		PERF_DB_KIND="sqlite" \
		PERF_DB_DSN="sqlite+aiosqlite:////$$DB_PATH" \
		PERF_RESULTS_DIR="$(PERF_RESULTS_DIR)" \
		PERF_RUN_ID="$$(date -u +%Y%m%dT%H%M%SZ)" \
		PERF_GIT_SHA="$(GIT_SHA)" \
		$(PYTEST) -m $(DB_PERF_MARKER) -s $(DB_PERF_FILES); \
	'

else
	@echo "Unknown PERF_DB_KIND: $(PERF_DB_KIND)"
	@exit 1
endif

# ------------------------------------------------------------
# View report
# ------------------------------------------------------------
perf-view:
	python scripts/perf_view.py \
		--results-dir "$(PERF_RESULTS_DIR)" \
		--out-dir "$(PERF_REPORT_DIR)" \
		$(if $(RUN_ID),--run-id $(RUN_ID),)

# ------------------------------------------------------------
# list report
# ------------------------------------------------------------
perf-list:
	python scripts/perf_list_runs.py
