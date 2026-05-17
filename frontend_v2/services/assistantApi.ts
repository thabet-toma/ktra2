/**
 * طلبات المساعد تذهب إلى Django فقط (مسارات assistant/* تحت VITE_API_URL).
 * الاتصال بـ OpenClaw يتم من خادم Django، ليس من المتصفح.
 */
import { apiPostFormData, apiPostObject } from "./restApi";

export async function uploadAssistantFile(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const data = await apiPostFormData<{ file_id?: string; detail?: string }>(
    "assistant/files/",
    form
  );
  const id = (data.file_id ?? "").trim();
  if (!id) {
    throw new Error("لم يُعاد معرّف الملف من الخادم.");
  }
  return id;
}

export async function sendAssistantMessage(
  message: string,
  fileIds?: string[]
): Promise<string> {
  const trimmed = message.trim();
  const ids = (fileIds ?? []).map((x) => x.trim()).filter(Boolean);
  const data = await apiPostObject<{ reply?: string; detail?: string }>(
    "assistant/chat/",
    {
      message: trimmed,
      ...(ids.length ? { file_ids: ids } : {}),
    }
  );
  if (data.detail && typeof data.detail === "string" && !data.reply) {
    throw new Error(data.detail);
  }
  return (data.reply ?? "").trim();
}
