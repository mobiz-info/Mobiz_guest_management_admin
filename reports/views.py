from datetime import datetime, date
from io import BytesIO
import re

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from operations.models import (
    Building,
    BuildingStaff,
    Company,
    CompanyStaff,
    Floor,
    GuestVisit,
    HoldDocument,
    IDTag,
    IDTagIssue,
    Tenant,
    TenantUnitAllocation,
    Unit,
    WorkSite,
)


# ============================================================
# DATE / EXPORT HELPERS
# ============================================================

def _format_date(value):
    """Format date objects as DD-MM-YYYY for report tables."""
    if not value:
        return '—'

    if isinstance(value, datetime):
        return _format_timestamp(value)

    if isinstance(value, date):
        return value.strftime('%d-%m-%Y')

    return str(value)


def _format_timestamp(value):
    """Format timestamps consistently as DD-MM-YYYY hh:mm AM/PM."""
    if not value:
        return '—'

    try:
        if timezone.is_naive(value):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return timezone.localtime(value).strftime('%d-%m-%Y %I:%M %p')

    except (TypeError, ValueError, OverflowError):
        return str(value)


def _export_cell(value):
    """Convert report values into export-safe text."""
    if value is None or value == '':
        return '—'

    if isinstance(value, datetime):
        return _format_timestamp(value)

    if isinstance(value, date):
        return value.strftime('%d-%m-%Y')

    if hasattr(value, 'get_full_name') and hasattr(value, 'username'):
        return value.get_full_name() or value.username

    return str(value)


# ============================================================
# PDF / EXCEL EXPORT
# ============================================================

def _report_export_response(
    request,
    report_type,
    title,
    headers,
    rows,
    file_format,
):
    """Export the currently filtered report."""
    safe_slug = (
        re.sub(r'[^a-zA-Z0-9_-]+', '-', report_type).strip('-')
        or 'report'
    )

    generated = timezone.localtime(
        timezone.now()
    ).strftime('%d-%m-%Y %I:%M %p')

    exported_rows = [
        [_export_cell(value) for value in row]
        for row in rows
    ]

    if file_format == 'excel':
        from openpyxl import Workbook
        from openpyxl.styles import (
            Font,
            PatternFill,
            Border,
            Side,
            Alignment,
        )
        from openpyxl.utils import get_column_letter

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Report'

        sheet.append([title])
        sheet.append([f'Generated: {generated}'])
        sheet.append([])
        sheet.append(list(headers))

        for row in exported_rows:
            sheet.append(row)

        last_col = max(1, len(headers))

        sheet.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=last_col,
        )

        sheet['A1'].font = Font(
            name='Calibri',
            size=16,
            bold=True,
            color='FFFFFF',
        )
        sheet['A1'].fill = PatternFill(
            'solid',
            fgColor='4338CA',
        )
        sheet['A1'].alignment = Alignment(vertical='center')
        sheet.row_dimensions[1].height = 30

        sheet['A2'].font = Font(
            italic=True,
            color='64748B',
            size=10,
        )

        header_row = 4

        for cell in sheet[header_row]:
            cell.font = Font(
                bold=True,
                color='FFFFFF',
                size=10,
            )
            cell.fill = PatternFill(
                'solid',
                fgColor='4F46E5',
            )
            cell.alignment = Alignment(
                vertical='center',
                wrap_text=True,
            )
            cell.border = Border(
                bottom=Side(
                    style='thin',
                    color='C7D2FE',
                )
            )

        sheet.row_dimensions[header_row].height = 28

        for row in sheet.iter_rows(
            min_row=header_row + 1,
            max_row=sheet.max_row,
        ):
            for cell in row:
                cell.alignment = Alignment(
                    vertical='top',
                    wrap_text=True,
                )
                cell.border = Border(
                    bottom=Side(
                        style='hair',
                        color='E2E8F0',
                    )
                )

        for col_idx in range(1, last_col + 1):
            values = [
                str(
                    sheet.cell(row=r, column=col_idx).value or ''
                )
                for r in range(header_row, sheet.max_row + 1)
            ]

            width = min(
                max(
                    max((len(value) for value in values), default=10) + 2,
                    12,
                ),
                38,
            )

            sheet.column_dimensions[
                get_column_letter(col_idx)
            ].width = width

        sheet.freeze_panes = 'A5'

        sheet.auto_filter.ref = (
            f'A{header_row}:'
            f'{get_column_letter(last_col)}{sheet.max_row}'
        )

        sheet.sheet_view.showGridLines = False

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )

        response['Content-Disposition'] = (
            f'attachment; filename="{safe_slug}.xlsx"'
        )

        return response

    if file_format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle,
        )
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
        )
        from xml.sax.saxutils import escape

        output = BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=11 * mm,
            bottomMargin=12 * mm,
            title=title,
            author='Guest Management Application',
        )

        styles = getSampleStyleSheet()

        heading_style = ParagraphStyle(
            'ReportHeading',
            parent=styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=17,
            leading=21,
            textColor=colors.HexColor('#312e81'),
            alignment=TA_LEFT,
            spaceAfter=4,
        )

        meta_style = ParagraphStyle(
            'ReportMeta',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=8,
        )

        header_style = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            textColor=colors.white,
        )

        cell_style = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor('#334155'),
            wordWrap='CJK',
        )

        story = [
            Paragraph(escape(title), heading_style),
            Paragraph(
                (
                    f'Generated: {escape(generated)}'
                    f' | Records: {len(rows)}'
                ),
                meta_style,
            ),
            Spacer(1, 2 * mm),
        ]

        if headers:
            table_data = [[
                Paragraph(escape(str(header)), header_style)
                for header in headers
            ]]

            for row in exported_rows:
                table_data.append([
                    Paragraph(
                        escape(str(value)).replace('\n', '<br/>'),
                        cell_style,
                    )
                    for value in row
                ])
        else:
            table_data = [[
                Paragraph('No columns available', cell_style)
            ]]

        page_width = landscape(A4)[0] - 20 * mm
        column_count = max(len(headers), 1)
        col_widths = [page_width / column_count] * column_count

        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
            hAlign='LEFT',
        )

        table.setStyle(TableStyle([
            (
                'BACKGROUND',
                (0, 0),
                (-1, 0),
                colors.HexColor('#4f46e5'),
            ),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            (
                'GRID',
                (0, 0),
                (-1, -1),
                0.35,
                colors.HexColor('#e2e8f0'),
            ),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            (
                'ROWBACKGROUNDS',
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    colors.HexColor('#f8fafc'),
                ],
            ),
        ]))

        story.append(table)
        document.build(story)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type='application/pdf',
        )

        response['Content-Disposition'] = (
            f'attachment; filename="{safe_slug}.pdf"'
        )

        return response

    raise Http404


# ============================================================
# AVAILABLE REPORTS
# ============================================================

COMPANY_REPORTS = {
    'work-site-summary': (
        'Work Site Report',
        'work_site_summary',
    ),
    'building-summary': (
        'Building Report',
        'building_summary',
    ),
    'tenant-occupancy': (
        'Tenant / Occupancy Report',
        'tenant_occupancy',
    ),
    'guest-visit-summary': (
        'Guest Visit Summary Report',
        'guest_visit_summary',
    ),
    'id-card-gate-pass-summary': (
        'ID Card / Gate Pass Summary',
        'id_card_gate_pass_summary',
    ),
    'hold-document-summary': (
        'Hold Document Report',
        'hold_document_summary',
    ),
}

TENANT_REPORTS = {
    'guest-visit': ('Guest Visit Report', 'guest_visit'),
    'visit-duration': ('Visit Duration Report', 'visit_duration'),
    'id-card-issue': ('ID Card Issue Report', 'id_card_issue'),
    'id-card-return': ('ID Card Return Report', 'id_card_return'),
    'active-id-tags': ('Active ID Tags Report', 'active_id_tags'),
}

SUPERADMIN_REPORTS = {
    'company-summary': (
        'Company / Client Report',
        'company_summary',
    ),
    'work-site-summary': (
        'Work Site Report',
        'work_site_summary',
    ),
    'building-summary': (
        'Building Report',
        'building_summary',
    ),
    'tenant-occupancy': (
        'Tenant / Occupancy Report',
        'tenant_occupancy',
    ),
}


# ============================================================
# ACCESS CONTROL / REPORT SCOPE
# ============================================================

def _available_reports(request):
    if request.user.is_superuser:
        return SUPERADMIN_REPORTS

    if hasattr(request.user, 'company_staff'):
        try:
            if (
                request.user.company_staff.status
                and request.user.company_staff.company.status
            ):
                return COMPANY_REPORTS
        except Exception:
            pass

    return TENANT_REPORTS


def _parse_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _active_tenant_allocations(company=None):
    """Return current tenant/unit allocations; this is the source of truth for occupancy."""
    qs = TenantUnitAllocation.objects.filter(
        released_at__isnull=True,
    ).select_related(
        'tenant',
        'unit',
        'unit__building',
        'unit__company',
    )
    if company is not None:
        qs = qs.filter(unit__company=company)
    return qs


def _report_scope(request):
    if request.user.is_superuser:
        return 'all', None

    tenant = getattr(request.user, 'tenant_profile', None)

    if tenant is not None:
        if not tenant.status:
            return 'none', None
        return 'tenant', tenant

    try:
        building_staff = (
            BuildingStaff.objects
            .select_related('building__company')
            .get(user=request.user, status=True)
        )
    except BuildingStaff.DoesNotExist:
        building_staff = None

    if building_staff:
        return 'building', building_staff.building

    try:
        company_staff = (
            CompanyStaff.objects
            .select_related('company')
            .get(
                user=request.user,
                status=True,
                company__status=True,
            )
        )
    except CompanyStaff.DoesNotExist:
        company_staff = None

    if company_staff:
        return 'company', company_staff.company

    return 'none', None


def _guest_visit_queryset(request):
    scope, obj = _report_scope(request)

    qs = GuestVisit.objects.select_related(
        'tenant',
        'unit',
        'unit__building',
        'unit__company',
        'purpose_of_visit',
    )

    if scope == 'all':
        return qs

    if scope == 'tenant':
        return qs.filter(tenant=obj)

    if scope == 'building':
        return qs.filter(unit__building=obj)

    if scope == 'company':
        return qs.filter(unit__company=obj)

    return qs.none()


def _tag_issue_queryset(request):
    scope, obj = _report_scope(request)

    qs = IDTagIssue.objects.select_related(
        'visit',
        'visit__tenant',
        'visit__unit',
        'visit__unit__building',
        'visit__unit__company',
        'tag',
        'issued_by',
        'returned_by',
    )

    if scope == 'all':
        return qs

    if scope == 'tenant':
        return qs.filter(visit__tenant=obj)

    if scope == 'building':
        return qs.filter(visit__unit__building=obj)

    if scope == 'company':
        return qs.filter(visit__unit__company=obj)

    return qs.none()


def _tag_queryset(request):
    scope, obj = _report_scope(request)

    qs = (
        IDTag.objects
        .select_related('building', 'building__company')
        .prefetch_related(
            Prefetch(
                'issues',
                queryset=(
                    IDTagIssue.objects
                    .filter(status=IDTagIssue.STATUS_ISSUED)
                    .select_related(
                        'visit',
                        'visit__tenant',
                        'visit__unit',
                    )
                ),
                to_attr='active_issues',
            )
        )
    )

    if scope == 'all':
        return qs

    if scope == 'tenant':
        unit_ids = list(
            obj.unit_allocations
            .filter(released_at__isnull=True)
            .values_list('unit_id', flat=True)
        )

        if obj.unit_id:
            unit_ids.append(obj.unit_id)

        building_ids = (
            Unit.objects
            .filter(pk__in=set(unit_ids))
            .values_list('building_id', flat=True)
            .distinct()
        )

        return qs.filter(building_id__in=building_ids)

    if scope == 'building':
        return qs.filter(building=obj)

    if scope == 'company':
        return qs.filter(building__company=obj)

    return qs.none()


# ============================================================
# VISIT STATUS / DURATION
# ============================================================

def _current_visit_status(visit):
    if visit.checked_out_at:
        return 'Checked Out'

    if visit.checked_in_at:
        outstanding = visit.tag_issues.filter(
            status=IDTagIssue.STATUS_ISSUED
        ).exists()

        return (
            'Active - ID Tag Not Returned'
            if outstanding
            else 'Checked In'
        )

    return visit.get_status_display()


def _format_duration(start, end=None):
    if not start:
        return '—'

    try:
        finish = end or timezone.now()

        if timezone.is_naive(start):
            start = timezone.make_aware(
                start,
                timezone.get_current_timezone(),
            )

        if timezone.is_naive(finish):
            finish = timezone.make_aware(
                finish,
                timezone.get_current_timezone(),
            )

        seconds = max(
            0,
            int((finish - start).total_seconds()),
        )

    except (TypeError, ValueError, OverflowError):
        return '—'

    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60

    return (
        f'{hours}h {minutes}m'
        + ('' if end else ' (Active)')
    )


def _date_range(request, field, queryset):
    start_raw = request.GET.get('start_date', '').strip()
    end_raw = request.GET.get('end_date', '').strip()

    start = _parse_date(start_raw)
    end = _parse_date(end_raw)

    if start:
        queryset = queryset.filter(
            **{f'{field}__date__gte': start}
        )

    if end:
        queryset = queryset.filter(
            **{f'{field}__date__lte': end}
        )

    return (
        queryset,
        start.strftime('%Y-%m-%d') if start else '',
        end.strftime('%Y-%m-%d') if end else '',
    )


# ============================================================
# COMPANY REPORTS
# ============================================================

def _company_report(report_type, request):
    """Return filtered company-admin reports scoped to their company."""
    staff = getattr(request.user, 'company_staff', None)

    if not staff or not staff.status or not staff.company_id:
        raise Http404

    company = staff.company

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    start = _parse_date(request.GET.get('start_date', ''))
    end = _parse_date(request.GET.get('end_date', ''))

    if report_type == 'work-site-summary':
        headers = [
            'Work Site',
            'Location',
            'Buildings',
            'Units',
            'Tenant Count',
            'Status',
        ]

        qs = WorkSite.objects.filter(
            company=company
        ).order_by('name')

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(location__icontains=search)
            )

        if status in ('active', 'inactive'):
            qs = qs.filter(status=(status == 'active'))

        rows = [
            [
                site.name,
                site.location or '—',
                site.buildings.count(),
                site.units.count(),
                _active_tenant_allocations().filter(
                    unit__work_site=site,
                    tenant__status=True,
                ).count(),
                'Active' if site.status else 'Inactive',
            ]
            for site in qs
        ]

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'building-summary':
        headers = [
            'Building',
            'Work Site',
            'Building Type',
            'Floors',
            'Units',
            'Occupied',
            'Vacant',
            'Tenant Count',
        ]

        qs = (
            Building.objects
            .filter(company=company)
            .select_related('work_site', 'building_type_master')
            .order_by('name')
        )

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(work_site__name__icontains=search)
            )

        if status in ('active', 'inactive'):
            qs = qs.filter(status=(status == 'active'))

        rows = []

        for building in qs:
            occupied = _active_tenant_allocations().filter(
                unit__building=building,
                tenant__status=True,
            ).count()

            units = building.units.count()

            building_type = (
                building.building_type_master.name
                if building.building_type_master_id
                else (
                    building.get_building_type_display()
                    if hasattr(building, 'get_building_type_display')
                    else getattr(building, 'building_type', '—')
                )
            )

            rows.append([
                building.name,
                (
                    building.work_site.name
                    if building.work_site_id
                    else '—'
                ),
                building_type or '—',
                building.floors.count(),
                units,
                occupied,
                max(0, units - occupied),
                occupied,
            ])

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'tenant-occupancy':
        headers = [
            'Tenant',
            'Tenant Type',
            'Building',
            'Unit',
            'Lease Start',
            'Lease End',
            'Status',
            'Occupancy',
        ]

        qs = _active_tenant_allocations(company)

        if search:
            qs = qs.filter(
                Q(tenant__full_name__icontains=search)
                | Q(unit__name__icontains=search)
                | Q(unit__building__name__icontains=search)
            )

        if status == 'inactive':
            qs = qs.filter(tenant__status=False)

        if start:
            qs = qs.filter(tenant__lease_start_date__gte=start)

        if end:
            qs = qs.filter(tenant__lease_start_date__lte=end)

        rows = [
            [
                allocation.tenant.full_name,
                allocation.tenant.get_tenant_type_display(),
                allocation.unit.building.name,
                allocation.unit.name,
                _format_date(allocation.tenant.lease_start_date),
                _format_date(allocation.tenant.lease_end_date),
                'Active' if allocation.tenant.status else 'Inactive',
                'Occupied' if allocation.tenant.status else 'Vacant',
            ]
            for allocation in qs.order_by(
                'unit__building__name',
                'unit__name',
                'tenant__full_name',
            )
        ]

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    visits = _guest_visit_queryset(request)

    if report_type == 'guest-visit-summary':
        headers = [
            'Building',
            'Total Visits',
            'Today',
            'Upcoming',
            'Completed',
            'Pending',
            'Approved',
            'Denied',
        ]

        if start:
            visits = visits.filter(visit_date__gte=start)

        if end:
            visits = visits.filter(visit_date__lte=end)

        if search:
            visits = visits.filter(
                Q(unit__building__name__icontains=search)
                | Q(guest_name__icontains=search)
            )

        if status in (
            GuestVisit.STATUS_PENDING,
            GuestVisit.STATUS_APPROVED,
            GuestVisit.STATUS_DENIED,
        ):
            visits = visits.filter(status=status)

        buildings = Building.objects.filter(
            company=company
        ).order_by('name')

        today = timezone.localdate()
        rows = []

        for building in buildings:
            qs = visits.filter(unit__building=building)

            rows.append([
                building.name,
                qs.count(),
                qs.filter(visit_date=today).count(),
                qs.filter(visit_date__gt=today).count(),
                qs.filter(checked_out_at__isnull=False).count(),
                qs.filter(
                    status=GuestVisit.STATUS_PENDING
                ).count(),
                qs.filter(
                    status=GuestVisit.STATUS_APPROVED
                ).count(),
                qs.filter(
                    status=GuestVisit.STATUS_DENIED
                ).count(),
            ])

        return headers, rows, list(GuestVisit.STATUS_CHOICES)

    if report_type == 'id-card-gate-pass-summary':
        headers = [
            'Building',
            'Cards / Tags Issued',
            'Active Cards',
            'Returned Cards',
            'Unreturned Cards',
            'Gate Passes',
        ]

        issues = _tag_issue_queryset(request)

        if start:
            issues = issues.filter(issued_at__date__gte=start)

        if end:
            issues = issues.filter(issued_at__date__lte=end)

        if search:
            issues = issues.filter(
                Q(tag__tag_number__icontains=search)
                | Q(visit__guest_name__icontains=search)
                | Q(visit__unit__building__name__icontains=search)
            )

        if status in (
            IDTagIssue.STATUS_ISSUED,
            IDTagIssue.STATUS_RETURNED,
        ):
            issues = issues.filter(status=status)

        buildings = Building.objects.filter(
            company=company
        ).order_by('name')

        rows = []

        for building in buildings:
            qs = issues.filter(
                visit__unit__building=building
            )

            rows.append([
                building.name,
                qs.count(),
                qs.filter(
                    status=IDTagIssue.STATUS_ISSUED
                ).count(),
                qs.filter(
                    status=IDTagIssue.STATUS_RETURNED
                ).count(),
                qs.filter(
                    status=IDTagIssue.STATUS_ISSUED
                ).count(),
                qs.filter(
                    visit__gate_pass_code__isnull=False
                ).exclude(visit__gate_pass_code='').count(),
            ])

        return headers, rows, list(IDTagIssue.STATUS_CHOICES)

    if report_type == 'hold-document-summary':
        headers = [
            'Person',
            'Type',
            'Building',
            'Item / Document',
            'Quantity',
            'Reference Number',
            'Status',
            'Received At',
            'Collected At',
        ]

        qs = (
            HoldDocument.objects
            .select_related(
                'visit__unit__building',
                'visit__tenant',
                'received_by',
                'collected_by',
            )
            .filter(
                Q(visit__unit__company=company)
                | Q(
                    visit__isnull=True,
                    received_by__company_staff__company=company,
                )
            )
            .order_by('-received_at')
        )

        if search:
            qs = qs.filter(
                Q(item_name__icontains=search)
                | Q(reference_number__icontains=search)
                | Q(person_name__icontains=search)
                | Q(person_mobile__icontains=search)
                | Q(visit__guest_name__icontains=search)
                | Q(visit__tenant__full_name__icontains=search)
            )

        if status:
            valid = {
                value
                for value, _ in HoldDocument.STATUS_CHOICES
            }

            if status in valid:
                qs = qs.filter(status=status)

        if start:
            qs = qs.filter(received_at__date__gte=start)

        if end:
            qs = qs.filter(received_at__date__lte=end)

        rows = []

        for document in qs:
            person = (
                document.person_name
                or (
                    document.visit.guest_name
                    if document.visit_id
                    else '—'
                )
            )

            building_name = (
                document.visit.unit.building.name
                if (
                    document.visit_id
                    and document.visit.unit_id
                )
                else '—'
            )

            rows.append([
                person,
                document.get_person_type_display(),
                building_name,
                document.item_name,
                document.quantity or 1,
                document.reference_number or '—',
                document.get_status_display(),
                _format_timestamp(document.received_at),
                _format_timestamp(document.collected_at),
            ])

        return headers, rows, [
            (value, label)
            for value, label in HoldDocument.STATUS_CHOICES
        ]

    raise Http404


# ============================================================
# SUPER ADMIN REPORTS
# ============================================================

def _superadmin_report(report_type, request=None):
    """Return filtered management reports for super admin."""
    search = request.GET.get('search', '').strip() if request else ''
    status = request.GET.get('status', '').strip() if request else ''

    start = (
        _parse_date(request.GET.get('start_date', ''))
        if request else None
    )

    end = (
        _parse_date(request.GET.get('end_date', ''))
        if request else None
    )

    if report_type == 'company-summary':
        headers = [
            'Company / Client',
            'Email',
            'Phone',
            'Work Sites',
            'Buildings',
            'Units',
            'Tenants',
            'Status',
        ]

        qs = Company.objects.all().order_by('name')

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )

        if status in ('active', 'inactive'):
            qs = qs.filter(status=(status == 'active'))

        rows = [
            [
                company.name,
                company.email or '—',
                company.phone or '—',
                company.work_sites.count(),
                company.buildings.count(),
                company.units.count(),
                company.units.filter(
                    tenants__status=True
                ).distinct().count(),
                'Active' if company.status else 'Inactive',
            ]
            for company in qs
        ]

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'work-site-summary':
        headers = [
            'Work Site',
            'Company / Client',
            'Location',
            'Buildings',
            'Units',
            'Tenants',
            'Status',
        ]

        qs = (
            WorkSite.objects
            .select_related('company')
            .order_by('company__name', 'name')
        )

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(location__icontains=search)
                | Q(company__name__icontains=search)
            )

        if status in ('active', 'inactive'):
            qs = qs.filter(status=(status == 'active'))

        rows = [
            [
                site.name,
                site.company.name,
                site.location or '—',
                site.buildings.count(),
                site.units.count(),
                _active_tenant_allocations().filter(
                    unit__work_site=site,
                    tenant__status=True,
                ).count(),
                'Active' if site.status else 'Inactive',
            ]
            for site in qs
        ]

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'building-summary':
        headers = [
            'Building',
            'Company / Client',
            'Work Site',
            'Type',
            'Floors',
            'Units',
            'Tenants',
            'Status',
        ]

        qs = (
            Building.objects
            .select_related(
                'company',
                'work_site',
                'building_type_master',
            )
            .order_by('company__name', 'name')
        )

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(company__name__icontains=search)
                | Q(work_site__name__icontains=search)
            )

        if status in ('active', 'inactive'):
            qs = qs.filter(status=(status == 'active'))

        rows = []

        for building in qs:
            building_type = (
                building.building_type_master.name
                if building.building_type_master_id
                else (
                    building.get_building_type_display()
                    if hasattr(building, 'get_building_type_display')
                    else building.building_type
                )
            )

            rows.append([
                building.name,
                building.company.name,
                (
                    building.work_site.name
                    if building.work_site_id
                    else '—'
                ),
                building_type or '—',
                building.floors.count(),
                building.units.count(),
                _active_tenant_allocations().filter(
                    unit__building=building,
                    tenant__status=True,
                ).count(),
                'Active' if building.status else 'Inactive',
            ])

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'tenant-occupancy':
        headers = [
            'Tenant',
            'Type',
            'Company / Client',
            'Building',
            'Unit',
            'Lease Start',
            'Lease End',
            'Status',
        ]

        qs = _active_tenant_allocations()

        if search:
            qs = qs.filter(
                Q(tenant__full_name__icontains=search)
                | Q(unit__name__icontains=search)
                | Q(unit__building__name__icontains=search)
                | Q(unit__company__name__icontains=search)
            )

        if status == 'inactive':
            qs = qs.filter(tenant__status=False)

        if start:
            qs = qs.filter(tenant__lease_start_date__gte=start)

        if end:
            qs = qs.filter(tenant__lease_start_date__lte=end)

        rows = [
            [
                allocation.tenant.full_name,
                allocation.tenant.get_tenant_type_display(),
                allocation.unit.company.name,
                allocation.unit.building.name,
                allocation.unit.name,
                _format_date(allocation.tenant.lease_start_date),
                _format_date(allocation.tenant.lease_end_date),
                'Active' if allocation.tenant.status else 'Inactive',
            ]
            for allocation in qs.order_by(
                'unit__building__name',
                'unit__name',
                'tenant__full_name',
            )
        ]

        return headers, rows, [
            ('active', 'Active'),
            ('inactive', 'Inactive'),
        ]

    if report_type == 'system-summary':
        headers = ['Metric', 'Count']

        rows = [
            ['Companies / Clients', Company.objects.count()],
            [
                'Active Companies',
                Company.objects.filter(status=True).count(),
            ],
            ['Work Sites', WorkSite.objects.count()],
            [
                'Active Work Sites',
                WorkSite.objects.filter(status=True).count(),
            ],
            ['Buildings', Building.objects.count()],
            [
                'Active Buildings',
                Building.objects.filter(status=True).count(),
            ],
            ['Floors', Floor.objects.count()],
            ['Units', Unit.objects.count()],
            [
                'Active Units',
                Unit.objects.filter(status=True).count(),
            ],
            ['Tenants', Tenant.objects.count()],
            [
                'Active Tenants',
                Tenant.objects.filter(status=True).count(),
            ],
            ['Users', User.objects.count()],
            ['Guest Visits', GuestVisit.objects.count()],
            ['ID Tags', IDTag.objects.count()],
            [
                'Issued ID Tags',
                IDTag.objects.filter(
                    status=IDTag.STATUS_ISSUED
                ).count(),
            ],
            ['Hold Documents', HoldDocument.objects.count()],
        ]

        return headers, rows, []

    raise Http404


# ============================================================
# REPORT HOME
# ============================================================

@login_required
def reports_home(request):
    available = _available_reports(request)

    return render(
        request,
        'reports/home.html',
        {
            'reports': [
                (slug, info[0])
                for slug, info in available.items()
            ],
            'is_superadmin': request.user.is_superuser,
            'is_company_admin': (
                hasattr(request.user, 'company_staff')
                and not request.user.is_superuser
            ),
        },
    )


# ============================================================
# REPORT DETAIL
# ============================================================

@login_required
def report_detail(request, report_type):
    available = _available_reports(request)

    legacy_combined_report = (
        report_type == 'id-card-report'
        and not request.user.is_superuser
        and not (
            hasattr(request.user, 'company_staff')
            and not request.user.is_superuser
        )
    )

    if report_type not in available and not legacy_combined_report:
        raise Http404

    title, _ = available.get(
        report_type,
        ('ID Card Issue / Return Report', 'id_card_report'),
    )

    rows = []
    headers = []

    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    selected_status = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    can_return_tags = False

    # --------------------------------------------------------
    # COMPANY ADMIN
    # --------------------------------------------------------

    if (
        hasattr(request.user, 'company_staff')
        and not request.user.is_superuser
        and report_type in COMPANY_REPORTS
    ):
        headers, rows, company_status_choices = _company_report(
            report_type,
            request,
        )

        context = {
            'title': title,
            'headers': headers,
            'rows': rows,
            'start_date': start_date,
            'end_date': end_date,
            'status_choices': company_status_choices,
            'selected_status': selected_status,
            'search': search,
            'report_type': report_type,
            'can_return_tags': False,
            'is_superadmin': False,
            'is_company_admin': True,
            'show_date_filters': report_type in (
                'tenant-occupancy',
                'guest-visit-summary',
                'id-card-gate-pass-summary',
                'hold-document-summary',
            ),
        }

        download = request.GET.get('download', '')

        if download in ('pdf', 'excel'):
            return _report_export_response(
                request,
                report_type,
                title,
                headers,
                rows,
                download,
            )

        return render(request, 'reports/detail.html', context)

    # --------------------------------------------------------
    # SUPER ADMIN
    # --------------------------------------------------------

    if request.user.is_superuser:
        headers, rows, super_status_choices = _superadmin_report(
            report_type,
            request,
        )

        context = {
            'title': title,
            'headers': headers,
            'rows': rows,
            'start_date': start_date,
            'end_date': end_date,
            'status_choices': super_status_choices,
            'selected_status': selected_status,
            'search': search,
            'report_type': report_type,
            'can_return_tags': False,
            'is_superadmin': True,
            'is_company_admin': False,
            'show_date_filters': report_type == 'tenant-occupancy',
        }

        download = request.GET.get('download', '')

        if download in ('pdf', 'excel'):
            return _report_export_response(
                request,
                report_type,
                title,
                headers,
                rows,
                download,
            )

        return render(request, 'reports/detail.html', context)

    # --------------------------------------------------------
    # TENANT REPORTS
    # --------------------------------------------------------

    scope, _ = _report_scope(request)

    if report_type == 'guest-visit':
        qs = _guest_visit_queryset(request)

        start = _parse_date(start_date)
        end = _parse_date(end_date)

        if start:
            qs = qs.filter(visit_date__gte=start)

        if end:
            qs = qs.filter(visit_date__lte=end)

        if search:
            qs = qs.filter(
                Q(guest_name__icontains=search)
                | Q(
                    visitor_id_card_number__icontains=search
                )
                | Q(unit__name__icontains=search)
                | Q(unit__building__name__icontains=search)
                | Q(unit__company__name__icontains=search)
            )

        if selected_status in (
            GuestVisit.STATUS_PENDING,
            GuestVisit.STATUS_APPROVED,
            GuestVisit.STATUS_DENIED,
        ):
            qs = qs.filter(status=selected_status)

        # Company column is intentionally omitted for tenant reports.
        headers = [
            'Guest',
            'Guest ID',
            'Verification ID Type',
            'Verification ID Number',
            'Additional Visitors',
            'Total Visitors',
            'Building',
            'Unit',
            'Visit Purpose',
            'Visit Date',
            'Check-in',
            'Check-out',
            'Status',
        ]

        for visit in qs.order_by('-visit_date', '-created_at'):
            rows.append([
                visit.guest_name,
                visit.visitor_id_card_number or '—',
                visit.get_id_type_display() if visit.id_type else '—',
                visit.id_number or '—',
                visit.additional_visitors or 0,
                1 + (visit.additional_visitors or 0),
                visit.unit.building.name,
                visit.unit.name,
                (
                    visit.purpose_of_visit.name
                    if visit.purpose_of_visit_id
                    else '—'
                ),
                _format_date(visit.visit_date),
                _format_timestamp(visit.checked_in_at),
                _format_timestamp(visit.checked_out_at),
                _current_visit_status(visit),
            ])

    elif report_type == 'visit-duration':
        qs = _guest_visit_queryset(request).filter(
            checked_in_at__isnull=False
        )

        if search:
            qs = qs.filter(
                Q(guest_name__icontains=search)
                | Q(
                    visitor_id_card_number__icontains=search
                )
                | Q(unit__name__icontains=search)
                | Q(unit__building__name__icontains=search)
                | Q(unit__company__name__icontains=search)
            )

        qs, start_date, end_date = _date_range(
            request,
            'checked_in_at',
            qs,
        )

        if selected_status == 'active':
            qs = qs.filter(checked_out_at__isnull=True)

        elif selected_status == 'completed':
            qs = qs.filter(checked_out_at__isnull=False)

        else:
            selected_status = ''

        # Visit Date removed. Check-in includes both date and time.
        headers = [
            'Entry No.',
            'Guest',
            'Verification ID Type',
            'Verification ID Number',
            'Total Visitors',
            'Building',
            'Unit',
            'Check-in',
            'Check-out',
            'Duration',
            'Status',
        ]

        for visit in qs.order_by('-checked_in_at'):
            checkout_at = visit.checked_out_at
            is_completed = checkout_at is not None

            rows.append([
                visit.gate_pass_code or '—',
                visit.guest_name,
                visit.get_id_type_display() if visit.id_type else '—',
                visit.id_number or '—',
                1 + (visit.additional_visitors or 0),
                visit.unit.building.name,
                visit.unit.name,
                _format_timestamp(visit.checked_in_at),
                (
                    _format_timestamp(checkout_at)
                    if is_completed
                    else 'Still active'
                ),
                _format_duration(
                    visit.checked_in_at,
                    checkout_at,
                ),
                'Completed' if is_completed else 'Active',
            ])

    elif report_type in (
        'id-card-issue',
        'id-card-return',
        'id-card-report',
    ):
        qs = _tag_issue_queryset(request)

        qs, start_date, end_date = _date_range(
            request,
            'issued_at',
            qs,
        )

        if search:
            qs = qs.filter(
                Q(tag__tag_number__icontains=search)
                | Q(tag__nfc_number__icontains=search)
                | Q(visit__guest_name__icontains=search)
                | Q(visit__unit__name__icontains=search)
                | Q(
                    visit__unit__building__name__icontains=search
                )
            )

        if selected_status in (
            IDTagIssue.STATUS_ISSUED,
            IDTagIssue.STATUS_RETURNED,
        ):
            qs = qs.filter(status=selected_status)

        headers = [
            'Issue Ref',
            'Entry No.',
            'ID Tag Number',
            'Guest',
            'Verification ID Type',
            'Verification ID Number',
            'Building',
            'Unit',
            'Visit Date',
            'Issued At',
            'Issued By',
            'Issue Status',
            'Returned At',
            'Returned By',
            'Return Status',
        ]

        # Action column is only for the issue workflow.
        if report_type in ('id-card-issue', 'id-card-report'):
            headers.append('Action')

        # Only tenant users can record a tag return.
        can_return_tags = (
            report_type in ('id-card-issue', 'id-card-report')
            and scope == 'tenant'
        )

        for issue in qs.order_by('-issued_at'):
            returned = (
                issue.status != IDTagIssue.STATUS_ISSUED
            )

            row = [
                issue.pk,
                issue.visit.gate_pass_code or '—',
                issue.tag.tag_number,
                issue.visit.guest_name,
                (
                    issue.visit.get_id_type_display()
                    if issue.visit.id_type else '—'
                ),
                issue.visit.id_number or '—',
                issue.visit.unit.building.name,
                issue.visit.unit.name,
                _format_date(issue.visit.visit_date),
                _format_timestamp(issue.issued_at),
                issue.issued_by or '—',
                issue.get_status_display(),
                _format_timestamp(issue.returned_at),
                issue.returned_by or '—',
                'Returned' if returned else 'Not Returned',
            ]

            if report_type in (
                'id-card-issue',
                'id-card-report',
            ):
                row.append(
                    'Return'
                    if can_return_tags and not returned
                    else '—'
                )

            rows.append(row)

    else:
        qs = _tag_queryset(request)

        if search:
            qs = qs.filter(
                Q(tag_number__icontains=search)
                | Q(nfc_number__icontains=search)
                | Q(building__name__icontains=search)
            )

        if selected_status:
            valid_statuses = {
                value
                for value, _ in IDTag.STATUS_CHOICES
            }

            if selected_status in valid_statuses:
                qs = qs.filter(status=selected_status)
            else:
                selected_status = ''

        headers = [
            'ID Tag Number',
            'NFC Number',
            'Type',
            'Building',
            'Status',
            'Current Guest Visit',
            'Main Guest',
        ]

        for tag in qs.order_by('tag_number'):
            active_issue = (
                tag.active_issues[0]
                if tag.active_issues
                else None
            )

            rows.append([
                tag.tag_number,
                tag.nfc_number,
                tag.get_tag_type_display(),
                (
                    tag.building.name
                    if tag.building
                    else 'Not allocated'
                ),
                tag.get_status_display(),
                (
                    active_issue.visit.pk
                    if active_issue
                    else '—'
                ),
                (
                    active_issue.visit.guest_name
                    if active_issue
                    else '—'
                ),
            ])

    # --------------------------------------------------------
    # FILTER CHOICES
    # --------------------------------------------------------

    if report_type == 'guest-visit':
        filter_status_choices = GuestVisit.STATUS_CHOICES

    elif report_type == 'visit-duration':
        filter_status_choices = [
            ('active', 'Active'),
            ('completed', 'Completed'),
        ]

    elif report_type in (
        'id-card-issue',
        'id-card-return',
        'id-card-report',
    ):
        filter_status_choices = IDTagIssue.STATUS_CHOICES

    elif report_type == 'active-id-tags':
        filter_status_choices = IDTag.STATUS_CHOICES

    else:
        filter_status_choices = []

    show_date_filters = report_type in (
        'guest-visit',
        'visit-duration',
        'id-card-report',
        'id-card-issue',
        'id-card-return',
        'tenant-occupancy',
    )

    context = {
        'title': title,
        'headers': headers,
        'rows': rows,
        'start_date': start_date,
        'end_date': end_date,
        'search': search,
        'status_choices': filter_status_choices,
        'selected_status': selected_status,
        'show_date_filters': show_date_filters,
        'report_type': report_type,
        'can_return_tags': can_return_tags,
        'is_superadmin': False,
        'is_company_admin': False,
    }

    download = request.GET.get('download', '')

    if download in ('pdf', 'excel'):
        return _report_export_response(
            request,
            report_type,
            title,
            headers,
            rows,
            download,
        )

    return render(
        request,
        'reports/detail.html',
        context,
    )
