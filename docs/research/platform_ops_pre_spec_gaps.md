# Platform Operations: Pre-Spec Gap Research

Issue: [#205](https://github.com/thabet-toma/ktra2/issues/205)

Base: `newktra` at `05a5ea656f891ae995454dd8ff7973ebf1f764a7`

Evidence tier: Verify (source fallback; graph tooling was unavailable in this session)

## Outcome

No discovery gap blocks `/to-spec`. The remaining choices can be specified now. The only fact the repository cannot answer is which production users currently act as platform operators; that becomes an explicit rollout inventory step, not a design question.

## 1. In-app notifications

### Repository evidence

- `hr/notify.py::_write` writes tenant-scoped `bridge.FirestoreMirrorDoc` records in the `notifications` collection. Delivery is best-effort.
- `frontend_v2/services/notificationsService.ts::subscribeToNotifications` reads the latest 50 notifications, then filters them in the client for the active user or `all_managers`.
- `frontend_v2/services/sqlApiClient.ts::onSnapshot` is an HTTP snapshot on mount and after the tab regains focus following 60 seconds. It is not a WebSocket subscription or periodic poll.
- `frontend_v2/components/notifications/NotificationCenter.tsx` is mounted by `AppLayout.tsx` and is the live notification surface.
- `notifications` is not a global collection in `bridge/views.py`; reusing it for a platform-wide shell would risk cross-tenant disclosure because user filtering currently happens after retrieval.
- No Django Channels/Daphne/WebSocket server was found. SMTP is intentionally absent in `core/settings.py`.

### Decision recommendation

- Notify the company owner through the existing tenant-scoped in-app notification path.
- Add a dedicated, server-filtered `PlatformNotification` API for the independent command center; reuse the presentational notification contract where useful.
- Refresh on entry and every 60 seconds while the tab is visible, with an explicit last-updated indicator. WebSockets and email are out of v1.

## 2. Timezone and the meaning of “day”

### Repository evidence

- `core/settings.py` uses `DJANGO_TIME_ZONE`, defaulting to `Asia/Hebron`, with `USE_TZ=True`.
- No per-user or per-tenant timezone field and no `timezone.activate` call was found.
- `hr/attendance.py::resolve_attendance_date` uses `timezone.localdate(moment)` and can attribute an after-midnight event to the preceding shift day.
- `core/date_ranges.py` is the required seam for datetime range filtering. `DateTimeField.__date` is unsafe on the production MySQL setup when timezone tables are unavailable.
- Attendance already stores explicit work dates in `CheckEvent.attendance_date` and `AttendanceDay.date`.

### Decision recommendation

- Use the platform operating timezone, configurable through Django and defaulting to `Asia/Hebron`, for attendance, daily evaluation, and snapshots in v1.
- Store timestamps in UTC and store `service_date` explicitly as a `DateField`.
- Treat the evaluation link’s 72-hour expiry as an absolute timestamp.
- Per-company and per-employee timezones are a later capability; historical dates must never be reinterpreted.

## 3. Platform employee identity and bootstrap

### Repository evidence

- No `PlatformOperationsStaff` entity or equivalent role exists.
- `auth.User` is global, while `UserCompanyMembership`, `hr.Employee`, and `employee_ops.EmployeeProfile` are tenant-scoped.
- Platform administration is inferred from `is_superuser` or configured email through `core.import_access.is_super_admin`; `is_staff` alone is not sufficient.
- The closest structural precedent is `AccountantProfile` plus `AccountantEngagement`: one global identity associated with multiple companies.
- Existing migration commands use `--dry-run`, are rerunnable, and avoid guessing relationships.

### Decision recommendation

- Create an explicit `PlatformEmployee` linked to `User`, with platform roles, specialty, and lifecycle status.
- A super admin may pass platform guards, but is not included in measured employee performance without an explicit `PlatformEmployee` row.
- Bootstrap through an idempotent command with `--dry-run` and an explicit user list. The report may show candidates, but it must not auto-enroll them.
- Production inventory identifies the first real employee and opt-in company; this is a rollout prerequisite, not a spec blocker.

## 4. Employee offboarding

### Repository evidence

- `core.platform_admin_api.platform_user_set_active` changes `User.is_active` only.
- `employee_ops.services.deactivate_employee` preserves employee history, removes only the relevant membership, and cancels pending invitations.
- `accountant_portal.services.suspend_engagement` and `revoke_engagement` lock the engagement, preserve audit fields, and revoke only relation-created access.
- Deleting `User` cascades company memberships and is therefore not an acceptable offboarding seam.

### Decision recommendation

Implement one idempotent transactional service that:

1. Locks the platform employee and active engagements.
2. Marks the employee `inactive` or `left` and cancels pending invitations.
3. Suspends engagements and removes only memberships proven to have been created by those engagements.
4. Returns open work orders to the reassignment queue without deleting them.
5. Preserves the employee, engagements, evaluations, work orders, and activity history.
6. Disables `User.is_active` only when the account is dedicated to platform employment; otherwise platform access alone is disabled.
7. Presents customer memberships created by the employee as a review list rather than deleting them automatically.

## 5. Advisory deliverables

### Repository evidence

- `core.reports._framework.ReportSpec` provides structured, generated reports but does not persist a delivered artifact.
- `employee_ops.models.TaskSubmission` provides a reviewable text-and-attachment submission lifecycle.
- `accountant_portal.models.PracticeDocument` provides a customer-linked attachment precedent.
- `ReviewPackageExportView` provides export and audit precedent.

### Decision recommendation

- Model advisory output as `WorkOrderDeliverable` owned by a work order, with `note`, `structured_report`, and `attachment` types.
- Store summary, attachment references, review status, reviewer, and approval timestamp.
- Reuse `ReportSpec` to render structured reports; persist an immutable delivery snapshot when sent to the customer.
- Do not build a separate recommendation engine in v1.
- Include a deliverable in daily evaluation only after its advisory work order is approved and closed.

## 6. Constraints the specification must state explicitly

1. **Bounded platform data exception.** Platform-owned entities may omit `tenant` only behind dedicated platform guards. Customer-related records carry optional `client_tenant`; ordinary tenant models remain strictly tenant-filtered.
2. **Platform activity log.** The current `ActivityLog` requires a tenant and integer entity id, so it cannot record UUID-based platform work orders as-is. Introduce a platform activity log or explicitly redesign the existing model.
3. **Dedicated platform notifications.** The independent command center must not query tenant notification collections globally or filter confidential data in the browser.
4. **Membership service seam.** Extract membership mutation services from `tenants/views.py`, add audit, and keep dependency direction one-way; `tenants` must not import the new operations module.
5. **Created-membership provenance.** A manager role grants broad access, so `created_membership` and an audit of memberships created by the agent are safety requirements.
6. **Secure upload contracts.** External intake and recruiting need endpoints that return protected attachment IDs. Reuse the upload core, not the current raw-URL HTTP contract.
7. **Explicit platform billing tenant.** Monthly billing must fail closed if the operating tenant is not configured, and invoices must use the normal sales and accounting services.
8. **Comments inherit customer scope.** A work-order comment inherits optional `client_tenant`; `client_visible` is forbidden when no customer company exists.
9. **No datetime `__date` filters.** Daily metrics use explicit `service_date` or `core.date_ranges`.
10. **Sales attribution is feasible; membership attribution is incomplete.** `SalesInvoice.created_by` supports handled-sales reporting, but membership writes need provenance and audit before transparency claims are complete.

## Proposed resolution of final policy ticket

- Notifications: tenant bell for customer owners; dedicated platform inbox; visible-tab 60-second refresh; no email/WebSocket in v1.
- Capacity: weighted capacity units based on open work, SLA pressure, and package complexity; policy target by specialty; override requires a reason.
- Offboarding: transactional suspension, selective access revocation, requeue open work, and preserve history.
- Time: configurable platform timezone (`Asia/Hebron` default), UTC timestamps, explicit service dates.
- Deliverables: reviewable work-order notes, structured reports, and attachments; no separate recommendation engine.
- Rollout: one explicitly selected platform employee and one opt-in company, preceded by a dry-run report; no inferred migration or historical backfill without evidence.

## Coverage and limitations

The requested codebase-memory graph and `check_index_coverage` were not callable in the research session, so verification fell back to targeted repository search and direct source reading. The principal inspected paths were:

`core/settings.py`, `core/date_ranges.py`, `core/models.py`, `core/activity.py`, `core/platform_admin_api.py`, `core/import_access.py`, `core/access.py`, `core/modules.py`, `core/media_views.py`, `core/reports_api.py`, `core/reports/_framework.py`, `bridge/models.py`, `bridge/views.py`, `hr/notify.py`, `hr/models.py`, `hr/attendance.py`, `hr/authentication.py`, `tenants/models.py`, `tenants/views.py`, `tenants/services.py`, `employee_ops/models.py`, `employee_ops/services.py`, `employee_ops/management/commands/migrate_employee_ops_mirror.py`, `accountant_portal/models.py`, `accountant_portal/services.py`, `accountant_portal/practice.py`, `accountant_portal/views.py`, `accountant_portal/management/commands/migrate_accountant_offices.py`, `sales/models.py`, `sales/views.py`, `frontend_v2/App.tsx`, `frontend_v2/components/layout/AppLayout.tsx`, `frontend_v2/components/notifications/NotificationCenter.tsx`, `frontend_v2/services/notificationsService.ts`, `frontend_v2/services/sqlApiClient.ts`, and `frontend_v2/types/notification.ts`.

Source searches also covered timezone fields/activation, Channels/Daphne/WebSocket consumers, SMTP, platform-staff symbols, and platform-notification models. Production data was not read, so the number and identity of accounts needing bootstrap remain intentionally unknown.
