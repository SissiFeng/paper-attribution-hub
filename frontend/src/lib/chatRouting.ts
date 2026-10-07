import type { SqlChatOut } from "@/types";

const UNSAFE_SQL_FAILURE =
  /raw sql|write-oriented|drop table|delete from|insert into|update\s+\w+/i;

export function sqlResultNeedsEvidence(result: SqlChatOut): boolean {
  return result.rows.length === 0;
}

export function sqlErrorAllowsEvidenceFallback(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("422") && !UNSAFE_SQL_FAILURE.test(message);
}

export function evidenceSearchQuery(result: SqlChatOut | undefined): string | null {
  if (!result) return null;
  const constraints = result.audit.query_constraints;
  for (const key of ["proposition_object", "text"]) {
    const value = constraints[key];
    if (typeof value === "string" && value.trim().length >= 2) {
      return value.trim();
    }
  }
  return null;
}
