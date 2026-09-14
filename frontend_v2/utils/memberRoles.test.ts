import test from "node:test";
import assert from "node:assert/strict";

// node --test يحتاج امتداداً صريحاً في الاستيراد.
import {
  ASSIGNABLE_MEMBER_ROLES, MEMBER_ROLE_LABELS, isEmployeeMember,
  mapMemberToUser, memberRoleLabel,
} from "./memberRoles.ts";
import { userRoleLabel } from "./userRoleLabel.ts";

const row = (over: Record<string, unknown> = {}) => ({
  membership_id: 1,
  user_id: 42,
  username: "buyer",
  email: "buyer@example.test",
  full_name: "مسؤول المشتريات",
  role: "procurement",
  is_active: true,
  ...over,
});

test("دورُ المشتريات يصل الواجهةَ سليماً فيطابقه الفلتر", () => {
  const user = mapMemberToUser(row());
  assert.equal(user.role, "procurement");
  // فلترُ الشاشة: `user.role !== roleFilter` ⇒ يُستبعد. السحقُ القديم إلى
  // "employee" كان يجعل هذا الفلتر لا يطابق شيئاً أبداً عبر هذا المسار.
  assert.equal([user].filter((u) => u.role === "procurement").length, 1);
});

test("كلُّ أدوار العضوية تمرّ كما هي — لا سحقَ إلى مديرٍ/موظف", () => {
  for (const role of Object.keys(MEMBER_ROLE_LABELS)) {
    assert.equal(mapMemberToUser(row({ role })).role, role);
  }
});

test("isApproved من is_active وحدَه — لا قيمةَ مثبَّتة", () => {
  assert.equal(mapMemberToUser(row({ is_active: true })).isApproved, true);
  assert.equal(mapMemberToUser(row({ is_active: false })).isApproved, false);
  // حقلٌ غائبٌ لا يُقرأ «مفعَّلاً»: الكذبةُ الصامتة أسوأُ من نقطةٍ رمادية.
  assert.equal(mapMemberToUser(row({ is_active: undefined })).isApproved, false);
});

test("لا يُختلق ما لا تحمله العضوية", () => {
  const user = mapMemberToUser(row()) as unknown as Record<string, unknown>;
  assert.equal("employmentStatus" in user, false);
  assert.equal("isEmailVerified" in user, false);
});

test("الاسمُ يسقط على اسم المستخدم حين لا اسمَ كاملاً", () => {
  assert.equal(mapMemberToUser(row({ full_name: "" })).name, "buyer");
  assert.equal(mapMemberToUser(row({ email: "" })).email, "");
});

test("«موظف» في شاشات التقارير والنقاط = كلُّ عضوٍ ليس مديراً", () => {
  assert.equal(isEmployeeMember("manager"), false);
  for (const role of ["accountant", "sales", "procurement", "staff", "viewer",
    "ess", "field_staff", "legal_accountant"]) {
    assert.equal(isEmployeeMember(role), true, role);
  }
});

test("تسميةُ الدور مصدرُها `userRoleLabel` نفسُه — لا نسخةٌ ثانية", () => {
  assert.equal(memberRoleLabel("procurement"), "موظف مشتريات");
  assert.equal(memberRoleLabel("field_staff"), "موظف ميداني");
  // القاعدةُ الأولى في 212-P1: لا مفتاحَ إنجليزيٌّ يصل الشاشة.
  assert.equal(memberRoleLabel("role_from_the_future"), "مستخدم");
  assert.equal(memberRoleLabel(undefined), "مستخدم");
  // وكلُّ تسميةٍ تُعرَض في الشاشة هي حرفيّاً ما تعرضه الترويسة.
  for (const role of Object.keys(MEMBER_ROLE_LABELS)) {
    assert.equal(MEMBER_ROLE_LABELS[role], userRoleLabel(role), role);
  }
});

test("قائمةُ الإسناد أضيقُ من قائمة العرض — والمحاسبُ القانوني خارجها", () => {
  assert.equal(ASSIGNABLE_MEMBER_ROLES.includes("legal_accountant" as never), false);
  for (const role of ASSIGNABLE_MEMBER_ROLES) {
    assert.ok(MEMBER_ROLE_LABELS[role], role);
  }
});
