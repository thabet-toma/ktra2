/**
 * T-HR M1 — عميل REST للهيكل التنظيمي (وحدة `hr_suite` المرخّصة).
 *
 * الخادم `hr/org_api.py`: كل نقطة تفتح ببوابة الترخيص فترد **404** لا 403 على
 * شركةٍ غير مرخّصة — فالفشل هنا يُقرأ «لا وجود للوحدة»، وهو المقصود.
 *
 * الوحدة محايدة مالياً: قسمٌ ومسمّى وظيفي لا يمسّان قيداً ولا حساباً.
 */
import {
  apiDelete,
  apiGetList,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const DEPARTMENTS = "hr/departments/";
const JOB_TITLES = "hr/job-titles/";

const tenantOpts = () => ({ tenantId: resolveTenantId() });

export interface DepartmentRow {
  id: number;
  name: string;
  parent: number | null;
  parent_name: string | null;
  branch: number | null;
  branch_name: string | null;
  manager: number | null;
  manager_name: string | null;
  is_active: boolean;
  notes: string;
  employees_count: number;
}

export interface DepartmentDraft {
  name: string;
  parent?: number | null;
  branch?: number | null;
  manager?: number | null;
  is_active?: boolean;
  notes?: string;
}

export interface JobTitleRow {
  id: number;
  name: string;
  department: number | null;
  department_name: string | null;
  is_active: boolean;
  employees_count: number;
}

export interface JobTitleDraft {
  name: string;
  department?: number | null;
  is_active?: boolean;
}

export const listDepartments = (params?: { search?: string; active?: boolean }) =>
  apiGetList<DepartmentRow>(DEPARTMENTS, {
    ...tenantOpts(),
    query: {
      search: params?.search || undefined,
      active: params?.active === undefined ? undefined : params.active ? 1 : 0,
    },
  });

export const createDepartment = (draft: DepartmentDraft) =>
  apiPostObject<DepartmentRow>(DEPARTMENTS, draft, tenantOpts());

export const updateDepartment = (id: number, draft: Partial<DepartmentDraft>) =>
  apiPatchObject<DepartmentRow>(`${DEPARTMENTS}${id}/`, draft, tenantOpts());

export const deleteDepartment = (id: number) =>
  apiDelete(`${DEPARTMENTS}${id}/`, tenantOpts());

export const listJobTitles = (params?: { search?: string; department?: number }) =>
  apiGetList<JobTitleRow>(JOB_TITLES, {
    ...tenantOpts(),
    query: {
      search: params?.search || undefined,
      department: params?.department || undefined,
    },
  });

export const createJobTitle = (draft: JobTitleDraft) =>
  apiPostObject<JobTitleRow>(JOB_TITLES, draft, tenantOpts());

export const updateJobTitle = (id: number, draft: Partial<JobTitleDraft>) =>
  apiPatchObject<JobTitleRow>(`${JOB_TITLES}${id}/`, draft, tenantOpts());

export const deleteJobTitle = (id: number) =>
  apiDelete(`${JOB_TITLES}${id}/`, tenantOpts());
