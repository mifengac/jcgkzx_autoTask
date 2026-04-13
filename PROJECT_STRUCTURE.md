# Project Structure Guide

## Overview

This document describes the organized project structure for JCGKZX AutoTask after reorganization (as of April 2026).

## Root Level Organization

### Core Application Directories

- **autotask_api/** - Main FastAPI application code
  - `main.py` - FastAPI entry point
  - `api/` - HTTP routers and endpoints
  - `services/` - Business logic and orchestration
  - `models.py` - SQLAlchemy database models
  - `schemas.py` - Pydantic request/response schemas
  - `database.py` - Database configuration

- **frontend/** - Frontend static assets
  - HTML, CSS, and JavaScript files
  - No build step required

- **tests/** - Automated test suite
  - Unit and integration tests
  - Uses pytest framework

### Documentation & References

- **docs/** - Development and design documentation
  - `0309dev.md` - Development notes (2026-03-09)
  - `0404_jiagou_tz.md` - Architecture design notes
  - `0405_qingmingjingqing.md` - Feature documentation
  - `0407_0123_dxpt_ceshi_rule_checklist.md` - Rule checklist for messaging tests
  - `dsjjqfx.md` - External API interface documentation

- **README.md** - Project overview and quick start guide
- **DEPLOY.md** - Deployment and Docker configuration guide
- **AGENTS.md** - Agent context and development guidelines

### Database & Configuration

- **migrations/** - Database schema and migration scripts
  - `0309dev_migrate_contacts.sql` - Contact management migration
  - `0309dev_schema.sql` - Initial schema
  - `0404_theme_monitor_schema.sql` - Theme monitoring schema
  - `0408_auth_user.sql` - Authentication user table
  - `0408_b_count.sql` - Count tracking table
  - `migrate_ywdata_b_dxpt_mdjfyj.sql` - Data migration

- **config/** - Configuration files
  - `crontab` - Cron job scheduling configuration

### Examples & Templates

- **examples/** - Example and development scripts
  - `0123_dxpt_ceshi.py` - SMS platform test script (has manifest template)
  - `0310jsbrjq_monitor.py` - Monitoring script (has manifest template)
  - `data_scraper_multi.py` - Multi-source data scraper (has manifest template)
  - `monitor_wcnr_jq.py` - Content monitoring script (has manifest template)
  - `zq_kshddpt_dsjfx_jq.py` - Data fetch script (has manifest template)

- **manifest_templates/** - ZIP upload example manifests
  - Each example script has a corresponding manifest.json template

- **dist_scripts/** - Distribution and deployment scripts

### Infrastructure & Runtime

- **instantclient_11_2/** - Oracle 11g client libraries
  - Used for Oracle database connections

### Build & Dependencies

- **Dockerfile** - Container image definition
- **docker-compose.yml** - Container orchestration (run config and build args)
- **pyproject.toml** - Python project configuration (uv/pip)
- **requirements.txt** - Python dependencies
- **uv.lock** - Dependency lock file
- **.env.example** - Environment variable template

## Cleanup Summary

### Files Moved to `migrations/`
- All SQL schema and migration files (6 files)

### Files Moved to `examples/`
- 5 example/development Python scripts with corresponding manifest templates

### Files Moved to `docs/`
- 5 development documentation and specification markdown files

### Files Moved to `config/`
- Cron job configuration file

### Files Remaining at Root
- Core configuration files (pyproject.toml, requirements.txt, etc.)
- Docker compose file
- Primary documentation (README.md, DEPLOY.md, AGENTS.md)

## Usage Notes

When accessing moved files, update import paths or references:

### Example: Reference migration scripts
```bash
# Previously
cat 0309dev_schema.sql

# Now
cat migrations/0309dev_schema.sql
```

### Example: Run example scripts
```bash
# Previously
python data_scraper_multi.py

# Now
python examples/data_scraper_multi.py
```

### Example: View documentation
```bash
# Previously
cat dsjjqfx.md

# Now
cat docs/dsjjqfx.md
```

## Folder Structure Diagram

```
jcgkzx_autoTask/
├── autotask_api/              [Core Application]
│   ├── api/
│   ├── services/
│   ├── models.py
│   ├── schemas.py
│   └── database.py
├── frontend/                  [UI Assets]
├── tests/                     [Test Suite]
├── migrations/                [Database Scripts]
│   ├── 0309dev_schema.sql
│   ├── 0309dev_migrate_contacts.sql
│   ├── 0404_theme_monitor_schema.sql
│   ├── 0408_auth_user.sql
│   ├── 0408_b_count.sql
│   └── migrate_ywdata_b_dxpt_mdjfyj.sql
├── docs/                      [Documentation]
│   ├── 0309dev.md
│   ├── 0404_jiagou_tz.md
│   ├── 0405_qingmingjingqing.md
│   ├── 0407_0123_dxpt_ceshi_rule_checklist.md
│   └── dsjjqfx.md
├── examples/                  [Example Scripts]
│   ├── 0123_dxpt_ceshi.py
│   ├── 0310jsbrjq_monitor.py
│   ├── data_scraper_multi.py
│   ├── monitor_wcnr_jq.py
│   └── zq_kshddpt_dsjfx_jq.py
├── manifest_templates/        [ZIP Upload Templates]
├── config/                    [Configuration]
│   └── crontab
├── dist_scripts/
├── instantclient_11_2/        [Oracle Client]
├── docker-compose.yml         [Container run + build config]
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── README.md                  [Main Documentation]
├── DEPLOY.md                  [Deployment Guide]
├── AGENTS.md                  [Development Guidelines]
└── PROJECT_STRUCTURE.md       [This File]
```

## Next Steps

1. Update CI/CD pipelines if they reference moved files
2. Update any scripts or documentation that hard-code file paths
3. Verify manifest_templates still have correct relative paths to example scripts
4. Update team documentation to reflect new file locations
