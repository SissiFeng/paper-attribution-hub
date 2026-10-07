import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  chatPageContext,
  numericSearchParam,
  scopedEvidencePaperId,
} from "../src/lib/chatContext";

const chat = readFileSync("src/components/GlobalChat.tsx", "utf8");
const main = readFileSync("src/main.tsx", "utf8");
const api = readFileSync("src/lib/api.ts", "utf8");
const css = readFileSync("src/styles.css", "utf8");
const chatApi = readFileSync("../backend/app/api/chat.py", "utf8");
const chatService = readFileSync("../backend/app/services/chat_service.py", "utf8");
const sqlService = readFileSync("../backend/app/services/nl_to_sql_service.py", "utf8");

assert.equal(main.includes('import { GlobalChat }'), true);
assert.equal(main.indexOf("</Routes>") < main.indexOf("<GlobalChat />"), true);
assert.equal(chat.includes("useLocation"), true);
assert.equal(chat.includes("sessionStorage"), true);
assert.equal(chat.includes("AbortController"), true);
assert.equal(chat.includes("requestGeneration"), true);
assert.equal(chat.includes("inFlightRef"), true);
assert.equal(chat.includes("90_000"), true);
assert.equal(chat.includes("cancelRequest"), true);
assert.equal(chat.includes("streamChatMessage"), true);
assert.equal(chat.includes("createChatSession"), true);
assert.equal(chat.includes("New chat"), true);
assert.equal(chat.includes("Tier 1 only"), true);
assert.equal(chat.includes("Read-only tools"), true);
assert.equal(chat.includes("Sources required"), true);
assert.equal(chat.includes("Citation-linked synthesis"), true);
assert.equal(chat.includes("Insufficient evidence"), true);
assert.equal(chat.includes('role="dialog"'), true);
assert.equal(chat.includes('aria-live="polite"'), true);
assert.equal(chat.includes('event.key === "Escape"'), true);
assert.equal(chat.includes("MAX_QUERY_LENGTH = 2000"), true);
assert.equal(chat.includes("Inspect query, rows, and audit trail"), true);
assert.equal(chat.includes("submitRagFeedback"), true);
assert.equal(chat.includes("dangerouslySetInnerHTML"), false);
assert.equal(chat.includes("innerHTML"), false);

assert.equal(api.includes('request<ChatSession>("/chat/sessions"'), true);
assert.equal(api.includes("/messages/stream"), true);
assert.equal(api.includes('Accept: "text/event-stream"'), true);
assert.equal(api.includes("paperFilterPayloadFromSearchParams(search)"), true);
assert.equal(chatApi.includes('prefix="/chat"'), true);
assert.equal(chatApi.includes("StreamingResponse"), true);
assert.equal(chatService.includes('answer_kind="verified_structured"'), true);
assert.equal(chatService.includes('answer_kind = "insufficient_evidence"'), true);
assert.equal(chatService.includes("ensure_safe_query(normalized_query)"), true);
assert.equal(sqlService.includes("_llm_plan"), false);
assert.equal(sqlService.includes("import openai"), false);
assert.equal(sqlService.includes("import anthropic"), false);
assert.equal(sqlService.includes('"llm_used": False'), true);
assert.equal(sqlService.includes("sqlalchemy-bound-parameters"), true);
assert.equal(css.includes("@media (max-width: 720px)"), true);
assert.equal(css.includes("@media (prefers-reduced-motion: reduce)"), true);
assert.equal(css.includes("min-height: 48px"), true);
assert.equal(css.includes(".global-chat-trust"), true);
assert.equal(css.includes(".global-chat-sql-audit"), true);

const emptyParams = new URLSearchParams();
assert.equal(numericSearchParam(emptyParams, "year_from"), null);
assert.equal(numericSearchParam(new URLSearchParams("year_from="), "year_from"), null);
assert.equal(numericSearchParam(new URLSearchParams("year_from=2021"), "year_from"), 2021);
assert.equal(numericSearchParam(new URLSearchParams("year_from=nan"), "year_from"), null);
assert.equal(
  chatPageContext(
    "/timeline",
    "?labels=CORE_RELEVANT&labels=RELATED_RELEVANT&timeline_by=field&secret=drop-me",
  ),
  "Dashboard route: /timeline?labels=CORE_RELEVANT&labels=RELATED_RELEVANT&timeline_by=field",
);
assert.equal(scopedEvidencePaperId("/papers/P%20001/evidence-map"), "P 001");
assert.equal(scopedEvidencePaperId("/timeline"), null);

console.log("Persistent evidence chat contract checks passed.");
