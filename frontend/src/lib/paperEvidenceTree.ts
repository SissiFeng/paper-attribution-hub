import type {
  AttributionCentrality,
  AttributionEvidencePath,
  AttributionEvidenceTree,
  AttributionTreeNode,
  Classification,
  Paper,
} from "@/types";

interface DerivedEvidence {
  source: string;
  type: string;
  quote: string;
  score: number;
  confidence: number | null;
  chunkIds?: string[];
  detector: string;
  polarity?: "positive" | "negative";
}

export interface EvidenceMapDataset {
  source: "server_aet" | "paper_payload";
  tree: AttributionEvidenceTree;
}

function stableId(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function centrality(score: number): AttributionCentrality {
  const magnitude = Math.abs(score);
  if (magnitude >= 0.75) return "core_contribution";
  if (magnitude >= 0.4) return "supporting_method";
  return "incidental_mention";
}

function scoreSignals(classification: Classification): DerivedEvidence[] {
  const values = [
    ["Author score", "author_signal", classification.author_score],
    ["Institution score", "institution_signal", classification.institution_score],
    ["Topic score", "topic_signal", classification.topic_score],
    ["Network score", "network_signal", classification.network_score],
    ["Full-text score", "fulltext_signal", classification.fulltext_evidence_score],
    ["Citation score", "citation_signal", classification.citation_score],
  ] as const;
  return values
    .filter(([, , score]) => score !== 0)
    .map(([label, type, score]) => ({
      source: "Classifier scores",
      type,
      quote: `${label}: ${score.toFixed(3)}`,
      score,
      confidence: classification.confidence,
      detector: classification.model_version,
    }));
}

function reasonSignal(
  reason: string,
  classification: Classification
): Pick<DerivedEvidence, "type" | "score"> {
  const normalized = reason.toLowerCase();
  if (normalized.includes("funding") || normalized.includes("ac/uoft")) {
    return {
      type: "funding_affiliation_signal",
      score: classification.funding_signal ?? classification.confidence,
    };
  }
  if (normalized.includes("tier-1") || normalized.includes("label query")) {
    return {
      type: "retrieval_signal",
      score: classification.retrieval_signal ?? classification.confidence,
    };
  }
  if (
    normalized.includes("architecture") ||
    normalized.includes("closed-loop")
  ) {
    return {
      type: "sdl_architecture_signal",
      score: classification.architecture_signal ?? classification.confidence,
    };
  }
  if (normalized.includes("member") && normalized.includes("author")) {
    return {
      type: "ac_author_signal",
      score: Math.max(classification.author_score, classification.confidence),
    };
  }
  if (normalized.includes("sdl tag")) {
    return {
      type: "sdl_topic_signal",
      score: Math.max(classification.topic_score, classification.confidence),
    };
  }
  return {
    type: "classification_reason",
    score: classification.confidence,
  };
}

function classificationEvidence(classification: Classification): DerivedEvidence[] {
  const evidence: DerivedEvidence[] = [
    ...classification.reasons.map((reason) => {
      const signal = reasonSignal(reason, classification);
      return {
        source: "Classification reasons",
        type: signal.type,
        quote: reason,
        score: signal.score,
        confidence: classification.confidence,
        detector: classification.model_version,
      };
    }),
    ...classification.matched_people.map((person) => ({
      source: "Matched authors",
      type: "author_match",
      quote: [
        person.name,
        person.match_type,
        person.institution ?? null,
      ]
        .filter(Boolean)
        .join(" · "),
      score: person.score,
      confidence: person.score,
      detector: "author_matcher",
    })),
    ...classification.matched_institutions.map((institution) => ({
      source: "Matched institutions",
      type: institution.is_partner
        ? "partner_institution_match"
        : "institution_match",
      quote:
        institution.matched_text ??
        `${institution.canonical_name}${institution.is_partner ? " · partner" : ""}`,
      score: institution.score,
      confidence: institution.score,
      detector: "institution_matcher",
    })),
    ...classification.matched_topics.map((topic) => ({
      source: "Matched topics",
      type: topic.is_core ? "core_topic_match" : "topic_match",
      quote: [topic.name, ...topic.hits].filter(Boolean).join(" · "),
      score: topic.score,
      confidence: topic.score,
      detector: "topic_matcher",
    })),
    ...classification.fulltext_evidence.map((item) => ({
      source: item.evidence_source || "Full text",
      type: item.evidence_type,
      quote: item.evidence_text,
      score: item.score,
      confidence: null,
      chunkIds: item.chunk_id ? [item.chunk_id] : [],
      detector: "fulltext_evidence",
      polarity: item.score < 0 ? ("negative" as const) : ("positive" as const),
    })),
    ...scoreSignals(classification),
  ];

  for (const path of classification.graph_signals?.second_degree_paths ?? []) {
    evidence.push({
      source: "Graph signals",
      type: "second_degree_author_path",
      quote: `${path.via_author_name} → ${path.ac_author_name}`,
      score: path.strength,
      confidence: path.strength,
      detector: "coauthor_graph",
    });
  }
  for (const citation of classification.graph_signals?.citation_signals ?? []) {
    evidence.push({
      source: "Graph signals",
      type: "ac_core_citation",
      quote: citation.cited_ac_core_title,
      score: classification.citation_score,
      confidence: classification.citation_score,
      detector: "citation_graph",
    });
  }
  return evidence;
}

export function deriveEvidenceMapFromPaper(paper: Paper): EvidenceMapDataset {
  const classification = paper.classification ?? null;
  const evidence = classification ? classificationEvidence(classification) : [];
  const generationSource = JSON.stringify({
    paperId: paper.id,
    updated: classification?.created_at ?? "",
    evidence,
  });
  const generationId = `live-${stableId(generationSource)}`;
  const rootId = `${generationId}:paper`;
  const root: AttributionTreeNode = {
    node_id: rootId,
    parent_node_id: null,
    node_type: "root",
    path: ["Paper"],
    section_type: null,
    title: paper.title,
    summary: [
      paper.year ?? null,
      paper.venue ?? null,
      classification?.label ?? "Unclassified",
    ]
      .filter(Boolean)
      .join(" · "),
    page_start: null,
    page_end: null,
    source_section_id: null,
    source_chunk_ids: [],
  };

  const sources = [...new Set(evidence.map((item) => item.source))].sort();
  const sourceNodes = new Map<string, AttributionTreeNode>();
  for (const source of sources) {
    const node: AttributionTreeNode = {
      node_id: `${generationId}:source:${stableId(source)}`,
      parent_node_id: rootId,
      node_type: "source",
      path: ["Paper", source],
      section_type: source.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
      title: source,
      summary: `Live paper payload · ${evidence.filter((item) => item.source === source).length} signals`,
      page_start: null,
      page_end: null,
      source_section_id: null,
      source_chunk_ids: [
        ...new Set(
          evidence
            .filter((item) => item.source === source)
            .flatMap((item) => item.chunkIds ?? [])
        ),
      ],
    };
    sourceNodes.set(source, node);
  }

  const paths: AttributionEvidencePath[] = evidence.map((item, index) => {
    const polarity = item.polarity ?? (item.score < 0 ? "negative" : "positive");
    const magnitude = Math.min(1, Math.max(0.08, Math.abs(item.score)));
    const pathId = `${generationId}:evidence:${index + 1}`;
    return {
      generation_id: generationId,
      path_id: pathId,
      rank: index + 1,
      node_id: sourceNodes.get(item.source)?.node_id ?? rootId,
      path: ["Paper", item.source, item.type],
      evidence_type: item.type,
      polarity,
      centrality: centrality(item.score),
      quote: item.quote,
      page_start: null,
      page_end: null,
      source_chunk_ids: item.chunkIds ?? [],
      raw_score: item.score,
      weight: polarity === "negative" ? -magnitude : magnitude,
      confidence: item.confidence,
      detector_type: item.detector,
      metadata_status: "legacy_fallback",
    };
  });

  return {
    source: "paper_payload",
    tree: {
      paper_id: paper.id,
      tree_version: "live-paper-payload-v0.1",
      generation_mode: "derived_ephemeral",
      generation_id: generationId,
      metadata_contract_version: "paper-classification-payload",
      nodes: [root, ...sourceNodes.values()],
      evidence_paths: paths,
      evidence_review_recommended: paths.length === 0,
      evidence_review_reasons:
        paths.length === 0 ? ["AET_NO_CLASSIFICATION_EVIDENCE"] : [],
    },
  };
}
