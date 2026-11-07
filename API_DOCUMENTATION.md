# Mobiz Guest Management — Mobile Application Backend APIs Documentation

This document describes all RESTful backend JSON APIs for the **Householder Mobile Application**, the **Tenant Mobile Application**, and the **Security-Related Services** (reusing the Tenant account) in the Mobiz Guest Management system.

---

## 1. Overview & General Architecture

### Base URL
All API endpoints are mounted under the `/api/` prefix.

### Interactive Swagger UI & OpenAPI Specification
- **Interactive Swagger UI**: `http://127.0.0.1:8000/api/docs/`
- **OpenAPI 3.0.3 Schema (JSON)**: `http://127.0.0.1:8000/api/schema/`

### Authentication & Headers
All private endpoints require JWT Bearer authentication or session authentication.
For mobile apps, pass the JWT access token in the `Authorization` header:
```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Standard JSON Response Envelope
All API endpoints return standard, structured JSON responses.

#### Success Envelope (`200 OK`, `201 Created`):
```json
{
  "success": true,
  "message": "Operation successful description",
  "data": { ... }
}
```

#### Error Envelope (`400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`):
```json
{
  "success": false,
  "message": "Description of error",
  "errors": {
    "field_name": ["Specific validation error message."]
  }
}
```

---

## 2. Common & Authentication APIs

### 2.1 Unified Login
- **Endpoint URL**: `/api/auth/login/`
- **HTTP Method**: `POST`
- **Purpose**: Authenticates any authorized user (Super Admin, Company Admin, Householder / Unit, Tenant) and returns JWT access and refresh tokens along with user and profile metadata.
- **Authentication**: None (Public)
- **Required Request Fields**:
  - `username` (string): Username or email address
  - `password` (string): Account password
- **Sample Request**:
  ```json
  {
    "username": "unit101",
    "password": "Password123!"
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Login successful.",
    "data": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "user": {
        "id": 5,
        "username": "unit101",
        "email": "unit101@alpha.com",
        "first_name": "",
        "last_name": "",
        "role": "householder",
        "role_name": "Householder",
        "company_id": 1,
        "building_id": 1,
        "unit": {
          "id": 1,
          "name": "101",
          "building_name": "Alpha Tower",
          "company_name": "Alpha Properties"
        }
      }
    }
  }
  ```
- **Possible Error Responses**:
  - `400 Bad Request`: `{"success": false, "message": "Invalid credentials format.", "errors": {"username": ["This field is required."]}}`
  - `401 Unauthorized`: `{"success": false, "message": "Invalid username or password.", "errors": {"detail": ["Invalid username or password."]}}`
  - `403 Forbidden`: `{"success": false, "message": "Your account is not authorized or has no active profile.", "errors": {"detail": [...]}}`

### 2.2 Token Refresh
- **Endpoint URL**: `/api/auth/token/refresh/`
- **HTTP Method**: `POST`
- **Purpose**: Refreshes an expired JWT access token using a valid refresh token.
- **Authentication**: None (Public)
- **Required Request Fields**:
  - `refresh` (string): Valid JWT refresh token
- **Sample Request**:
  ```json
  {
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
  ```

### 2.3 Current User Info
- **Endpoint URL**: `/api/auth/me/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieves basic user details and assigned role.
- **Authentication**: `Bearer <token>`

---

## 3. Householder Mobile Application APIs

These endpoints are strictly protected by `IsHouseholder` and scoped to the authenticated Householder's Unit.

### 3.1 Householder Login
- **Endpoint URL**: `/api/householder/auth/login/`
- **HTTP Method**: `POST`
- **Purpose**: Dedicated login for Householder (Unit) accounts. Rejects logins from Tenant or unauthorized roles.
- **Authentication**: None (Public)
- **Required Request Fields**: `username`, `password`
- **Sample Request**:
  ```json
  {
    "username": "unit101",
    "password": "Password123!"
  }
  ```

### 3.2 Householder Profile
- **Endpoint URL**: `/api/householder/auth/me/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve profile information for the authenticated Householder.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Householder profile retrieved.",
    "data": {
      "user_id": 5,
      "username": "unit101",
      "unit_id": 1,
      "unit_name": "101",
      "unit_type": "flat",
      "unit_type_display": "Flat",
      "email": "unit101@alpha.com",
      "mobile_number": "9876543210",
      "building_name": "Alpha Tower",
      "company_name": "Alpha Properties"
    }
  }
  ```

### 3.3 Unit Details
- **Endpoint URL**: `/api/householder/unit/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve full details of the associated Unit, including Building, Floor, Company, and currently allocated active Tenant.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Unit details retrieved.",
    "data": {
      "id": 1,
      "name": "101",
      "email": "unit101@alpha.com",
      "mobile_number": "9876543210",
      "unit_type": "flat",
      "unit_type_display": "Flat",
      "building_id": 1,
      "building_name": "Alpha Tower",
      "floor_id": 1,
      "floor_name": "Floor 1",
      "floor_number": 1,
      "company_id": 1,
      "company_name": "Alpha Properties",
      "work_site_id": 1,
      "work_site_name": "Alpha Site",
      "establishment_type_id": "7f8b9a10-...",
      "establishment_type_name": "Residential",
      "status": true,
      "current_tenant": {
        "id": 1,
        "full_name": "John Doe",
        "mobile_number": "9876500001",
        "email": "john@example.com",
        "tenant_type": "rental",
        "tenant_type_display": "Rental Tenant"
      }
    }
  }
  ```

### 3.4 Householder Dashboard Statistics
- **Endpoint URL**: `/api/householder/dashboard/`
- **HTTP Method**: `GET`
- **Purpose**: Returns real-time KPI metrics and recent Gate Passes for the Unit.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Dashboard statistics retrieved.",
    "data": {
      "unit_name": "101",
      "building_name": "Alpha Tower",
      "company_name": "Alpha Properties",
      "total_guests": 14,
      "pending_walk_in_requests": 1,
      "pending_advance_requests": 2,
      "approved_gate_passes": 11,
      "active_visitors": 1,
      "recent_gate_passes": [ ... ]
    }
  }
  ```

### 3.5 Create Advance Guest Visit Request (Workflow B)
- **Endpoint URL**: `/api/householder/guest-visits/advance/`
- **HTTP Method**: `POST`
- **Purpose**: Creates an Advance Guest Visit request originated by the Unit. The request is sent to the active Tenant allocated to this Unit for approval. Gate Pass is not generated until Tenant approves.
- **Authentication**: `Bearer <token>`
- **Required Request Fields**:
  - `guest_name` (string): Full name of the guest
  - `guest_mobile_number` (string): Mobile number of the guest
  - `purpose_of_visit` (UUID string): UUID of the active Purpose of Visit
  - `visit_date` (string, `YYYY-MM-DD`): Planned date of visit
- **Optional Request Fields**:
  - `visit_time` (string, `HH:MM:SS`): Planned visit time
  - `additional_visitors` (integer): Number of additional visitors
  - `accompanying_people` (array of objects): `[{"name": "...", "mobile_number": "..."}]`
  - `vehicle_details` (string): Vehicle registration number/model
  - `notes` (string): Additional notes
  - `guest_photo` (file): Uploaded guest photo
- **Sample Request**:
  ```json
  {
    "guest_name": "David Miller",
    "guest_mobile_number": "9876543299",
    "purpose_of_visit": "d3b07384-d113-42be-b1e9-44be2580a82b",
    "visit_date": "2026-11-08",
    "visit_time": "10:00:00",
    "additional_visitors": 1,
    "accompanying_people": [
      {"name": "Robert Miller", "mobile_number": "9876543298"}
    ],
    "notes": "Plumbing service and repair"
  }
  ```
- **Sample Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "Advance guest visit request submitted successfully. Awaiting Tenant approval.",
    "data": {
      "id": 10,
      "guest_name": "David Miller",
      "status": "pending",
      "unit_approval_status": "approved",
      "tenant_approval_status": "pending",
      "gate_pass_code": null,
      "visit_date": "2026-11-08"
    }
  }
  ```

### 3.6 List Advance Guest Visit Requests
- **Endpoint URL**: `/api/householder/guest-visits/advance/`
- **HTTP Method**: `GET`
- **Purpose**: List all advance visit requests submitted by this Unit, showing their approval status.
- **Authentication**: `Bearer <token>`

### 3.7 List Walk-in Guest Visit Requests
- **Endpoint URL**: `/api/householder/guest-visits/walk-in/`
- **HTTP Method**: `GET`
- **Purpose**: List all walk-in requests submitted for this Unit awaiting Unit action.
- **Authentication**: `Bearer <token>`

### 3.8 Accept Walk-in Request (Workflow C)
- **Endpoint URL**: `/api/householder/guest-visits/<id>/accept/`
- **HTTP Method**: `POST`
- **Purpose**: Accepts a pending Walk-in request. The request advances to Tenant approval.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Walk-in request accepted. It is now awaiting final Tenant approval.",
    "data": {
      "id": 12,
      "unit_approval_status": "approved",
      "status": "pending"
    }
  }
  ```

### 3.9 Reject Walk-in Request (Workflow C)
- **Endpoint URL**: `/api/householder/guest-visits/<id>/reject/`
- **HTTP Method**: `POST`
- **Purpose**: Rejects a Walk-in request. The request is closed with status `denied` and no Gate Pass will be generated.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Walk-in request rejected. No Gate Pass will be generated.",
    "data": {
      "id": 12,
      "unit_approval_status": "denied",
      "status": "denied"
    }
  }
  ```

### 3.10 List Generated Gate Passes
- **Endpoint URL**: `/api/householder/gate-passes/`
- **HTTP Method**: `GET`
- **Purpose**: View all approved Gate Passes generated for this Unit.
- **Authentication**: `Bearer <token>`

### 3.11 Retrieve Gate Pass Details & QR Code
- **Endpoint URL**: `/api/householder/gate-passes/<id>/` (or `/api/householder/gate-passes/by-code/<gate_pass_code>/`)
- **HTTP Method**: `GET`
- **Purpose**: Retrieve full Gate Pass details, unique code, masked ID, and base64 encoded PNG QR code.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Gate Pass details retrieved.",
    "data": {
      "id": 10,
      "gate_pass_code": "ENT-20261107-A4B92C",
      "status": "approved",
      "visit_type": "advance",
      "guest_name": "David Miller",
      "guest_mobile_number": "9876543299",
      "unit_name": "101",
      "building_name": "Alpha Tower",
      "tenant_name": "John Doe",
      "purpose_name": "Maintenance",
      "visit_date": "2026-11-08",
      "visit_time": "10:00:00",
      "masked_id_number": "******7890",
      "qr_code_image": "data:image/png;base64,iVBORw0KGgo...",
      "qr_data": "ENT-20261107-A4B92C",
      "is_checked_in": false,
      "is_checked_out": false
    }
  }
  ```

### 3.12 Guest Visit History
- **Endpoint URL**: `/api/householder/guest-visits/history/`
- **HTTP Method**: `GET`
- **Query Parameters**:
  - `search` (optional): Filter by guest name, mobile, gate pass code, purpose
  - `status` (optional): Filter by status (`pending`, `approved`, `denied`)
- **Authentication**: `Bearer <token>`

### 3.13 Active Visitors for Unit
- **Endpoint URL**: `/api/householder/visitors/active/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve visitors currently checked in to the Unit who have not checked out yet.
- **Authentication**: `Bearer <token>`

### 3.14 Single Guest Visit Details
- **Endpoint URL**: `/api/householder/guest-visits/<id>/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve complete details of a specific guest visit for this Unit.
- **Authentication**: `Bearer <token>`

### 3.15 Householder Notifications
- **Endpoint URLs**:
  - `GET /api/householder/notifications/`: List notifications
  - `GET /api/householder/notifications/unread-count/`: Get unread count
  - `POST /api/householder/notifications/<id>/read/`: Mark notification as read
  - `POST /api/householder/notifications/mark-all-read/`: Mark all as read
- **Authentication**: `Bearer <token>`

---

## 4. Tenant Mobile Application APIs

These endpoints are strictly protected by `IsTenant` and scoped to the authenticated Tenant and their allocated Units.

### 4.1 Tenant Login
- **Endpoint URL**: `/api/tenant/auth/login/`
- **HTTP Method**: `POST`
- **Purpose**: Dedicated login for Tenant accounts.
- **Authentication**: None (Public)
- **Required Request Fields**: `username`, `password`
- **Sample Request**:
  ```json
  {
    "username": "tenant_john",
    "password": "Password123!"
  }
  ```

### 4.2 Tenant Profile & Update
- **Endpoint URL**: `/api/tenant/auth/me/` (or `/api/tenant/profile/`)
- **HTTP Methods**: `GET`, `PUT`, `PATCH`
- **Purpose**: Retrieve profile details or update contact address, notes, and phone number.
- **Authentication**: `Bearer <token>`
- **Sample Update Request (`PATCH /api/tenant/profile/`)**:
  ```json
  {
    "address": "Apartment 101, Alpha Tower",
    "notes": "Prefers morning visits"
  }
  ```

### 4.3 Tenant Allocated Units
- **Endpoint URL**: `/api/tenant/units/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve all active Units currently allocated to the authenticated Tenant.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Associated unit details retrieved.",
    "data": [
      {
        "id": 1,
        "name": "101",
        "building_name": "Alpha Tower",
        "floor_name": "Floor 1",
        "company_name": "Alpha Properties"
      }
    ]
  }
  ```

### 4.4 Tenant Dashboard Statistics
- **Endpoint URL**: `/api/tenant/dashboard/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve Tenant dashboard KPIs: total guests, allocated units, pending approvals, active visitors, family count, staff count, and recent passes.
- **Authentication**: `Bearer <token>`

### 4.5 Create Advance Guest Visit Booking (Workflow A)
- **Endpoint URL**: `/api/tenant/guest-visits/advance/`
- **HTTP Method**: `POST`
- **Purpose**: Creates an Advance Guest Visit booking directly by the Tenant. Validates required visitor details, automatically approves the booking, and instantly generates a unique Gate Pass and QR Code.
- **Authentication**: `Bearer <token>`
- **Required Request Fields**:
  - `unit` (integer): ID of the allocated Unit
  - `guest_name` (string): Full name of the guest
  - `guest_mobile_number` (string): Mobile number of the guest
  - `purpose_of_visit` (UUID string): UUID of the active Purpose of Visit
  - `visit_date` (string, `YYYY-MM-DD`): Date of visit
- **Optional Request Fields**:
  - `visit_time` (string, `HH:MM:SS`)
  - `additional_visitors` (integer)
  - `accompanying_people` (array of objects)
  - `vehicle_details` (string)
  - `notes` (string)
  - `guest_photo` (file)
- **Sample Request**:
  ```json
  {
    "unit": 1,
    "guest_name": "Robert Brown",
    "guest_mobile_number": "9876500099",
    "purpose_of_visit": "d3b07384-d113-42be-b1e9-44be2580a82b",
    "visit_date": "2026-11-07",
    "visit_time": "14:30:00",
    "additional_visitors": 2,
    "accompanying_people": [
      {"name": "Sarah Brown", "mobile_number": "9876500098"},
      {"name": "Tommy Brown", "mobile_number": "9876500097"}
    ],
    "vehicle_details": "KL-11-AB-1234"
  }
  ```
- **Sample Response (201 Created)**:
  ```json
  {
    "success": true,
    "message": "Advance guest visit booked successfully. Gate Pass generated.",
    "data": {
      "id": 14,
      "gate_pass_code": "ENT-20261107-C3F81D",
      "status": "approved",
      "visit_type": "advance",
      "guest_name": "Robert Brown",
      "guest_mobile_number": "9876500099",
      "unit_name": "101",
      "qr_code_image": "data:image/png;base64,iVBORw...",
      "qr_data": "ENT-20261107-C3F81D"
    }
  }
  ```

### 4.6 Create Walk-in Guest Visit Request (Workflow C)
- **Endpoint URL**: `/api/tenant/guest-visits/walk-in/`
- **HTTP Method**: `POST`
- **Purpose**: Creates a Walk-in Guest Visit request. The request is submitted in `pending` status and sent to the associated Unit for acceptance.
- **Authentication**: `Bearer <token>`
- **Required Request Fields**: `unit`, `guest_name`, `guest_mobile_number`, `purpose_of_visit`, `visit_date`

### 4.7 View Submitted Guest Visit Requests
- **Endpoint URL**: `/api/tenant/guest-visits/`
- **HTTP Method**: `GET`
- **Purpose**: List all guest visit requests created by or for this Tenant.
- **Authentication**: `Bearer <token>`

### 4.8 View Requests Awaiting Tenant Approval
- **Endpoint URL**: `/api/tenant/guest-visits/pending-approvals/`
- **HTTP Method**: `GET`
- **Purpose**: Returns all requests awaiting Tenant approval:
  1. Advance visit requests submitted by the Unit.
  2. Walk-in requests accepted by the Unit.
- **Authentication**: `Bearer <token>`

### 4.9 Approve Guest Visit (Generates Gate Pass)
- **Endpoint URL**: `/api/tenant/guest-visits/<id>/approve/`
- **HTTP Method**: `POST`
- **Purpose**: Approves a pending visit request. For Walk-in requests, enforces that the Unit has accepted first. Generates the unique Gate Pass code and QR Code.
- **Authentication**: `Bearer <token>`
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Guest visit approved and Gate Pass generated successfully.",
    "data": {
      "id": 10,
      "gate_pass_code": "ENT-20261107-B7D9E1",
      "status": "approved",
      "qr_code_image": "data:image/png;base64,..."
    }
  }
  ```

### 4.10 Reject Guest Visit
- **Endpoint URL**: `/api/tenant/guest-visits/<id>/reject/`
- **HTTP Method**: `POST`
- **Purpose**: Rejects a guest visit request.
- **Authentication**: `Bearer <token>`

### 4.11 View Generated Gate Passes
- **Endpoint URL**: `/api/tenant/gate-passes/`
- **HTTP Method**: `GET`
- **Purpose**: View all approved Gate Passes for this Tenant.
- **Authentication**: `Bearer <token>`

### 4.12 Retrieve Gate Pass Details & QR Code
- **Endpoint URL**: `/api/tenant/gate-passes/<id>/` (or `/api/tenant/gate-passes/by-code/<gate_pass_code>/`)
- **HTTP Method**: `GET`
- **Authentication**: `Bearer <token>`

### 4.13 Guest Visit History
- **Endpoint URL**: `/api/tenant/guest-visits/history/`
- **HTTP Method**: `GET`
- **Authentication**: `Bearer <token>`

### 4.14 Active Visitors for Tenant
- **Endpoint URL**: `/api/tenant/visitors/active/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieve currently active visitors for this Tenant.
- **Authentication**: `Bearer <token>`

### 4.15 Tenant Notifications
- **Endpoint URLs**:
  - `GET /api/tenant/notifications/`: List notifications
  - `GET /api/tenant/notifications/unread-count/`: Get unread count
  - `POST /api/tenant/notifications/<id>/read/`: Mark notification as read
  - `POST /api/tenant/notifications/mark-all-read/`: Mark all as read
- **Authentication**: `Bearer <token>`

---

## 5. Security-Related Services (Reusing Tenant Account)

Per project architecture, no separate Security Staff model is created. Authorized Tenant accounts (or Super Admin) execute security operations for their property.

### 5.1 Verify Gate Pass & QR Code
- **Endpoint URL**: `/api/security/verify/`
- **HTTP Method**: `POST`
- **Purpose**: Scans / verifies Gate Pass number or QR Code reference. Validates entry eligibility, visitor details, and current status.
- **Authentication**: `Bearer <token>` (Tenant account)
- **Required Request Fields**:
  - `code` (string): Gate Pass number scanned from QR code or typed manually (e.g., `ENT-20261107-C3F81D`)
- **Sample Request**:
  ```json
  {
    "code": "ENT-20261107-C3F81D"
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Gate Pass verified successfully.",
    "data": {
      "id": 14,
      "gate_pass_code": "ENT-20261107-C3F81D",
      "status": "approved",
      "guest_name": "Robert Brown",
      "guest_mobile_number": "9876500099",
      "unit_name": "101",
      "building_name": "Alpha Tower",
      "tenant_name": "John Doe",
      "purpose_name": "Family Visit",
      "visit_date": "2026-11-07",
      "is_valid_for_entry": true,
      "verification_status": "Valid for Entry",
      "is_checked_in": false,
      "is_checked_out": false
    }
  }
  ```

### 5.2 Perform Guest Check-in
- **Endpoint URL**: `/api/security/check-in/`
- **HTTP Method**: `POST`
- **Purpose**: Records guest arrival. Validates approved status, records verification ID type and number, marks physical ID as received, assigns an available or dynamic security ID Tag (`DYN-XXXX`), records check-in timestamp, and sends arrival notifications.
- **Authentication**: `Bearer <token>` (Tenant account)
- **Required Request Fields**:
  - `gate_pass_code` (string) OR `visit_id` (integer)
  - `id_type` (string): Choice of `national_id`, `passport`, `driving_license`, `other`
  - `id_number` (string): Verification document number
- **Optional Request Fields**:
  - `notes` (string): Security check-in notes
- **Sample Request**:
  ```json
  {
    "gate_pass_code": "ENT-20261107-C3F81D",
    "id_type": "national_id",
    "id_number": "ID7894561230",
    "notes": "Verified at Gate 1"
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Guest checked in successfully. Assigned ID Tag: TAG-101.",
    "data": {
      "id": 14,
      "gate_pass_code": "ENT-20261107-C3F81D",
      "is_checked_in": true,
      "checked_in_at": "2026-11-07T14:32:00+05:30",
      "issued_tag_number": "TAG-101",
      "active_id_tags": ["TAG-101"]
    }
  }
  ```

### 5.3 Return Original ID Card
- **Endpoint URL**: `/api/security/return-id-card/`
- **HTTP Method**: `POST`
- **Purpose**: Records the return of the guest's physical ID card prior to checkout.
- **Authentication**: `Bearer <token>` (Tenant account)
- **Required Request Fields**: `gate_pass_code` (or `visit_id`)

### 5.4 Return Issued ID Tag
- **Endpoint URL**: `/api/security/return-id-tag/`
- **HTTP Method**: `POST`
- **Purpose**: Records the return of an issued security ID / NFC tag. Releases the tag back to `available` inventory.
- **Authentication**: `Bearer <token>` (Tenant account)
- **Required Request Fields**: `tag_number` (or `issue_id`)
- **Sample Request**:
  ```json
  {
    "tag_number": "TAG-101"
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "ID tag TAG-101 returned successfully.",
    "data": {
      "tag_number": "TAG-101",
      "issue_id": 5,
      "returned_at": "2026-11-07T17:15:00+05:30"
    }
  }
  ```

### 5.5 Perform Guest Check-out
- **Endpoint URL**: `/api/security/check-out/`
- **HTTP Method**: `POST`
- **Purpose**: Records guest departure. Enforces prerequisite validations:
  - Guest must be checked in.
  - Cannot checkout more than once.
  - **All issued security ID tags must be returned.** (Returns 400 Bad Request with outstanding tag list if any remain unreturned).
  - Guest original ID must be returned.
- **Authentication**: `Bearer <token>` (Tenant account)
- **Required Request Fields**: `gate_pass_code` (or `visit_id`)
- **Optional Request Fields**:
  - `return_id` (boolean, default `true`): Automatically records original ID card return if not already returned.
  - `notes` (string): Checkout notes.
- **Sample Request**:
  ```json
  {
    "gate_pass_code": "ENT-20261107-C3F81D",
    "return_id": true
  }
  ```
- **Sample Response (200 OK)**:
  ```json
  {
    "success": true,
    "message": "Guest checked out successfully.",
    "data": {
      "id": 14,
      "is_checked_out": true,
      "checked_out_at": "2026-11-07T17:20:00+05:30"
    }
  }
  ```
- **Error Response if Tags Outstanding (400 Bad Request)**:
  ```json
  {
    "success": false,
    "message": "Return all issued ID tags before checkout: TAG-101.",
    "errors": {
      "outstanding_tags": ["TAG-101"]
    }
  }
  ```

### 5.6 Active Visitors Retrieval
- **Endpoint URL**: `/api/security/visitors/active/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieves all currently active visitors across the authorized building / property.
- **Authentication**: `Bearer <token>` (Tenant account)

### 5.7 Visitor History Retrieval
- **Endpoint URL**: `/api/security/visitors/history/`
- **HTTP Method**: `GET`
- **Purpose**: Retrieves visitor history across authorized properties with search support.
- **Authentication**: `Bearer <token>` (Tenant account)

---

## 6. Master Records APIs

- `GET /api/purposes-of-visit/`: Retrieve list of active Purposes of Visit (used to populate mobile dropdowns).
- `GET /api/countries/`: List countries
- `GET /api/states/`: List states
- `GET /api/districts/`: List districts
- `GET /api/areas/`: List areas
- `GET /api/establishment-types/`: List establishment types
- `GET /api/designations/`: List designations
