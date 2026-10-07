export type StoryDataStatus = "illustrative_poc" | "local_snapshot" | "verified_snapshot";

export interface StoryScope {
  label: string;
  included_papers: number;
  reviewed_papers: number;
  fulltext_papers: number;
  classified_papers: number;
}

export interface TimelineSeries {
  name: string;
  color: string;
  values: number[];
}

export interface FlowNode {
  id: string;
  name: string;
  layer: "institution" | "topic" | "label";
  color: string;
}

export interface FlowLink {
  source: string;
  target: string;
  value: number;
}

export interface EvidenceCard {
  eyebrow: string;
  value: string;
  label: string;
  detail: string;
  source_link: string;
  tone: "gold" | "teal" | "rose";
}

export interface VisualStory extends Record<string, unknown> {
  contract_version: "visual_story.v1";
  story_id: string;
  title: string;
  subtitle: string;
  period_label: string;
  generated_at: string;
  data_status: StoryDataStatus;
  scope: StoryScope;
  timeline: {
    years: number[];
    series: TimelineSeries[];
    annotation: string;
  };
  flow: {
    nodes: FlowNode[];
    links: FlowLink[];
    annotation: string;
  };
  evidence_cards: EvidenceCard[];
  audit: {
    filter_fingerprint: string;
    paper_set_sha256: string;
    algorithm: string;
    metric_definitions: Record<string, string>;
    source_endpoints: string[];
  };
}
