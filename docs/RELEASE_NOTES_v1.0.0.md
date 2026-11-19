# Power BI Validation Tool — Release Notes v1.0.0

**Release Date:** November 2026  
**Build Status:** Production Ready (All 15 Stages Complete)  
**Test Suite:** 168 Passed / 0 Failed  

---

## 1. Executive Summary

The **Power BI Validation Tool** is an enterprise-grade, local-first Windows desktop application built with Python 3.12, PySide6 (Qt 6), SQLite (SQLAlchemy + Alembic), and Microsoft Authentication Library (MSAL). It empowers BI engineers, data quality analysts, and analytics teams to monitor semantic models, enforce row-level validation rules, detect statistical anomalies in DAX measures, and audit Power BI refresh reliability without sending proprietary data to external cloud third parties.

---

## 2. Capabilities by Stage

### Stage 0: Desktop Base & Enterprise Navigation
- Window shell with responsive navigation sidebar, consistent corporate color palette (`#F4F7FB` background, `#1668DC` primary action blue, `#0F172A` text), and smooth page transitions.

### Stage 1: Logging, Exception Handling & Reusable UI
- Secret-redacting logger ensuring access tokens, bearer headers, client secrets, and passwords are never written to disk.
- Global uncaught exception hooks for main and worker threads.
- Non-blocking notification banner (`NotificationBanner`) with Info, Success, Warning, and Error severities.

### Stage 2: Local SQLite Persistence & Alembic Migrations
- Six relational tables (`app_settings`, `workspace_registrations`, `validation_rules`, `validation_runs`, `validation_results`, `refresh_records`).
- Automated database migrations via Alembic.

### Stage 3: Microsoft Entra ID Authentication & DPAPI Token Cache
- MSAL OAuth 2.0 PKCE flow with multi-tenant support (`organizations` or custom tenant ID).
- Windows DPAPI token cache (`CryptProtectData` / `CryptUnprotectData`) for secure silent session restore across app restarts.
- Silent token acquisition and automatic renewal.

### Stage 4: Power BI REST Client & Connectivity Verifier
- Exponential backoff retry handler (`429 Too Many Requests`, `503 Service Unavailable`).
- Real-time workspace, dataset, and report access verification card with effective permission calculation.

### Stage 5: Workspace & Dataset Registry UI
- Tabular registry with active/inactive toggles and dataset deletion protection.
- Bulk import of datasets via CSV and Excel (`.xlsx`) with row-level validation and error reporting.
- Azure CLI one-click fallback for development environments.
- Support for "My Workspace" (`id="me"`).

### Stage 6: Semantic Model Metadata Discovery
- DMV schema query (`$SYSTEM.TMSCHEMA_TABLES`, `COLUMNS`, `MEASURES`) via Execute Queries REST API.
- Fallback to REST table endpoints if DMVs are restricted.
- Searchable metadata selector widget (`MetadataSelectorWidget`) with background worker fetching.

### Stage 7: Row-Based Validation Rule Configuration
- Rule configuration supporting Table Columns, DAX Measures, and Semantic Model targets.
- Interactive `RuleEditorDialog` with input validation, dynamic threshold controls, and JSON serialization.

### Stage 8: Power BI Refresh Monitoring & SLA Tracking
- Background refresh history synchronization tracking latest attempt vs latest successful refresh.
- In-progress protection: in-progress refreshes return `duration_ms = None` and render `— (In Progress)` (never false completed duration).
- Interactive `RefreshDetailsDialog` with live history table and JSON error diagnostics.

### Stage 9: DAX Query Execution Foundation
- Safe identifier escaping (`escape_measure_name`, `escape_table_name`, `escape_column_reference`).
- High-performance result parser explicitly distinguishing `BLANK()` from numeric zero `0`.
- Responsive background `QThread` execution with cancellation support.
- `DaxInspectorDialog` allowing immediate testing of measure queries.

### Stage 10: Deterministic Validation Engine
- **Null / Blank Check:** Detects missing or empty strings against count and percentage limits.
- **Duplicate Check:** Validates uniqueness on single or composite primary key columns.
- **Latest Date Check:** Enforces freshness SLAs (hours/days) and detects future date violations.
- **Row Count Check:** Compares dataset size against fixed baselines, min/max ranges, or previous run row counts.
- **Refresh Status Check:** Enforces model refresh SLAs.

### Stage 11: KPI Baseline & Historical Anomaly Engine
- Pure statistical computations (`mean`, `median`, `stdev`, `z_score`, `percentage_deviation`).
- Safe zero-baseline and negative-baseline handling without division-by-zero errors.
- Lookback window selection (7, 15, 30, 60, 90, custom days).
- Weekend filtering (`ignore_weekends`).
- Directional monitoring (`both`, `increase`, `decrease`).
- Configurable insufficient-history handling (WARNING vs ERROR).

### Stage 12: Validation Run Orchestration
- Sequential execution of enabled rules with progress tracking and cooperative cancellation.
- Overall run status calculation (`FAIL` > `ERROR` > `WARNING` > `PASS`).
- Isolated error boundaries: an unexpected error in one check is recorded as `ERROR` and does not halt subsequent checks.
- Concurrent run guard preventing accidental simultaneous runs on the same dataset.
- SQLite persistence of `ValidationRun` and `ValidationResult` records.

### Stage 13: Home Dashboard & Results Diagnostics
- Centerpiece health dashboard with "▶ Run Validation" and "Cancel" buttons.
- Five KPI summary cards: Overall Health, Passed, Failed, Warnings, Errors.
- Real-time search filter and status filter ("Failed Only", "Warnings Only", etc.).
- Interactive results table with double-click inspector.
- `ResultDetailsDialog` displaying full execution diagnostics and copy-to-clipboard functionality.

### Stage 14: History, Export & Diagnostics
- Complete execution history log with chronological sorting and status filters.
- Run-to-run comparison dialog (`RunComparisonDialog`) identifying regressions and improvements.
- CSV and styled Excel (`.xlsx`) report exports.
- Sanitized diagnostic log export with secrets redacted.
- Database backup, integrity validation, restore, and historical retention pruning.

### Stage 15: Hardening & Packaging
- Standalone executable build specification (`powerbi_validation_tool.spec`).
- Windows standard installer script (`installer/PowerBI_Validation_Tool.iss`).
- Full automated test suite passing with 168 tests.

---

## 3. Security & Data Protection Guarantees

1. **Local-First Architecture:** No data rows or semantic model schemas are sent to external third parties. All evaluations occur in memory on the user's desktop.
2. **Secret Redaction:** The redaction engine scrubs bearer tokens, client secrets, passwords, and sensitive system paths from logs, banners, dialogs, clipboard copies, and exports.
3. **Windows DPAPI Storage:** Stored MSAL authentication tokens are encrypted with `CryptProtectData` tied to the active Windows user account.
