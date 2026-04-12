import { apiPostObject } from "./restApi";

export async function sendAssistantMessage(message: string): Promise<string> {
  const data = await apiPostObject<{ reply?: string; detail?: string }>(
    "assistant/chat/",
    { message: message.trim() }
  );
  if (data.detail && typeof data.detail === "string" && !data.reply) {
    throw new Error(data.detail);
  }
  return (data.reply ?? "").trim();
}
