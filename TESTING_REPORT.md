# Mobiz Guest Management – Testing Team Issue Update

## Scope and source of truth
This update follows the user's latest 38-item status list. Items marked **Pass** were preserved. Items marked **Fail** were corrected. Items marked **Not Tested** were treated as incomplete and received code/UI updates. Item 27 remains separate because the Testing Team marked it **Not Testable**.

## Status summary
- **20 Pass:** preserved; no intentional changes to these working items.
- **4 Fail:** fixes applied in code.
- **13 Not Tested:** implementation updates applied; runtime/browser verification is still required.
- **1 Not Testable:** not changed; requires a test account/environment that can exercise Company Admin tenant creation.

## Item-by-item status
| No. | Testing Team item | Latest user status | Update in this archive |
|---:|---|---|---|
| 1 | Country number validation | Pass | Preserved |
| 2 | Country search visibility | Pass | Preserved |
| 3 | Duplicate country prevention | Pass | Preserved |
| 4 | State number validation | Pass | Preserved |
| 5 | State mandatory asterisk | Pass | Preserved |
| 6 | District number validation | Pass | Preserved |
| 7 | District mandatory asterisk | Pass | Preserved |
| 8 | Area number validation | Pass | Preserved |
| 9 | Area mandatory asterisk | Pass | Preserved |
| 10 | Designation Add page | Pass | Preserved |
| 11 | Designation number validation | Pass | Preserved |
| 12 | Building Type validation | Fail | Server-side model/form validation retained and verified by source inspection; digits are rejected |
| 13 | Establishment Type Add page | Pass | Preserved |
| 14 | Purpose Add page | Pass | Preserved |
| 15 | Purpose number validation | Pass | Preserved |
| 16 | ID Card building dropdown | Not Tested | Building options now load from the complete Building queryset; dropdown retains the selected building on edit |
| 17 | Card/Tag number validation | Not Tested | Predefined card/tag and optional NFC numbers accept digits only; dynamic IDs retain generated `DYN-...` format |
| 18 | Company mandatory fields | Pass | Preserved |
| 19 | Company Country–State dropdown | Fail | State API now filters by selected country |
| 20 | Company State–District dropdown | Fail | District API now filters by selected state |
| 21 | Company District–Area dropdown | Fail | Area API now filters by selected district |
| 22 | Company phone validation | Pass | Preserved |
| 23 | Duplicate company prevention | Pass | Preserved |
| 24 | Company name and phone validation | Pass | Preserved |
| 25 | Unit Edit | Pass | Preserved |
| 26 | Tenant lease start date | Pass | Preserved |
| 27 | Company Admin Tenant creation | Not Testable | Left unchanged; needs a valid Company Admin test scenario |
| 28 | Client Details alignment | Not Tested | Detail card width, spacing, grid alignment, and text readability improved without changing the page structure |
| 29 | Worksite alignment | Not Tested | Form width, field sizing, spacing, and responsive action alignment improved |
| 30 | Building list visibility | Not Tested | Status/actions columns receive more width; action controls can wrap instead of crowding |
| 31 | Company Admin Tenant deletion | Not Tested | Tenant list now displays Delete for authorized Company Admins as well as Super Admin; server-side scope checks remain in place |
| 32 | Unit User Advance Guest Visit alignment | Not Tested | Advance Guest Visit form width, grid spacing, and responsive alignment improved for Unit self-service |
| 33 | Weak password rejection | Not Tested | Minimum password length raised to 10; existing similarity, common-password, and numeric-password validators remain enabled |
| 34 | Guest Visit mobile validation | Not Tested | Shared validator rejects alphabetic, invalid-length, repeated-digit, and sequential mobile numbers |
| 35 | Family Members search | Not Tested | Visible Search button added beside the search input; existing query filtering retained |
| 36 | Family mobile validation | Not Tested | Mobile field constrained in the form and validated server-side for 7–15 digits, formatting, repeated digits, and sequential runs |
| 37 | Staff form alignment | Not Tested | Staff form width, grid gaps, input sizing, and mobile stacking improved |
| 38 | Hold Documents mandatory fields | Not Tested | Required labels visibly mark required fields; required controls and server-side checks retained |

## Files changed
- `api/views.py` – dependent State, District, and Area API querysets.
- `operations/views.py` – ID Tag building options and number validation; tenant deletion visibility context; family/staff/guest mobile validation.
- `operations/tests.py` – mobile-number validation test cases.
- `api/tests.py` – tests for country → state → district → area filtering.
- `guest_management_project/settings.py` – minimum password length set to 10; other password validators retained.
- `templates/master/id_tag/form.html` – numeric input constraints for predefined tags/NFC values.
- `templates/operations/company/detail.html` – detail layout alignment.
- `templates/operations/work_site/form.html` – worksite form alignment.
- `templates/operations/building/list.html` – building table status/actions visibility.
- `templates/operations/tenant/list.html` – authorized Company Admin delete action visibility.
- `templates/operations/tenant/family_list.html` – visible Search button.
- `templates/operations/tenant/family_form.html` – family mobile input constraints.
- `templates/operations/tenant/staff_form.html` – staff form alignment and mobile input constraints.
- `templates/operations/guest_visit/form.html` – Unit Advance Guest Visit alignment and mobile input constraints.
- `templates/operations/hold_document/form.html` – required-field markers.

## Verification performed in this environment
- Python source compilation (`python -m compileall`) passed.
- Django automated tests and browser/UI tests were not run because Django and the project dependencies are not installed in this execution environment, and package installation is unavailable here.
- Therefore the 13 formerly Not Tested items are **code-updated but not runtime-certified**. Run `python manage.py check` and `python manage.py test`, then manually verify the affected pages with Super Admin, Company Admin, Unit User, and Tenant accounts before production use.

## Local verification commands
```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py test
```
