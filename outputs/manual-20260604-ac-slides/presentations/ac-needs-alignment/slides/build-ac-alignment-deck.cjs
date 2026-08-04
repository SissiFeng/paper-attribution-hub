const fs = require("fs");
const path = require("path");
const { Presentation, PresentationFile } = require("@oai/artifact-tool");

const OUT = "/Users/sissifeng/Downloads/paper-attribution-system/outputs/manual-20260604-ac-slides/presentations/ac-needs-alignment/output/ac-attribution-needs-alignment.pptx";
const W = 1280;
const H = 720;

const C = {
  bg: "#FBFCFA",
  ink: "#172126",
  muted: "#5E6A71",
  line: "#D7E0E5",
  dark: "#10181D",
  green: "#1F8A70",
  blue: "#2F6FED",
  amber: "#C7861A",
  orange: "#D75C2A",
  slate: "#31424D",
  purple: "#8B5CF6",
  pink: "#D9468F",
};

function slide(p, fn) {
  const s = p.slides.add({ width: W, height: H });
  rect(s, 0, 0, W, H, C.bg, "none", 0);
  fn(s);
}

function rect(s, x, y, w, h, fill = "#FFFFFF", line = C.line, radius = 8) {
  const sh = s.shapes.add({ geometry: "rect" });
  sh.position.set({ left: x, top: y, width: w, height: h });
  if (fill === "none") sh.fill.transparency = 100000;
  else sh.fill.color = fill;
  if (line === "none") sh.line.visible = false;
  else {
    sh.line.visible = true;
    sh.line.color = line;
    sh.line.width = 1;
  }
  if (radius) sh.borderRadius = radius;
  return sh;
}

function ellipse(s, x, y, w, h, fill, line = "none") {
  const sh = s.shapes.add({ geometry: "ellipse" });
  sh.position.set({ left: x, top: y, width: w, height: h });
  sh.fill.color = fill;
  if (line === "none") sh.line.visible = false;
  else {
    sh.line.visible = true;
    sh.line.color = line;
    sh.line.width = 1;
  }
}

function txt(s, value, x, y, w, h, opt = {}) {
  const sh = rect(s, x, y, w, h, "none", "none", 0);
  sh.text.set(value);
  sh.text.typeface = opt.typeface || "Aptos";
  sh.text.fontSize = opt.size || 20;
  sh.text.color = opt.color || C.ink;
  sh.text.bold = Boolean(opt.bold);
  sh.text.wrap = "square";
  sh.text.autoFit = "shrinkText";
  sh.text.alignment = opt.align || "left";
  sh.text.verticalAlignment = opt.valign || "top";
  sh.text.insets = { top: 0, right: 0, bottom: 0, left: 0 };
}

function line(s, x, y, w, h = 2, color = C.line) {
  rect(s, x, y, w, h, color, "none", 0);
}

function header(s, eyebrow, title, subtitle) {
  txt(s, eyebrow, 64, 42, 540, 22, { size: 13, bold: true, color: C.green });
  txt(s, title, 64, 76, 840, 86, { size: 36, bold: true });
  if (subtitle) txt(s, subtitle, 64, 158, 880, 46, { size: 18, color: C.muted });
  line(s, 64, 670, 1088, 1);
  txt(s, "AC paper attribution system · walkthrough", 64, 682, 520, 16, { size: 11, color: "#7B878D" });
}

function bullets(s, items, x, y, w, opt = {}) {
  const gap = opt.gap || 48;
  items.forEach((item, i) => {
    const yy = y + i * gap;
    ellipse(s, x, yy + 8, 10, 10, opt.color || C.green);
    txt(s, item, x + 26, yy, w - 26, opt.h || 34, { size: opt.size || 18, color: opt.textColor || C.ink });
  });
}

function formula(s, value, x, y, w, h, opt = {}) {
  rect(s, x, y, w, h, opt.fill || "#F6F8F9", opt.line || C.line, 6);
  txt(s, value, x + 18, y + 15, w - 36, h - 26, {
    size: opt.size || 19,
    bold: opt.bold ?? true,
    color: opt.color || C.slate,
    align: opt.align || "center",
  });
}

function formulaBlock(s, x, y, w, h, title, main, note, accent = C.green, opt = {}) {
  rect(s, x, y, w, h, opt.fill || C.dark, opt.line || `${accent}55`, 12);
  const pad = opt.compact ? 22 : 28;
  const titleY = y + (opt.compact ? 18 : 26);
  const mainY = y + (opt.compact ? 48 : 68);
  const lineY = opt.compact ? y + h - 48 : y + h - 76;
  const noteY = opt.compact ? y + h - 34 : y + h - 58;
  txt(s, title, x + pad, titleY, w - pad * 2, 18, {
    size: opt.titleSize || 11,
    bold: true,
    color: accent,
    typeface: "JetBrains Mono",
  });
  txt(s, main, x + pad, mainY, w - pad * 2, opt.mainH || 92, {
    size: opt.mainSize || 20,
    bold: true,
    color: "#EEF5F3",
    typeface: "JetBrains Mono",
    align: opt.align || "left",
  });
  line(s, x + pad, lineY, w - pad * 2, 1, "#35515A");
  txt(s, note, x + pad, noteY, w - pad * 2, opt.noteH || 42, {
    size: opt.noteSize || 12,
    color: "#B5C3C7",
    typeface: "JetBrains Mono",
  });
}

function insightCard(s, x, y, w, h, title, body, accent = C.green) {
  rect(s, x, y, w, h, "#FFFFFF", C.line, 8);
  rect(s, x, y, 4, h, accent, "none", 0);
  txt(s, title, x + 18, y + 16, w - 36, 18, {
    size: 12,
    bold: true,
    color: accent,
    typeface: "JetBrains Mono",
  });
  txt(s, body, x + 18, y + 44, w - 36, h - 54, { size: 14, color: C.muted });
}

function tag(s, label, x, y, color, w = 150) {
  rect(s, x, y, w, 34, `${color}18`, "none", 6);
  txt(s, label, x + 12, y + 8, w - 24, 18, { size: 13, bold: true, color });
}

function statCard(s, x, y, title, body) {
  rect(s, x, y, 250, 92, "#16242A", "#31515D", 8);
  txt(s, title, x + 24, y + 22, 190, 28, { size: 21, bold: true, color: "#FFFFFF" });
  txt(s, body, x + 24, y + 54, 190, 22, { size: 14, color: "#B9C6CB" });
}

function miniCard(s, x, y, title, body, color = C.green, w = 300, h = 92) {
  rect(s, x, y, w, h, "#FFFFFF", C.line, 8);
  txt(s, title, x + 20, y + 18, w - 40, 24, { size: 20, bold: true, color });
  txt(s, body, x + 20, y + 48, w - 40, h - 56, { size: 13, color: C.muted });
}

async function main() {
  const p = Presentation.create(undefined, { slideSize: { width: W, height: H } });

  slide(p, s => {
    rect(s, 0, 0, W, H, C.dark, "none", 0);
    rect(s, 0, 0, 10, H, C.green, "none", 0);
    txt(s, "System walkthrough", 72, 64, 520, 24, { size: 15, bold: true, color: "#91D6C2" });
    txt(s, "AC Literature Attribution System", 72, 112, 780, 108, { size: 44, bold: true, color: "#FFFFFF" });
    txt(s, "How the system turns broad paper search results into an AC knowledge base, then lets people query, explore, and reason over that knowledge.", 72, 240, 850, 74, { size: 22, color: "#CED8DD" });
    statCard(s, 72, 402, "Automated pipeline", "ingest → classify → evidence");
    statCard(s, 348, 402, "Knowledge base", "paper pages + entities + graph");
    statCard(s, 624, 402, "Exploration tools", "Agentic RAG · Multi-Graph · Co-author");
    txt(s, "Narrative: first show the pipeline, then explain the algorithm, then show how the digested database is consumed.", 72, 594, 920, 42, { size: 18, color: "#DDE5E8" });
  });

  slide(p, s => {
    header(s, "1 · Walkthrough flow", "Start with the big picture: this is a developing AC system", "The point is not only to classify papers once. The point is to maintain a living AC research knowledge system.");
    const steps = [
      ["Broad paper pool", "search pulls in thousands of candidate papers"],
      ["Automated classification", "papers are assigned relevance levels"],
      ["AC knowledge base", "AC-related papers enter the structured corpus"],
      ["Evidence + Wiki", "each paper gets reasons, scores, and a digest page"],
      ["Graph + Q&A tools", "Agentic RAG, Multi-Graph, Co-author, People Grid consume the corpus"],
    ];
    steps.forEach((st, i) => {
      const x = 70 + i * 218;
      ellipse(s, x + 34, 252, 62, 62, i === 2 ? "#EAF7F2" : "#F4F7F8", i === 2 ? C.green : C.line);
      txt(s, String(i + 1), x + 55, 272, 20, 20, { size: 20, bold: true, color: i === 2 ? C.green : C.muted, align: "center" });
      txt(s, st[0], x - 10, 338, 150, 26, { size: 17, bold: true, align: "center" });
      txt(s, st[1], x - 20, 370, 170, 34, { size: 12, color: C.muted, align: "center" });
      if (i < steps.length - 1) line(s, x + 112, 282, 90, 2);
    });
    formula(s, "paper → classification label + confidence + evidence → wiki/entity graph → retrieval/network/analytics", 138, 500, 880, 70, { color: C.slate });
  });

  slide(p, s => {
    header(s, "2 · What the pipeline classifies", "The system separates AC attribution from broader SDL relevance", "A paper can be relevant to the field without being attributable to AC.");
    const labels = [
      ["CORE_RELEVANT", "high-confidence AC / SDL core", C.green],
      ["RELATED_RELEVANT", "clear AC relation, weaker topic/core evidence", C.blue],
      ["SDL_FIELD_RELEVANT", "SDL field paper, weak AC attribution", C.purple],
      ["ADJACENT", "weak but potentially useful related signal", C.amber],
      ["UNCERTAIN", "needs reranker / judge / human review", C.orange],
      ["EXCLUDE", "no enough attribution or relevance signal", C.muted],
    ];
    labels.forEach((l, i) => {
      const x = i % 3 === 0 ? 90 : i % 3 === 1 ? 450 : 810;
      const y = i < 3 ? 236 : 402;
      rect(s, x, y, 300, 104, `${l[2]}15`, l[2], 8);
      txt(s, l[0], x + 20, y + 18, 250, 24, { size: 20, bold: true, color: l[2] });
      txt(s, l[1], x + 20, y + 52, 244, 34, { size: 14, color: C.muted });
    });
    txt(s, "AC-positive labels are what move directly into the AC knowledge-base workflow; other labels support review, field monitoring, and exclusion.", 164, 570, 850, 42, { size: 21, bold: true, color: C.slate, align: "center" });
  });

  slide(p, s => {
    header(s, "3 · Classification algorithm", "The score is interpretable: evidence signals are combined, then rules decide the label", "This is the part to explain after showing that the system can classify broad paper batches.");
    formulaBlock(
      s, 110, 218, 960, 210,
      "CLASSIFICATION CONFIDENCE",
      "confidence(paper) = Σ wi · signali(paper)",
      "signals = author match · institution match · topic relevance · network proximity · full-text evidence · citation evidence",
      C.green,
      { mainSize: 30, mainH: 70, align: "center", noteSize: 13 }
    );
    insightCard(s, 96, 478, 330, 118, "AC attribution score", "AC ≈ acknowledgement + funding + AC member + AC program + retrieval signal", C.green);
    insightCard(s, 474, 478, 330, 118, "SDL relevance score", "SDL ≈ architecture signal + retrieval signal + SDL topic / keyword signal", C.blue);
    insightCard(s, 852, 478, 330, 118, "Review gate", "High evidence promotes CORE / RELATED. Weak or conflicting evidence goes to review.", C.amber);
  });

  slide(p, s => {
    header(s, "4 · Paper page: score, reasons, audit trail", "Every classified paper has a detail page explaining why it was selected", "This is what makes the classification reviewable and traceable.");
    rect(s, 78, 226, 480, 364);
    txt(s, "Evidence drawer", 108, 256, 260, 28, { size: 25, bold: true, color: C.green });
    tag(s, "label + confidence", 108, 314, C.green, 164);
    tag(s, "score grid", 292, 314, C.blue, 104);
    tag(s, "human decision", 414, 314, C.amber, 140);
    bullets(s, [
      "Author / institution / topic / full-text / network / citation scores",
      "Matched AC people, institutions, topics, and evidence snippets",
      "Graph signals: second-degree collaborator paths, AC core citations",
      "Reviewer can confirm or correct the label with notes",
    ], 110, 376, 380, { size: 17, gap: 44, color: C.green, h: 32 });
    rect(s, 638, 226, 430, 364, "#F8FAFF", "#BED0F6");
    txt(s, "Why it matters", 668, 256, 260, 28, { size: 25, bold: true, color: C.blue });
    bullets(s, [
      "The system can answer: why is this paper AC-related?",
      "Each label has auditability: score + reasons + source evidence",
      "Human-confirmed labels become locked review knowledge",
      "This creates the paper-level foundation for the later graph and Q&A layer",
    ], 670, 318, 330, { size: 18, gap: 54, color: C.blue, h: 40 });
  });

  slide(p, s => {
    header(s, "5 · Wiki + entity extraction", "Each AC paper becomes a page in the knowledge-base layer", "The current system has the first step: digesting papers into structured, reusable knowledge.");
    const pipeline = [
      ["Paper", "title, abstract, metadata, full text"],
      ["Wiki page", "identity, provenance, SDL evidence, AC evidence, classification"],
      ["Entities", "people, institutions, topics, methods, funders, citations"],
      ["Knowledge graph", "nodes + edges used by retrieval and network tools"],
      ["Future Q&A", "LLM answers over the digested AC corpus"],
    ];
    pipeline.forEach((p, i) => {
      const x = 82 + i * 212;
      rect(s, x, 260, 150, 96, i === 3 ? "#EAF7F2" : "#FFFFFF", i === 3 ? C.green : C.line);
      txt(s, p[0], x + 16, 282, 118, 24, { size: 20, bold: true, color: i === 3 ? C.green : C.ink, align: "center" });
      txt(s, p[1], x + 14, 316, 122, 28, { size: 11, color: C.muted, align: "center" });
      if (i < pipeline.length - 1) line(s, x + 158, 308, 46, 2);
    });
    formula(s, "digested paper = markdown/wiki sections + extracted entities + traceable evidence pointers", 158, 476, 840, 70, { fill: "#F8FBFA", line: "#BBD8CC", color: C.green });
    txt(s, "Talk track: today the system builds paper-level pages and entity structure; the next layer is a richer graph-backed Q&A experience.", 170, 584, 820, 36, { size: 20, bold: true, color: C.slate, align: "center" });
  });

  slide(p, s => {
    header(s, "6 · Consumer 1: Agentic Graph RAG", "Once the corpus is digested, users can ask questions over it", "This page is the Q&A/search entry point: an ask box retrieves text evidence, graph context, and SQL facts from the AC database.");
    rect(s, 90, 236, 440, 332);
    txt(s, "Ask box examples", 120, 266, 250, 28, { size: 25, bold: true, color: C.blue });
    bullets(s, [
      "Which AC papers use Bayesian optimization?",
      "What automation platforms appear in self-driving lab papers?",
      "Which papers mention funding acknowledgements?",
      "Which papers connect NLP, automation, and materials discovery?",
    ], 122, 326, 350, { size: 18, gap: 52, color: C.blue, h: 38 });
    rect(s, 610, 236, 440, 332, "#F8FBFA", "#BBD8CC");
    txt(s, "Returned result", 640, 266, 250, 28, { size: 25, bold: true, color: C.green });
    bullets(s, [
      "Answer synthesized from retrieved source chunks",
      "Source papers and evidence snippets",
      "BM25 / cosine / graph score bars",
      "NL-to-SQL plan: intent, SQL, structured rows",
      "Graph path context: coauthor route or AC core citation",
      "Proposition hits: uses_method, funded_by, cites, topic",
    ], 642, 316, 350, { size: 16, gap: 38, color: C.green, h: 28 });
  });

  slide(p, s => {
    header(s, "7 · Retrieval algorithm", "The new layer adds NL-to-SQL without removing the original retrieval stack", "This is the LLM retrieval highlight: free-form questions can hit passages, graph paths, propositions, and database facts.");
    formulaBlock(
      s, 100, 196, 980, 112,
      "QUERY ROUTER",
      "query → chunks + graph paths + propositions + SQL facts",
      "The system can answer from passages, structured graph context, extracted claims, and exact database rows.",
      C.blue,
      { compact: true, mainSize: 25, mainH: 34, align: "center", noteSize: 12, noteH: 22 }
    );
    formulaBlock(
      s, 100, 332, 474, 134,
      "TEXT RANKING",
      "RRF(d) = 1/(60 + rankBM25)\n       + 1/(60 + rankcosine)",
      "BM25 handles exact terms; cosine handles semantic match.",
      C.blue,
      { compact: true, mainSize: 18, mainH: 52, noteSize: 11, noteH: 18 }
    );
    formulaBlock(
      s, 630, 332, 450, 134,
      "GRAPH BOOST",
      "final = text_score × (1 + 0.3·Gnorm)",
      "Graph score gently promotes papers central to AC relationships.",
      C.green,
      { compact: true, mainSize: 21, mainH: 44, noteSize: 11, noteH: 18 }
    );
    formulaBlock(
      s, 100, 490, 980, 112,
      "NL-TO-SQL",
      "natural language → constrained intent → read-only SQL → structured rows",
      "Adds exact counts, lists, top authors, institutions, and review queue rows without replacing retrieval.",
      C.pink,
      { compact: true, mainSize: 22, mainH: 34, align: "center", noteSize: 12, noteH: 22 }
    );
  });

  slide(p, s => {
    header(s, "8 · Consumer 2: Multi-Graph", "The graph page lets users explore the entities extracted from papers", "Each node is an entity; each edge is a relationship chosen by the user.");
    formulaBlock(
      s, 96, 218, 500, 160,
      "NODE SET",
      "V = authors ∪ institutions ∪ papers\n    ∪ topics ∪ methods ∪ funders",
      "Nodes are entities extracted from paper pages and wiki records.",
      C.blue,
      { compact: true, mainSize: 18, mainH: 62, noteSize: 11, noteH: 18 }
    );
    formulaBlock(
      s, 650, 218, 500, 160,
      "EDGE SET",
      "E = authored ∪ coauthored ∪ cites\n    ∪ topic ∪ method ∪ funding",
      "Edges are selected relationships; users choose which graph to compose.",
      C.green,
      { compact: true, mainSize: 18, mainH: 62, noteSize: 11, noteH: 18 }
    );
    const cases = [
      ["Co-author view", "author nodes + coauthored edges"],
      ["Citation view", "paper / AC core nodes + cites_ac_core edges"],
      ["Topic view", "paper / topic nodes + belongs_to_topic edges"],
      ["Method/funder view", "paper / method / funder nodes + propositions"],
    ];
    cases.forEach((c, i) => {
      const x = 114 + i * 260;
      rect(s, x, 470, 210, 88, i % 2 ? "#F8FAFF" : "#F8FBFA", i % 2 ? "#BED0F6" : "#BBD8CC");
      txt(s, c[0], x + 16, 490, 178, 22, { size: 18, bold: true, color: i % 2 ? C.blue : C.green, align: "center" });
      txt(s, c[1], x + 14, 520, 182, 26, { size: 12, color: C.muted, align: "center" });
    });
  });

  slide(p, s => {
    header(s, "9 · Why Multi-Graph matters", "It helps AC ask relationship questions that a table cannot answer", "The value is selective graph composition: choose which entities and relationships matter for the question.");
    rect(s, 80, 232, 330, 300);
    txt(s, "Question types", 110, 262, 220, 28, { size: 25, bold: true, color: C.green });
    bullets(s, [
      "Which topics connect to which institutions?",
      "Which papers cite AC core work?",
      "Which methods appear across multiple AC-related papers?",
      "Which funders or programs are visible in evidence?",
    ], 112, 322, 260, { size: 17, gap: 48, color: C.green, h: 34 });
    rect(s, 474, 232, 330, 300, "#F8FAFF", "#BED0F6");
    txt(s, "Interaction", 504, 262, 220, 28, { size: 25, bold: true, color: C.blue });
    bullets(s, [
      "Toggle node types",
      "Toggle edge types",
      "Use TimeSlider by year",
      "Click a node to focus ego graph",
      "Group by institution, topic, country, era, label, community",
    ], 506, 322, 260, { size: 17, gap: 38, color: C.blue, h: 28 });
    rect(s, 868, 232, 250, 300, "#FFF9EA", "#E8D6A8");
    txt(s, "Result", 898, 262, 160, 28, { size: 25, bold: true, color: C.amber });
    txt(s, "A visual map of how AC-attributed papers connect people, places, topics, methods, funding, and citation evidence.", 898, 328, 180, 120, { size: 20, bold: true, color: C.slate, align: "center" });
  });

  slide(p, s => {
    header(s, "10 · Consumer 3: Co-author intelligence", "The co-author page helps decide who AC should pay attention to", "It moves from visualization to prioritization: which people are important under a chosen lens?");
    rect(s, 80, 232, 450, 330);
    txt(s, "Use case", 110, 262, 220, 28, { size: 25, bold: true, color: C.blue });
    bullets(s, [
      "For a given topic or AC-relevant corpus, identify external collaborators or bridge authors",
      "Switch between author network and institution heatmap",
      "Click a person to see papers, collaborators, and importance explanation",
    ], 112, 322, 350, { size: 19, gap: 70, color: C.blue, h: 48 });
    rect(s, 624, 232, 450, 330, "#F8FBFA", "#BBD8CC");
    txt(s, "Six dimensions", 654, 262, 260, 28, { size: 25, bold: true, color: C.green });
    bullets(s, [
      "AC proximity",
      "Relationship strength",
      "Excess centrality",
      "Cross-SDL diversity",
      "Citation affinity",
      "Recency",
    ], 656, 318, 300, { size: 18, gap: 34, color: C.green, h: 25 });
  });

  slide(p, s => {
    header(s, "11 · Co-author importance formula", "The importance score is adjustable, but normalized", "If AC disagrees with the default lens, the page can change the weights and recompute.");
    formula(s, "importance(person) = Σ wi · dimensioni(person)", 160, 224, 820, 70);
    formula(s, "Σ wi = 1", 430, 320, 280, 60, { fill: "#F8FBFA", line: "#BBD8CC", color: C.green, size: 28 });
    const profiles = [
      ["AC attribution", "closer to AC and attributable work"],
      ["Bridge builders", "connect AC-adjacent communities"],
      ["Institution hubs", "durable institution-spanning collaboration"],
      ["Emerging connectors", "recent activity + early bridge potential"],
      ["Topic diffusion", "methods moving across SDL contexts"],
    ];
    profiles.forEach((pr, i) => {
      const x = 96 + i * 214;
      rect(s, x, 460, 176, 78, "#FFFFFF", C.line);
      txt(s, pr[0], x + 12, 478, 150, 20, { size: 15, bold: true, color: i % 2 ? C.blue : C.green, align: "center" });
      txt(s, pr[1], x + 14, 506, 148, 22, { size: 10, color: C.muted, align: "center" });
    });
    txt(s, "Talk track: this is not a fixed black-box ranking. The lens can be adjusted depending on whether AC cares about attribution, bridges, emerging people, or topic diffusion.", 150, 588, 860, 38, { size: 20, bold: true, color: C.slate, align: "center" });
  });

  slide(p, s => {
    header(s, "12 · AC members / People Grid", "The people view turns AC members into a structured periodic table", "This gives a simple entry point into the member-centric view of the knowledge base.");
    rect(s, 80, 232, 450, 330);
    txt(s, "Periodic table of people", 110, 262, 300, 28, { size: 25, bold: true, color: C.green });
    bullets(s, [
      "Each AC member is an element",
      "Symbol = two letters from surname",
      "Atomic number = number of attributed papers",
      "Color = top research topic / SDL category",
      "Click a person to see papers and focus the network",
    ], 112, 322, 360, { size: 18, gap: 42, color: C.green, h: 30 });
    rect(s, 624, 232, 450, 330, "#F8FAFF", "#BED0F6");
    txt(s, "Next layer", 654, 262, 240, 28, { size: 25, bold: true, color: C.blue });
    bullets(s, [
      "Member-specific paper list",
      "Personal collaboration graph",
      "Topic / method / institution context",
      "Long-term view of how AC influence radiates through the global research network",
    ], 656, 322, 340, { size: 19, gap: 58, color: C.blue, h: 42 });
  });

  slide(p, s => {
    header(s, "13 · What to align with AC", "The demo should end with decisions, not just features", "These choices determine how the system should behave over repeated update cycles.");
    bullets(s, [
      "Label policy: what exactly counts as AC, SDL-field, adjacent, uncertain, and exclude?",
      "Evidence standard: when can a paper automatically enter the AC knowledge base?",
      "Review policy: who reviews high-priority non-gold / uncertain papers, and how often?",
      "Graph policy: which relationships matter most for AC: coauthor, citation, topic, method, funding?",
      "People policy: which importance lens should guide outreach or collaboration analysis?",
      "Reporting policy: which metrics can be used in leadership or funder-facing claims?",
    ], 120, 220, 930, { size: 22, gap: 66, color: C.green, h: 46 });
  });

  slide(p, s => {
    header(s, "14 · Proposed next step", "Run the workflow on a real broad batch and calibrate with AC review", "The current platform is ready to support the first operating-cycle discussion.");
    const steps = [
      ["1", C.green, "Run broad ingest", "Use a 2,000-3,000 paper search result and let the system classify + build evidence pages."],
      ["2", C.blue, "Review border cases", "Use evidence drawer, Wiki, Agentic RAG, and Multi-Graph to inspect uncertain or high-value papers."],
      ["3", C.amber, "Tune operating contract", "Adjust thresholds, review rules, graph lenses, and people-importance profiles."],
    ];
    steps.forEach((st, i) => {
      const x = 104 + i * 350;
      rect(s, x, 246, 310, 190);
      txt(s, st[0], x + 26, 274, 36, 32, { size: 28, bold: true, color: st[1] });
      txt(s, st[2], x + 26, 326, 230, 34, { size: 24, bold: true });
      txt(s, st[3], x + 26, 374, 230, 58, { size: 16, color: C.muted });
    });
    txt(s, "Target outcome: a defensible, repeatable AC literature attribution workflow that becomes smarter as the database grows.", 144, 548, 888, 46, { size: 26, bold: true, color: C.slate, align: "center" });
  });

  const blob = await PresentationFile.exportPptx(p);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, Buffer.from(blob.data));
  console.log(OUT);
  process.exit(0);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
