import { renderToStaticMarkup } from "react-dom/server";

import { MarkdownView } from "../src/pages/TransferStudioPage";

const html = renderToStaticMarkup(
  <MarkdownView md={"# Proposal\n\nA regular paragraph.\n\n- A cited result [src:P_1]"} />
);

if (!html.includes("A regular paragraph.")) {
  throw new Error("Transfer proposal paragraph was not rendered");
}
if (!html.includes("P_1")) {
  throw new Error("Transfer proposal citation was not rendered");
}

console.log("Transfer markdown contract check passed.");
