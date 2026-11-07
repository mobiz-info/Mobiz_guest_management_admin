# Mobiz Guest Management — Building / Floor / Unit Scope

Django 4.2 application using direct HTML forms (no `core/forms.py`, `operations/forms.py`, or `template_fields.py`).

## Included modules

- Common Super Admin login and global masters: Country, State, District, Area, Designation, Establishment Type, Purpose of Visit, Building Type.
- Company / Client with a Company Admin login.
- Company → Work Site → Building → Floor → Unit → Tenant hierarchy.
- Building Type Master separate from Establishment Type Master.
- Building records do not create or require separate Building Staff login accounts. Company Admin manages all buildings within the assigned company.
- Company Staff (Company Admin) are scoped to their company and can manage all buildings, floors and units within that company.
- Premium list/form templates with search, pagination, status labels, edit/delete actions and confirmation.
- Dependent Work Site, Building and Floor dropdowns in the Unit form.
- Tenant management includes contact details, address, Owner/Rental type, lease dates, generated login credentials, individual multi-unit allocation, status, notes, search and pagination. Tenant access is scoped to the logged-in user’s company or assigned building.

Guest Visit registration, tenant approval/denial and Gate Pass code generation remain in the existing codebase, but are deferred from this delivery and are not re-audited here. Visitor phone, photo, ID proof, vehicle and check-in/check-out fields are intentionally not assumed. Auto Care Excel Import remains outside this Guest Management scope.

## Local setup (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python seed_data.py
python manage.py createsuperuser
python manage.py check
python manage.py test operations
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The project uses SQLite by default. This archive retains the existing `db.sqlite3` file and adds migration `operations.0005_tenant`. Back up your current database before copying files or running migrations. `python manage.py migrate` creates the Tenant table without removing existing project tables.

## Building type vs establishment type

Building Type describes the property (Apartment, Villa, Office, Other, Residential, Commercial, Office Building). Establishment Type describes an individual unit (Shop, Office, Residential, Godown, Restaurant, Clinic). They are separate master tables.

## Security notes

All data scope is enforced in server-side views, not only hidden in the navigation. Before production deployment, configure a strong secret key, `DEBUG=False`, explicit `ALLOWED_HOSTS`, HTTPS and secure CSRF settings.


## Tenant login and family members

The tenant module supports:

- Tenant Type: Rental Tenant or Owner.
- A separate Django login username and password for each newly created tenant.
- Secure password storage through Django's `create_user` / `set_password` behavior.
- Multiple family members per tenant, each with a required name and mobile number and an optional email address. Tenant dashboards also manage household/domestic staff contact records (without separate logins).
- Tenant accounts can access only their own family-member records.
- Super Admin and Company Staff access is scoped to their authorized tenants.

### Apply the new database migration

Back up `db.sqlite3` before migrating. From the folder containing `manage.py`, activate the project's virtual environment and run:

```bash
python manage.py migrate
python manage.py check
python manage.py test operations
```

Migration `operations/migrations/0006_tenant_login_and_family_members.py` added tenant login and family-member support. Migration `0007_tenant_multi_unit_and_guest_visits.py` adds the latest multi-unit allocation and Guest Visit features.


## Tenant allocation and Guest Visit workflow (latest)

- A tenant can be allocated multiple individual units through `TenantUnitAllocation`; units are selected individually in the tenant form, grouped by building.
- Multiple tenants can be assigned different units in the same building. Selecting a building no longer allocates every active unit in that building.
- Units allocated to another active tenant are hidden from the available-unit selector, and the server checks conflicts again during save. Each unit can have only one active tenant allocation at a time. A database unique constraint is the final guard against duplicate allocation.
- The legacy `Tenant.unit` field remains as the primary/first unit for compatibility with existing templates and data. The allocation table is the source of truth for multi-unit assignments.
- Tenant address is stored separately from unit/building address.
- Tenant usernames are entered manually by the Super Admin and checked for uniqueness.
- The Super Admin enters a unique tenant username and initial password. The mobile number may be used as the initial password; it is stored with Django password hashing and newly created tenants must change it at first login.
- Rental tenants require a lease start date. If no lease end date is entered, the app defaults it to one year after the start date; staff may enter a different end date. The tenant list flags expired leases and leases expiring within 30 days. Owner lease dates are cleared.
- Deactivating a tenant blocks tenant-only login, releases active unit allocations by recording `released_at`, and preserves tenant, family-member, guest-visit and allocation history. Permanent deletion is not the default.
- Guest Visit code is retained in the repository but is outside the current Tenant-focused update. Review Guest Visit, approval/denial and Gate Pass separately in the next session.

### Apply the latest migration

Back up `db.sqlite3` first, then run from the project directory:

```powershell
python manage.py migrate
python manage.py check
python manage.py test operations
```

Migration `operations.0007_tenant_multi_unit_and_guest_visits` adds the address field, allocation table and Guest Visit table, and copies each existing tenant's legacy `unit` into the allocation table. If the same legacy unit is already assigned to multiple tenant records, that migration stops with a clear error rather than deleting or silently reassigning tenant records. Migration `operations.0008_tenant_password_change_and_allocation_history` adds allocation release history and first-login password change. Migration `operations.0009_tenant_staff_members` adds household/domestic staff contact records. Resolve duplicate legacy assignments before running the migrations.


## Temporary tenant assumptions

See `TENANT_MODULE_WORKING_ASSUMPTIONS.md` for the current decisions pending confirmation. Apply the latest migration with `python manage.py migrate` after backing up `db.sqlite3`.


## Update 2026-10-16 — individual unit allocation

The Tenant create/edit form now lists individual available units grouped by building and floor. Select only the units the tenant should occupy. This allows different tenants to occupy separate units in the same building while preserving multiple-unit assignments, allocation history, and building-staff scope rules. No new database migration is required for this UI/view change.

**Verification note:** Python syntax compilation passed in the delivery environment. Django `check`, migration checks, automated tests and browser testing could not be run because Django dependencies were unavailable and package installation was blocked. Run the local verification commands above before treating this update as production-ready.


## Guest Visit workflow (updated)

The Guest Visit module supports advance visits created by a tenant and walk-in requests entered by authorised building/company staff. Each request is tied to a tenant and one of that tenant's currently allocated units, selected through Building then Unit. Requests remain pending until the assigned tenant approves or rejects them. Approval generates and stores a Gate Pass code. Vehicle details are optional; accompanying persons can be added with a name and mobile number. Authorised building/company staff can record check-in and check-out timestamps.

Apply the new migration before testing the module:

```powershell
python manage.py migrate
python manage.py check
python manage.py test operations
```

Walk-in requests are entered by existing authorised Company Staff accounts; a separate Security role/account model has not been added because that was not specified as a confirmed requirement.

### Tenant module updates

- Tenant household staff designation is selected from active admin-managed designations (global designations enabled for the tenant's company and company-specific designations).
- Family members are grouped by their assigned Building / Floor / Unit on the list page.
- These updates do not add database fields, so they do not require a new migration.

## Unit login and two-step guest approval update

This update adds a separate login account for each newly created Unit:
- Username: Unit Email ID
- Initial password: Unit Mobile Number

Guest workflow:
- Unit-created Advance Guest Visit requests are sent to the allocated Tenant. The Tenant's approval generates the Gate Pass.
- Tenant-created Walk-in requests are sent to the related Unit. The Unit must accept first; the Tenant must then approve. Only the Tenant approval generates the Gate Pass.
- Approved Gate Passes are listed on the Unit Dashboard.

After replacing the project files, install the packages from `requirements.txt` and run:

```bash
python manage.py migrate
python manage.py runserver
```

The new migration is `operations/0019_unit_login_and_two_step_guest_approval.py`. Existing database records are retained; the migration adds columns without deleting existing records. Newly created Unit accounts use the mobile number as the initial password, so share credentials securely and ask the Unit user to change the password after first login as a production hardening step.

---

## Mobile Application Backend REST APIs

The project now provides full backend REST API support for two mobile applications:

1. **Householder Mobile Application** (for Unit accounts)
2. **Tenant Mobile Application** (for Tenant accounts)
3. **Security-Related Services** (reusing Tenant authentication and permissions)

### API Documentation & Swagger UI
- **Interactive Swagger UI**: `http://127.0.0.1:8000/api/docs/`
- **OpenAPI 3.0 JSON Schema**: `http://127.0.0.1:8000/api/schema/`
- **Full Markdown API Reference**: See [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md) for request/response payloads for every endpoint.

### New Migrations
- `operations/migrations/0019_unit_login_and_two_step_guest_approval.py` (Unit login columns and two-step approval statuses)
- `operations/migrations/0020_notification.py` (In-app Notification model)

### Running Automated Tests
```powershell
python manage.py test api
```
All 19 test cases verify:
- Householder and Tenant logins and JWT token creation
- Role-based permissions and Unit/Tenant data isolation
- Advance Guest Visit creation and approval workflows
- Walk-in Guest Visit two-step acceptance and approval workflows
- Gate Pass and secure QR Code generation
- Security verification, check-in, ID tag allocation, and checkout tag validation
- In-app notification delivery, unread count, and marking read

