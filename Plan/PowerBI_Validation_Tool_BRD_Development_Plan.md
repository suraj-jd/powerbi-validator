# Power BI Validation Tool

## Business Requirements Document (BRD) and Incremental Development Plan

**Version:** 1.0\
**Date:** 18 November 2026\
**Product type:** Windows desktop application\
**Initial scope:** Validate one Power BI report / semantic model, with
an architecture that can expand to multiple workspaces, reports, and
datasets.

------------------------------------------------------------------------

# 1. Executive Summary

The Power BI Validation Tool is a local-first Windows desktop
application that authenticates a user with Microsoft, connects to Power
BI workspaces and semantic models for which the user has sufficient
permissions, lets the user configure validation rules, executes those
rules, and presents clear PASS, FAIL, and WARNING results.

The application is intended to reduce manual checking of Power BI
reports after refreshes or data changes. It will check data quality,
KPI/DAX values, historical anomalies, and refresh execution details.

The first release must focus on **one registered report and its semantic
model**. The application should nevertheless use a data model that
supports multiple workspace/dataset/report registrations later without
redesigning the database.

The application is local-first: - Windows desktop UI. - Local SQLite
database for configuration and validation history. - Microsoft
authentication through OAuth/MSAL. - Power BI Service APIs for
workspace, dataset, and refresh metadata. - DAX query execution through
the supported Power BI query interface available to the tenant and
dataset. - No mandatory cloud-hosted backend in the initial release.

------------------------------------------------------------------------

# 2. Product Goals

## 2.1 Primary goals

1.  Authenticate the user using a Microsoft identity and retain the
    session securely.
2.  Verify the signed-in user can access the selected Power BI workspace
    and semantic model.
3.  Register a workspace, report, and dataset using manual entry or
    CSV/Excel import.
4.  Configure multiple independent validation rules in a tabular rule
    editor.
5.  Execute configured checks and record the actual result for every
    rule.
6.  Show a detailed results table on the home page.
7.  Retrieve refresh status, start time, end time, and duration.
8.  Compare DAX measure values or other numeric results against fixed or
    historical baselines.
9.  Store validation history locally for trend analysis and
    auditability.
10. Keep the first release understandable, reliable, and easy to extend.

## 2.2 Non-goals for the first release

-   Editing or repairing PBIX files.
-   Automatically proving that a business KPI is semantically correct
    without an expected value or business rule.
-   Automatically understanding every visual's intended meaning from a
    screenshot.
-   Replacing Power BI Service monitoring or administration.
-   Cloud-hosted multi-user administration.
-   Automatically validating every measure in a model without user
    selection.
-   Automatic report visual pixel comparison.
-   Running unattended as a Windows service before interactive
    authentication and scheduling are designed.

------------------------------------------------------------------------

# 3. Users and Main Use Case

## Primary user

A Power BI report owner, workspace administrator, member, or contributor
who has been granted the required permissions to inspect a workspace,
semantic model, execute permitted queries, and view refresh history.

**Important:** Microsoft sign-in alone does not prove workspace
ownership. The application must check actual workspace/dataset
permissions and display the effective access level. It must not label
someone "Owner" unless the available Microsoft API data explicitly
supports that conclusion.

## Main use case

1.  User launches the desktop application.
2.  User signs in with Microsoft.
3.  Application validates the account and required Power BI access.
4.  User adds one workspace/report/dataset.
5.  User selects tables, columns, and measures for validation.
6.  User configures validation type and any rule-specific conditions.
7.  User saves the configuration.
8.  User clicks **Run Validation**.
9.  Application retrieves current values, refresh metadata, and required
    data.
10. Validation engine evaluates every rule.
11. Home page displays summary KPIs and a row-by-row result table.
12. User opens a failed row to see expected value, actual value,
    deviation, and failure reason.
13. Results are stored in local history.

------------------------------------------------------------------------

# 4. User Interface Requirements

## 4.1 Main navigation

The desktop application should use a clean light enterprise theme: -
White workspace. - Dark navy sidebar. - Blue primary actions. - Green
PASS, red FAIL, amber WARNING. - Dense but readable tables. - Resizable
window and scrollable content. - Consistent spacing, typography, and
control sizes.

Main navigation: 1. Home 2. Settings 3. History 4. About

The signed-in account and Sign out action should remain visible in the
sidebar or account area.

## 4.2 Home / Dashboard page

### A. Authentication banner

Display: - Signed-in user display name. - Signed-in email address. -
Authentication status. - Workspace access status for the selected
workspace. - Switch Account action. - Sign Out action.

Never display access tokens, refresh tokens, client secrets, or
passwords.

### B. Run summary cards

Display: - Total checks executed. - Passed checks. - Failed checks. -
Warnings. - Overall health percentage.

Health percentage should be calculated consistently and documented. A
suggested initial formula is:

`Passed checks / (Passed checks + Failed checks + Warnings) * 100`

If no checks have run, show "Not yet validated" rather than 0% or 100%.

### C. Report overview

Display: - Workspace name. - Workspace ID. - Report name. - Report ID,
if registered. - Semantic model / dataset name. - Dataset ID. - Latest
known refresh status. - Last refresh completion time. - Last validation
time.

### D. Validation results table

The primary result table must include these columns:

  -----------------------------------------------------------------------
  Column                              Description
  ----------------------------------- -----------------------------------
  SR                                  Sequential row number for this run

  Workspace Name                      Registered workspace name

  Report Name                         Registered report name

  Validation Check                    Null, Duplicate, Latest Date, DAX
                                      Measure, Anomaly, Refresh, etc.

  Table Name                          Table used by the rule; blank where
                                      not applicable

  Column / Measure Name               Target column or measure

  Actual Value                        Value returned by the check

  Expected / Baseline                 Expected value or comparison
                                      baseline, when applicable

  Deviation                           Actual deviation, when applicable

  Status                              PASS, FAIL, WARNING, or ERROR

  Details                             Short explanation and reason
  -----------------------------------------------------------------------

The table should support: - Sorting. - Filtering by status and
validation type. - Search. - Opening a result for full details. - Export
to CSV/Excel in a later stage.

Do not force table or column values for checks where they do not apply,
such as refresh checks.

### E. Refresh execution details

Refresh monitoring must show: - Refresh status: Success, Failed, In
Progress, Unknown. - Refresh start time. - Refresh end time, if
completed. - Total duration. - Refresh type, if available. - Refresh
request / refresh ID, if available. - Error detail, if the API returns
one.

Refresh status and KPI/data validation status are independent. A
successful refresh does not mean the data is correct.

### F. Validation history

Show previous runs with: - Date and time. - Overall status. - Passed /
failed / warning counts. - Duration. - Report name. - Open details
action.

History must be retained locally and must not be overwritten by a new
run.

------------------------------------------------------------------------

# 5. Settings Page Requirements

Settings should be divided into manageable sections. The initial
implementation may show all sections on one scrollable page, but each
section should have a clear boundary.

## 5.1 Workspace, report, and dataset registry

Support two entry methods:

### Manual table entry

The user must be able to add multiple registrations. Each row contains:

  Field                           Required      Description
  ------------------------------- ------------- -----------------------------------------------------
  Workspace Name                  Yes           Friendly workspace name
  Workspace ID                    Yes           Power BI workspace GUID
  Report Name                     Yes           Friendly report name
  Report ID                       Recommended   Power BI report GUID
  Dataset / Semantic Model Name   Recommended   Friendly model name
  Dataset ID                      Yes           Semantic model GUID
  Active                          Yes           Whether this registration is included in validation

Actions: - Add row. - Edit row. - Delete row. - Validate IDs / Verify
Access. - Save registrations.

The first release only needs one active registration for execution, but
the UI and database should permit more than one.

### CSV / Excel import

Support: - CSV. - XLSX.

The import workflow must: 1. Show a template or required column names.
2. Preview the imported rows. 3. Validate GUID formats and required
fields. 4. Identify missing values and duplicate IDs. 5. Show row-level
import errors. 6. Allow the user to correct or skip invalid rows. 7.
Confirm before saving.

Do not silently discard invalid rows.

Suggested template columns:

`WorkspaceName,WorkspaceId,ReportName,ReportId,DatasetName,DatasetId,Active`

## 5.2 Validation rule editor

Validation rules must be configured as a table, with one row
representing one independent rule.

Suggested columns:

  Field                   Description
  ----------------------- -------------------------------------
  SR                      Rule sequence
  Enabled                 Include / exclude this rule
  Table Name              Table to inspect
  Column / Measure Name   Target column or measure
  Target Type             Column, Measure, or Model / Refresh
  Validation Check        Type of check
  Conditions / Summary    Human-readable summary of the rule
  Advanced                Opens row-specific configuration
  Action                  Edit / Duplicate / Delete

Actions: - Add Validation Rule. - Duplicate Rule. - Delete Rule. -
Enable / Disable Rule. - Reorder Rule. - Save Rules.

The editor must not require a table/column for model-level refresh
checks. A DAX measure rule must identify the measure and, where
necessary, its table or home table.

## 5.3 Validation types and required configuration

### A. Null / Blank Check

Inputs: - Table. - Column. - Null definition: database null, DAX BLANK,
empty string, whitespace-only string, or selected combination. -
Optional allowed blank count or percentage. - Optional filter condition.

Output: - Null count. - Total rows checked. - Null percentage. - PASS /
FAIL / WARNING.

### B. Duplicate Check

Inputs: - Table. - One or more key columns. - Duplicate definition:
exact duplicate row or duplicate key combination. - Allowed duplicate
count, default zero. - Optional filter condition.

Output: - Duplicate count. - Duplicate key count. - Sample duplicate
keys, where safe and practical. - PASS / FAIL / WARNING.

### C. Latest Date Check

Inputs: - Table. - Date column. - Expected freshness window, such as
maximum age in hours/days. - Optional timezone. - Optional allowed
future-date behavior.

Output: - Latest date found. - Current comparison time. - Age of latest
data. - PASS / FAIL / WARNING.

### D. Row Count Check

Inputs: - Table or a defined DAX expression. - Baseline method: fixed
value, previous run, or historical period. - Allowed absolute or
percentage deviation. - Optional minimum / maximum.

Output: - Current row count. - Baseline. - Difference and percentage
deviation. - PASS / FAIL / WARNING.

### E. DAX Measure Check

Inputs: - Measure name. - Optional table / home table. - Optional DAX
query filter context. - Expected-value method: - Fixed baseline. -
Minimum / maximum. - Previous successful run. - Historical mean. -
Historical median. - Historical mode, only where meaningful. - Previous
day / week / month. - Allowed deviation. - Optional minimum historical
sample count.

Output: - DAX value fetched. - Baseline / expected range. - Absolute
difference. - Percentage deviation, where mathematically valid. - PASS /
FAIL / WARNING.

### F. Anomaly Check

Anomaly checks should be configured per rule, not globally only.

Required inputs: - Target table and column or DAX measure. -
Aggregation: SUM, COUNT, DISTINCTCOUNT, AVERAGE, MIN, MAX, or selected
DAX measure. - Time/date column, if time-series comparison is
required. - Comparison method. - Lookback period. - Allowed deviation. -
Minimum historical observations. - Optional ignore weekends. - Optional
minimum and maximum bounds.

Supported comparison methods: 1. Fixed baseline. 2. Previous period. 3.
Historical mean. 4. Historical median. 5. Historical mode, only for
discrete/repeated values. 6. Standard deviation / Z-score. 7. Previous
successful validation run.

The UI should show the advanced controls relevant to the selected
method. Do not show irrelevant fields for every method.

### G. Refresh Check

Inputs: - Dataset ID from the selected registration. - Expected refresh
status. - Optional maximum refresh age. - Optional maximum duration. -
Optional acceptable refresh types, if needed.

Output: - Refresh status. - Start time. - End time. - Duration. - Error
details, if available. - PASS / FAIL / WARNING.

Refresh checks are model-level rules and do not require table or column
names.

## 5.4 Row-specific advanced settings

Each rule row must have its own Advanced action. Opening it should show
only the settings for that rule.

Example for a DAX anomaly rule: - Measure: Total Active Employees. -
Method: Historical Median. - Lookback: Last 30 completed days. - Allowed
deviation: 10%. - Minimum historical observations: 20. - Ignore
weekends: Yes. - Direction: Flag increase, decrease, or both. - Missing
history behavior: Warning / Fail / Skip.

A setting changed for one rule must not unintentionally modify another
rule.

------------------------------------------------------------------------

# 6. Result Status and Evaluation Rules

Use four statuses:

-   **PASS:** The check executed successfully and met the configured
    condition.
-   **FAIL:** The check executed successfully but violated the
    configured condition.
-   **WARNING:** The result is inconclusive, historical data is
    insufficient, a freshness threshold is near its limit, or a
    configured warning condition was met.
-   **ERROR:** The check could not execute because of permissions, query
    failure, missing object, unsupported operation, or connectivity
    issue.

Do not treat an execution error as a data-quality failure. Keep ERROR
distinct so the user knows the rule did not produce a trustworthy
result.

## 6.1 Deviation calculation

For a non-zero baseline:

`Deviation % = ((Actual Value - Baseline) / ABS(Baseline)) * 100`

For a zero baseline, percentage deviation is undefined. Use absolute
difference or a separately configured zero-baseline rule. Do not divide
by zero.

For two-sided tolerance:

`PASS when ABS(Actual - Baseline) <= Allowed Absolute Deviation`

or:

`PASS when ABS(Deviation %) <= Allowed Deviation %`

The rule must state whether it is: - Two-sided tolerance. - Minimum
threshold. - Maximum threshold. - Expected range.

## 6.2 Historical comparisons

Historical calculations must use comparable periods and a documented
date boundary.

Recommended defaults: - Compare completed days rather than partial
current-day data. - Store the timestamp and time zone used for each
run. - Exclude the current incomplete period when the selected rule
requires it. - Do not silently treat missing dates as zero. - Require a
minimum number of valid historical observations. - Mark insufficient
history as WARNING or ERROR according to the rule configuration.

Mean, median, and standard deviation are generally useful for numeric
measures. Mode is most useful for discrete or frequently repeated
values; it may be meaningless for continuously varying numeric values.

For seasonal data, consider same weekday or same period comparisons
later. A simple last-N-days average can create false alerts when normal
weekday/weekend patterns exist.

------------------------------------------------------------------------

# 7. Refresh Monitoring Requirements

Refresh information should be retrieved from the Power BI refresh
history endpoint where available and permitted.

For each refresh record, store: - Dataset ID. - Refresh ID / request ID,
if returned. - Status. - Start time. - End time. - Duration calculated
from start and end timestamps. - Refresh type, if returned. - Error
details, if returned. - Time retrieved.

If a refresh is still running, end time and duration should be displayed
as In Progress / elapsed duration, not as a completed duration.

The application should clearly distinguish: - Latest refresh attempt. -
Latest successful refresh. - Latest completed refresh.

The user should be able to select which definition a rule validates.

------------------------------------------------------------------------

# 8. Authentication, Authorization, and Security

## 8.1 Authentication

Use Microsoft Authentication Library (MSAL) with OAuth 2.0 / OpenID
Connect.

Support: - Organizational Microsoft Entra ID accounts. - Personal
Microsoft accounts only where the configured app registration, Power BI
resource, and tenant policies support them.

Power BI workspace access is generally associated with an organizational
tenant. Personal Microsoft account sign-in must not be presented as
guaranteed Power BI access.

Use the system browser or MSAL-supported interactive sign-in flow. Do
not build a username/password form.

## 8.2 Token persistence

-   Use MSAL token cache.
-   Persist the cache using Windows-protected storage, such as Windows
    DPAPI-backed protection.
-   Do not store raw access tokens or refresh tokens in SQLite.
-   Support token refresh and interactive reauthentication when
    required.
-   Provide Sign Out and clear local token cache on user request.

## 8.3 Permission verification

After sign-in: 1. Retrieve the signed-in account identity. 2. Request
only the scopes required for the feature being used. 3. Query the
workspace and dataset using the signed-in identity. 4. Verify the
required access. 5. Display the actual access result. 6. Provide a clear
message when access is insufficient.

Do not infer ownership from a successful login. Use the actual
permission data available from Microsoft APIs.

## 8.4 Local data security

-   Store configuration and run history in SQLite.
-   Store no passwords.
-   Protect the MSAL cache separately.
-   Avoid logging access tokens, secrets, or sensitive row-level
    business data.
-   Provide a way to delete local configuration and history.
-   Consider a configurable retention policy for validation history.

------------------------------------------------------------------------

# 9. Recommended Technology Stack

  -----------------------------------------------------------------------
  Layer                   Technology              Reason
  ----------------------- ----------------------- -----------------------
  Language                Python 3.12 or a        Mature ecosystem,
                          supported current       readable code, strong
                          Python release          data tooling

  Desktop UI              PySide6 (Qt for Python) Native-feeling Windows
                                                  desktop UI, tables,
                                                  dialogs, model/view
                                                  architecture

  UI architecture         Qt Model/View           Efficient editable
                                                  tables for workspace
                                                  and validation rules

  Authentication          MSAL for Python         Microsoft-supported
                                                  authentication library

  Token protection        Windows DPAPI via an    Protect cached
                          appropriate Python      authentication data on
                          package / Windows       the local machine
                          Credential APIs         

  HTTP/API                httpx or requests       Communicate with
                                                  Microsoft REST APIs

  API models              Pydantic                Validate API responses
                                                  and application
                                                  configuration

  Local database          SQLite                  No database server
                                                  required; ideal for
                                                  local-first single-user
                                                  application

  ORM / migrations        SQLAlchemy + Alembic    Maintainable database
                                                  access and safe schema
                                                  evolution

  Data processing         Pandas                  CSV/Excel import,
                                                  result processing,
                                                  historical data
                                                  preparation

  Excel import/export     openpyxl                Read/write XLSX files

  CSV                     Python standard `csv`   Simple and reliable CSV
                          module                  handling

  DAX / model access      Power BI Execute        Retrieve semantic model
                          Queries REST API where  measure values
                          supported;              
                          XMLA/ADOMD.NET as a     
                          separately validated    
                          integration path        

  Power BI metadata       Power BI REST APIs      Workspace, report,
                                                  dataset and refresh
                                                  metadata

  Statistics              NumPy + SciPy           Mean, median, standard
                                                  deviation and
                                                  statistical
                                                  calculations

  Anomaly algorithms      Initially deterministic Avoid unnecessary ML
                          Python rules;           complexity in the first
                          scikit-learn only if    release
                          later justified         

  Charts                  PySide6 Qt Charts or    Show trends and anomaly
                          Plotly embedded in Qt   context

  Logging                 Python `logging` with   Troubleshooting without
                          rotating file handler   exposing secrets

  Testing                 pytest + pytest-qt      Unit and UI testing

  Packaging               PyInstaller             Build a Windows
                                                  executable

  Installer               Inno Setup              Produce a user-friendly
                                                  Windows installer

  Version control         Git                     Small, reviewable
                                                  development stages
  -----------------------------------------------------------------------

## 9.1 Power BI integration decision

The application must not assume every Power BI tenant or dataset
supports every API.

### Power BI REST APIs

Use REST APIs for: - Listing accessible workspaces. - Reading reports
and datasets. - Checking available metadata. - Reading refresh
history. - Triggering refresh only if that feature is added and the user
explicitly enables it.

### DAX execution

Preferred initial path: - Use the Power BI Execute Queries REST API if
the tenant admin has enabled it, the dataset and user meet its
requirements, and the query limitations are acceptable.

Alternative path: - XMLA endpoint / ADOMD.NET for datasets and
capacities where XMLA connectivity is available and the user has the
necessary permissions and licensing.

The XMLA path may require a Windows/.NET bridge or a small helper
process. Keep it behind a connector interface so the validation engine
is not tied to one connection method.

### Local PBIX / Power BI Desktop

Directly connecting to a locally open PBIX model is a separate
integration scenario. It may use the local Analysis Services instance
exposed by Power BI Desktop, but the local port and lifecycle are
dynamic. Do not assume a PBIX file can be queried as a normal file.

The initial product should prioritize the authenticated Power BI Service
path. Add local Desktop/PBIX connectivity only after the Service-based
MVP works reliably.

------------------------------------------------------------------------

# 10. High-Level Architecture

Use a layered architecture:

1.  **Presentation layer**
    -   PySide6 windows, pages, dialogs, tables, and user interaction.
2.  **Application / service layer**
    -   Authentication service.
    -   Workspace registry service.
    -   Rule configuration service.
    -   Validation orchestration service.
    -   History service.
3.  **Connector layer**
    -   Microsoft identity connector.
    -   Power BI REST connector.
    -   DAX query connector.
    -   Excel/CSV import connector.
4.  **Validation engine**
    -   Null validator.
    -   Duplicate validator.
    -   Latest-date validator.
    -   Row-count validator.
    -   DAX-value validator.
    -   Anomaly validator.
    -   Refresh validator.
5.  **Persistence layer**
    -   SQLite database.
    -   Protected MSAL token cache.
    -   Application settings.
    -   Local logs.

A validation rule should be represented as configuration data, not as a
custom hard-coded code branch in the UI.

------------------------------------------------------------------------

# 11. Suggested Project Structure

``` text
powerbi_validation_tool/
│
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   │
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── pages/
│   │   │   ├── home_page.py
│   │   │   ├── settings_page.py
│   │   │   └── history_page.py
│   │   ├── dialogs/
│   │   ├── models/
│   │   └── widgets/
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   ├── logging_config.py
│   │   └── status.py
│   │
│   ├── auth/
│   │   ├── msal_auth.py
│   │   └── token_cache.py
│   │
│   ├── integrations/
│   │   └── powerbi/
│   │       ├── rest_client.py
│   │       ├── workspace_client.py
│   │       ├── dataset_client.py
│   │       ├── refresh_client.py
│   │       ├── dax_client.py
│   │       └── xmla_client.py
│   │
│   ├── validation/
│   │   ├── orchestrator.py
│   │   ├── base.py
│   │   ├── null_check.py
│   │   ├── duplicate_check.py
│   │   ├── latest_date_check.py
│   │   ├── row_count_check.py
│   │   ├── dax_measure_check.py
│   │   ├── anomaly_check.py
│   │   └── refresh_check.py
│   │
│   ├── services/
│   │   ├── registry_service.py
│   │   ├── rule_service.py
│   │   ├── validation_service.py
│   │   └── history_service.py
│   │
│   └── database/
│       ├── db.py
│       ├── models.py
│       └── repositories/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── ui/
│
├── assets/
├── scripts/
├── docs/
├── requirements.txt
├── pyproject.toml
├── README.md
└── .gitignore
```

Do not create every file as empty scaffolding on day one. Add modules
when their stage begins.

------------------------------------------------------------------------

# 12. Database Design

Use SQLite with migrations. The initial schema should include these
logical entities.

## 12.1 `app_settings`

Stores non-secret preferences: - Setting key. - Setting value. - Updated
timestamp.

Do not store tokens or secrets here.

## 12.2 `workspace_registrations`

-   ID (local primary key).
-   Workspace name.
-   Workspace ID.
-   Report name.
-   Report ID (nullable).
-   Dataset name.
-   Dataset ID.
-   Active flag.
-   Created timestamp.
-   Updated timestamp.

Workspace ID + Dataset ID should be protected against accidental
duplicate registrations. Report identity should be handled where more
than one report can use the same dataset.

## 12.3 `validation_rules`

-   ID.
-   Workspace registration ID.
-   Rule name.
-   Enabled flag.
-   Target type: COLUMN, MEASURE, MODEL.
-   Table name (nullable).
-   Column name (nullable).
-   Measure name (nullable).
-   Validation type.
-   Configuration JSON.
-   Display order.
-   Created timestamp.
-   Updated timestamp.

Store advanced, rule-specific settings in validated JSON or normalized
child tables. Start with JSON for flexibility, but validate its schema
by rule type.

## 12.4 `validation_runs`

-   ID.
-   Workspace registration ID.
-   Started timestamp.
-   Completed timestamp.
-   Overall status.
-   Passed count.
-   Failed count.
-   Warning count.
-   Error count.
-   Duration milliseconds.
-   Application version.

## 12.5 `validation_results`

-   ID.
-   Validation run ID.
-   Validation rule ID.
-   Status.
-   Actual value (safe serialized representation).
-   Expected value / baseline.
-   Deviation.
-   Result summary.
-   Detailed message.
-   Started timestamp.
-   Completed timestamp.

## 12.6 `refresh_records`

-   ID.
-   Workspace registration ID.
-   Dataset ID.
-   Refresh ID.
-   Status.
-   Start timestamp.
-   End timestamp.
-   Duration milliseconds.
-   Refresh type.
-   Error details.
-   Retrieved timestamp.

Keep raw API payloads only when they are needed for diagnostics, and
remove secrets or unnecessary sensitive data before persistence.

------------------------------------------------------------------------

# 13. Incremental Development Plan

Each stage should be small enough to build, run, test, and commit
independently. Do not ask a coding agent to implement several stages in
one large task.

## Stage 0 --- Create the base Python desktop application

**Goal:** A runnable Windows desktop shell with no Power BI connection
yet.

Tasks: 1. Create the Git repository. 2. Create a Python virtual
environment. 3. Add the initial dependency file. 4. Create the
application entry point. 5. Create a PySide6 main window. 6. Add the
left navigation: Home, Settings, History, About. 7. Add placeholder
pages. 8. Add application title, version, and window icon placeholder.
9. Add basic logging. 10. Add a clean exit flow.

Acceptance criteria: - Application starts with one command. - Main
window opens without errors. - Navigation changes pages. - Window
resizes correctly. - No Power BI credentials or network calls are
needed.

Suggested commit: `stage-0: create base PySide6 desktop application`

## Stage 1 --- Establish application structure and configuration

**Goal:** Make the project maintainable before adding integrations.

Tasks: 1. Create the agreed module structure. 2. Add central
configuration handling. 3. Add application-wide exception handling. 4.
Add rotating local log files. 5. Add a small reusable notification /
message component. 6. Add a reusable table widget or Qt model pattern.
7. Add a reusable confirmation dialog. 8. Add a simple About page with
app version.

Acceptance criteria: - UI code does not contain Power BI API logic. -
Errors are logged without exposing secrets. - Reusable UI components
work in a small demonstration.

Suggested commit:
`stage-1: establish app architecture and shared components`

## Stage 2 --- Local SQLite foundation

**Goal:** Persist local app configuration safely.

Tasks: 1. Add SQLite connection management. 2. Add SQLAlchemy models. 3.
Add Alembic migrations. 4. Create `app_settings`. 5. Create
`workspace_registrations`. 6. Create `validation_rules`. 7. Create
`validation_runs`. 8. Create `validation_results`. 9. Create
`refresh_records`. 10. Add repository methods for create, read, update,
and delete. 11. Add database backup / restore design notes; implement
later.

Acceptance criteria: - Database is created automatically on first
launch. - Data survives app restart. - CRUD tests pass. - A migration
can upgrade an existing database. - No authentication tokens are stored
in SQLite.

Suggested commit: `stage-2: add local SQLite database and repositories`

## Stage 3 --- Microsoft authentication

**Goal:** Sign in and retain a secure Microsoft session.

Tasks: 1. Create / configure a Microsoft Entra app registration. 2.
Decide supported account types and tenant configuration. 3. Configure
only the required delegated Power BI permissions. 4. Add MSAL. 5.
Implement interactive sign-in. 6. Display signed-in user name and email.
7. Add secure token cache persistence using Windows-protected storage.
8. Implement silent token acquisition. 9. Handle expired sessions and
interactive reauthentication. 10. Add Switch Account and Sign Out. 11.
Add an authentication status indicator.

Acceptance criteria: - User can sign in successfully. - Account details
are displayed. - App can obtain a valid Power BI access token. -
Restarting the app can restore the session where the cache remains
valid. - Expired or revoked sessions are handled cleanly. - Sign Out
clears the local authentication cache. - No password or raw token is
displayed or written to logs.

Important: - Microsoft app registration and tenant consent may require
an administrator. - Personal Microsoft account support depends on app
registration and Power BI resource support; do not assume every personal
account can access Power BI workspaces.

Suggested commit:
`stage-3: implement Microsoft authentication and secure token cache`

## Stage 4 --- Power BI connectivity and permission verification

**Goal:** Confirm the authenticated user can access a workspace and
dataset.

Tasks: 1. Create a reusable HTTP client. 2. Add safe API error handling
and request timeouts. 3. Add token acquisition to API requests. 4.
Implement a basic "Get My Accessible Workspaces" call. 5. Implement
workspace detail retrieval. 6. Implement dataset listing for a
workspace. 7. Implement report listing where available. 8. Verify access
to a manually supplied workspace ID. 9. Verify the dataset ID belongs to
/ is accessible in the expected workspace. 10. Display actual
permission/access information where available. 11. Add clear messages
for unauthorized, forbidden, not found, and throttled responses.

Acceptance criteria: - A valid workspace can be retrieved. - A wrong
workspace ID produces a clear error. - An inaccessible workspace is not
incorrectly labelled as owned. - Dataset selection can be verified. -
API calls use the signed-in user's identity.

Suggested commit:
`stage-4: connect Power BI REST APIs and verify access`

## Stage 5 --- Workspace, report, and dataset registry UI

**Goal:** Let the user maintain registrations.

Tasks: 1. Build the registration table. 2. Add manual Add / Edit /
Delete. 3. Add fields for Workspace Name and ID. 4. Add Report Name and
optional Report ID. 5. Add Dataset Name and ID. 6. Add Active /
Inactive. 7. Add GUID format validation. 8. Add Verify Access action. 9.
Save registrations to SQLite. 10. Load saved registrations at startup.
11. Add CSV import. 12. Add XLSX import. 13. Add import preview and
row-level validation errors. 14. Add an exportable blank template.

Acceptance criteria: - User can manually add and save a registration. -
Multiple registrations can be stored. - Invalid GUIDs are rejected with
helpful messages. - CSV/XLSX import preview works. - Duplicate
registrations are detected. - App restart retains registrations. -
First-run execution can still be limited to one selected report.

Suggested commit:
`stage-5: add workspace dataset registry and file import`

## Stage 6 --- Discover semantic model metadata

**Goal:** Help the user select valid tables, columns, and measures
rather than typing every object name.

Tasks: 1. Confirm which metadata API path is available for the target
dataset. 2. Retrieve table and column metadata where supported. 3.
Retrieve measure metadata where supported. 4. Display tables in a
searchable selector. 5. Display columns for the selected table. 6.
Display available measures. 7. Allow manual entry as a fallback. 8.
Validate that selected objects exist before saving a rule. 9. Handle
unsupported metadata access without crashing.

Acceptance criteria: - User can select a table and column from retrieved
metadata where supported. - User can select a measure where supported. -
Manual entry remains available. - Invalid object names are flagged
before a full validation run. - No claim is made that metadata discovery
is available for every dataset/API combination.

Suggested commit:
`stage-6: discover semantic model tables columns and measures`

## Stage 7 --- Validation rule editor (configuration only)

**Goal:** Build the row-based rule editor without executing Power BI
checks yet.

Tasks: 1. Build the validation rules table. 2. Add columns: SR, Enabled,
Target Type, Table, Column/Measure, Validation Type, Conditions,
Advanced, Action. 3. Add a new rule dialog / row editor. 4. Add edit,
duplicate, delete, enable/disable, and reorder. 5. Add validation type
selector. 6. Show relevant target fields for each validation type. 7.
Add per-rule Advanced Settings dialog. 8. Validate required fields by
rule type. 9. Save rules to SQLite. 10. Reload rules after app restart.

Acceptance criteria: - User can create multiple independent rules. -
Every row has its own configuration. - Refresh rules do not require
table/column values. - DAX measure rules require a measure. - Column
rules require a table and column. - Advanced settings for one row do not
modify another. - Rules persist across restarts.

Suggested commit:
`stage-7: build row-based validation rule configuration`

## Stage 8 --- Power BI refresh monitoring

**Goal:** Retrieve refresh history and display its details.

Tasks: 1. Implement refresh history API client. 2. Retrieve latest
refresh records for the selected dataset. 3. Map API refresh statuses
into application statuses. 4. Parse start and end timestamps. 5.
Calculate duration from timestamps. 6. Handle in-progress refreshes. 7.
Distinguish latest attempt from latest successful refresh. 8. Store
refresh records locally. 9. Add a refresh details view. 10. Implement
Refresh Check rule evaluation.

Acceptance criteria: - Latest refresh attempt is shown. - Status, start,
end, and duration are displayed when returned by the API. - Failed
refresh details are shown where available. - In-progress refreshes do
not display a false completed duration. - Refresh result is independent
of KPI results.

Suggested commit:
`stage-8: implement refresh history and refresh validation`

## Stage 9 --- DAX query execution foundation

**Goal:** Fetch a selected measure value from the semantic model.

Tasks: 1. Confirm Execute Queries API eligibility for the target tenant
and dataset. 2. Verify required tenant settings, permissions, and query
limitations. 3. Implement a DAX query client. 4. Add query timeout and
cancellation handling. 5. Execute a simple, safe test query. 6. Execute
a query for one selected measure. 7. Parse numeric, text, blank, and
error results. 8. Display the fetched value in a test screen. 9. Add an
integration test against a permitted test dataset. 10. Define an
XMLA/ADOMD.NET connector interface for environments where Execute
Queries is unavailable.

Acceptance criteria: - A selected measure can be queried where the API
path is supported. - BLANK is distinguished from zero. - Query failures
are reported as ERROR, not FAIL. - Query execution does not block the
UI. - DAX queries are constructed safely and do not accept arbitrary
untrusted query fragments.

Suggested commit: `stage-9: implement DAX measure query connector`

## Stage 10 --- Basic data validation engine

**Goal:** Implement deterministic checks before anomaly detection.

Build and test each validator separately:

### 10A. Null / blank check

-   Query null / blank counts.
-   Calculate percentage.
-   Apply allowed threshold.
-   Return actual count, percentage, and status.

### 10B. Duplicate check

-   Support one or multiple key columns.
-   Count duplicate keys.
-   Return count and status.

### 10C. Latest date check

-   Retrieve maximum date.
-   Calculate data age.
-   Compare against freshness threshold.

### 10D. Row count check

-   Retrieve row count.
-   Compare against fixed minimum / maximum or previous successful run.

Acceptance criteria: - Each check has unit tests. - Each check returns
the same standard result structure. - Empty tables and blank values are
handled explicitly. - Query errors produce ERROR. - The UI can show the
actual value and reason.

Suggested commits: - `stage-10a: implement null validation` -
`stage-10b: implement duplicate validation` -
`stage-10c: implement latest date validation` -
`stage-10d: implement row count validation`

## Stage 11 --- KPI baseline and anomaly engine

**Goal:** Compare DAX or aggregated values with expected and historical
values.

Tasks: 1. Define a standard numeric comparison service. 2. Implement
fixed baseline. 3. Implement minimum and maximum bounds. 4. Implement
absolute deviation. 5. Implement percentage deviation. 6. Implement
previous successful run comparison. 7. Implement historical mean. 8.
Implement historical median. 9. Implement historical standard deviation
/ Z-score. 10. Implement mode only for appropriate discrete values. 11.
Implement lookback windows: 7, 15, 30, 60, 90 days, and custom. 12.
Implement minimum historical sample requirements. 13. Implement
ignore-weekends option. 14. Implement direction selection: increases,
decreases, or both. 15. Implement insufficient-history handling. 16. Add
tests for zero baseline, negative baseline, missing periods, and
outliers.

Acceptance criteria: - Each anomaly rule uses its own saved settings. -
Current and baseline values are visible. - Deviation calculation is
correct. - Zero baseline does not cause division by zero. - Insufficient
history produces the configured WARNING / ERROR behavior. - Historical
data is not silently filled with zero.

Suggested commit:
`stage-11: implement KPI baseline and historical anomaly engine`

## Stage 12 --- Validation orchestration

**Goal:** Execute all enabled rules for the selected report and store a
complete run.

Tasks: 1. Create the validation orchestrator. 2. Load active
registration and enabled rules. 3. Run checks in a controlled sequence.
4. Show progress by rule. 5. Support cancellation between checks. 6.
Capture start and end time for each check. 7. Convert each validator
output into a standard result. 8. Continue after a single rule fails,
where safe. 9. Store run summary and individual results. 10. Prevent
accidental duplicate concurrent runs for the same registration. 11.
Handle token expiry during a run. 12. Add an overall run status
calculation.

Acceptance criteria: - One click runs all enabled rules for the selected
report. - A failed rule does not hide other rule results. - ERROR, FAIL,
WARNING, and PASS remain distinct. - Every rule has a persisted
result. - The run has a start time, end time, and duration.

Suggested commit:
`stage-12: orchestrate validation runs and persist results`

## Stage 13 --- Home dashboard and detailed results table

**Goal:** Present the complete health check in the agreed UI.

Tasks: 1. Build authentication banner. 2. Build summary KPI cards. 3.
Build report overview. 4. Build validation result table with the
required columns. 5. Add status filters. 6. Add search and sorting. 7.
Add result detail dialog. 8. Show refresh start, end, status, and
duration. 9. Build validation history table. 10. Add loading, empty,
success, and error states. 11. Connect Run Validation to the
orchestrator. 12. Refresh the dashboard after a run completes.

Acceptance criteria: - Dashboard reflects persisted data. - Result table
shows workspace, report, validation type, target, actual value, and
status. - Refresh details are clearly visible. - A user can inspect why
a rule failed. - Empty states are informative.

Suggested commit:
`stage-13: build health dashboard and detailed validation results`

## Stage 14 --- History, export, and diagnostics

**Goal:** Make results useful for audit and troubleshooting.

Tasks: 1. Add run history filters. 2. Open any previous run. 3. Compare
two runs. 4. Export results to CSV. 5. Export results to XLSX. 6. Add a
diagnostic log export with secrets removed. 7. Add configurable history
retention. 8. Add local database backup. 9. Add restore confirmation and
validation.

Acceptance criteria: - Previous runs remain available after a new run. -
Exported files match the selected run and filters. - Diagnostic export
contains no credentials or tokens. - Backup and restore are tested.

Suggested commit:
`stage-14: add validation history export and local backup`

## Stage 15 --- Hardening and packaging

**Goal:** Prepare a dependable Windows release.

Tasks: 1. Run unit and integration tests. 2. Test with a dedicated test
workspace and dataset. 3. Test permission-denied scenarios. 4. Test
expired/revoked authentication. 5. Test API throttling and network
interruptions. 6. Test empty datasets and large result sets. 7. Test
long-running DAX queries. 8. Test app restart and token-cache recovery.
9. Review log redaction. 10. Package using PyInstaller. 11. Create
installer using Inno Setup. 12. Test install, upgrade, uninstall, and
local data retention behavior. 13. Add version information and release
notes.

Acceptance criteria: - Clean installation works on a supported Windows
machine. - App launches without a Python installation. - Authentication
works after packaging. - Local database and protected token cache behave
as documented. - No secrets are bundled in the executable. - Critical
tests pass.

Suggested commit: `stage-15: harden and package Windows desktop release`

## Stage 16 --- Multi-report and scheduled monitoring (future)

Only begin after the single-report workflow is stable.

Possible features: - Multiple workspaces and datasets per run. -
Multiple reports sharing a semantic model. - Batch validation with
concurrency limits. - Per-workspace dashboards. - Scheduled checks using
Windows Task Scheduler. - Run after refresh detection / polling. - Email
or Teams alerts. - Optional local PBIX / Desktop model connector. -
Optional cloud synchronization or shared team configuration.

Do not build these into the first MVP.

------------------------------------------------------------------------

# 14. Recommended First MVP Scope

The first usable MVP should include:

1.  PySide6 desktop shell.
2.  Microsoft organizational sign-in.
3.  Secure token cache.
4.  Verify access to one workspace and dataset.
5.  Manually register one report and dataset.
6.  Add rules through the tabular rule editor.
7.  Refresh status, start, end, and duration.
8.  Fetch one selected DAX measure.
9.  Null check.
10. Duplicate check.
11. Latest date check.
12. Fixed baseline and historical mean/median comparison.
13. PASS / FAIL / WARNING / ERROR.
14. Home dashboard with detailed result table.
15. Local SQLite validation history.

CSV/XLSX import, XMLA fallback, multi-report execution, advanced
statistical methods, scheduling, and installer polish can follow as
separate increments.

------------------------------------------------------------------------

# 15. Testing Strategy

## Unit tests

Test without Power BI: - Deviation calculations. - Zero baseline
behavior. - Mean / median / mode calculations. - Historical window
selection. - Null and duplicate logic using sample data. - Status
mapping. - Rule configuration validation. - Database repositories.

## Integration tests

Use a dedicated non-production Power BI workspace: - Sign-in. -
Workspace access. - Dataset access. - Refresh history. - DAX query. -
Permission-denied behavior. - API throttling and timeout behavior.

## UI tests

-   Navigation.
-   Manual registration.
-   Rule row creation and editing.
-   Advanced settings dialog.
-   Import preview.
-   Run progress.
-   Result filtering.
-   History navigation.

Never run test queries or refresh operations against a production
dataset without explicit approval.

------------------------------------------------------------------------

# 16. Risks and Design Decisions

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  Tenant blocks API access            Detect early in Stage 4 and show
                                      required admin settings

  User has workspace access but not   Check each operation's actual
  required dataset permission         permission requirements

  Execute Queries API is unavailable  Keep DAX connector abstract; assess
                                      XMLA eligibility

  Refresh history has limited         Store each observed refresh locally
  retention or incomplete detail      

  Historical values are not available Require sufficient samples; return
  for all past days                   WARNING

  DAX measure depends on report       Allow explicit query/filter
  filter context                      configuration; document that report
                                      visual context is not automatically
                                      reproduced

  Large tables make checks slow       Push aggregation to the semantic
                                      model; use query limits and
                                      timeouts

  False anomaly alerts                Per-rule thresholds, minimum
                                      samples, historical context, and
                                      warning state

  Token cache exposure                Windows-protected token cache;
                                      never store raw tokens in SQLite

  API throttling                      Respect retry headers, backoff, and
                                      request limits

  UI freezes during validation        Run API and validation work outside
                                      the UI thread and marshal progress
                                      back safely
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 17. Important Functional Rules

1.  A refresh success must never automatically mark all data checks as
    PASS.
2.  A DAX query error must be ERROR, not FAIL.
3.  Missing data must not automatically be converted to zero.
4.  Every rule must have its own advanced configuration.
5.  Every validation run must be immutable history.
6.  Every result must explain why it passed, failed, warned, or errored.
7.  The UI must distinguish a report, a workspace, and a semantic
    model/dataset.
8.  One semantic model can serve multiple reports; do not assume a
    one-to-one relationship.
9.  Store timestamps in UTC internally and display them in the user's
    configured local timezone.
10. Never claim workspace ownership based only on authentication.
11. Do not assume all datasets support the same query APIs.
12. Start with one report, but avoid a database or code design that
    prevents future expansion.

------------------------------------------------------------------------

# 18. Development Workflow for AI Coding Agents

Use the following workflow for every stage:

1.  Read this BRD and the current project structure.
2.  Work only on the explicitly assigned stage and its acceptance
    criteria.
3.  Inspect existing code before editing.
4.  Do not rewrite working modules unnecessarily.
5.  Keep the implementation small and modular.
6.  Add or update tests for the changed functionality.
7.  Run the relevant tests and launch the application.
8.  Report files created/changed, tests run, results, and known
    limitations.
9.  Do not silently skip failing tests.
10. Do not begin the next stage until the current stage is reviewed and
    committed.

### Git discipline

Use one commit per completed stage or small sub-stage. Suggested
pattern:

``` bash
git status
git add .
git commit -m "stage-N: short description"
```

Do not commit: - `.env` files containing secrets. - Access tokens or
token caches. - Local production databases. - Personal logs. - Build
artifacts unless intentionally part of a release.

------------------------------------------------------------------------

# 19. Official Technical References

Use current Microsoft documentation during implementation because API
permissions, licensing, tenant settings, and feature support can change.

-   Microsoft Authentication Library (MSAL) for Python:
    https://learn.microsoft.com/entra/msal/python/
-   Microsoft identity platform authentication flows:
    https://learn.microsoft.com/entra/identity-platform/
-   Power BI REST API documentation:
    https://learn.microsoft.com/rest/api/power-bi/
-   Power BI Execute Queries REST API:
    https://learn.microsoft.com/rest/api/power-bi/datasets/execute-queries
-   Power BI refresh history:
    https://learn.microsoft.com/rest/api/power-bi/datasets/get-refresh-history
-   Power BI XMLA endpoints:
    https://learn.microsoft.com/power-bi/enterprise/service-premium-connect-tools
-   PySide6 documentation: https://doc.qt.io/qtforpython-6/
-   SQLAlchemy documentation: https://docs.sqlalchemy.org/
-   Alembic documentation: https://alembic.sqlalchemy.org/
-   PyInstaller documentation: https://pyinstaller.org/

------------------------------------------------------------------------

# 20. Immediate Next Step

Start with **Stage 0 only**.

The first deliverable should be a small, runnable PySide6 Windows
desktop shell with: - Main window. - Navy sidebar. - Home, Settings,
History, About navigation. - Placeholder content. - Application title
and version. - Basic logging. - Clean project structure.

Do not implement authentication, Power BI APIs, SQLite, or validation
logic in Stage 0. Those belong to later stages.

**Definition of success:** The app launches reliably, navigation works,
and the project is ready for Stage 1.
