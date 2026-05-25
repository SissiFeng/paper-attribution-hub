/**
 * Mock data for all API endpoints.
 * Activated automatically when the backend is unreachable (fetch fails),
 * or when VITE_USE_MOCK=true is set in the environment.
 */

import type {
  AnalyticsOverview,
  DiscoveryCandidate,
  DriftReport,
  EvalReport,
  EvidenceGapReport,
  GeographicReport,
  GraphExplanation,
  ImpactReport,
  InstitutionNetworkPayload,
  MissedPaperGroup,
  MultiGraphPayload,
  NetworkPayload,
  Paper,
  PeopleGrid,
  PipelineRun,
  QueueItem,
  ReportResult,
  SankeyPayload,
  TimelinePayload,
} from "@/types";

// ─── Papers ──────────────────────────────────────────────────────────────────

export const MOCK_PAPERS: Paper[] = [
  {
    id: "p001",
    title: "Solid-state lithium metal batteries with garnet-type electrolytes: recent progress and perspective",
    abstract: "We review recent progress in solid-state lithium metal batteries using garnet-type oxide electrolytes, focusing on interfacial engineering and ionic conductivity enhancement.",
    year: 2023,
    venue: "Nature Energy",
    doi: "10.1038/s41560-023-01234-5",
    keywords: ["solid-state electrolyte", "lithium metal", "garnet", "ionic conductivity"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Sarah Chen", order: 1, affiliation: "University of Toronto" },
      { name: "Michael Schmidt", order: 2, affiliation: "ETH Zurich" },
      { name: "Yuki Tanaka", order: 3, affiliation: "NIMS" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.96,
      author_score: 0.9,
      institution_score: 0.85,
      topic_score: 0.92,
      network_score: 0.78,
      fulltext_evidence_score: 0.88,
      citation_score: 0.71,
      matched_people: [
        { person_id: "ac001", name: "Sarah Chen", match_type: "direct", score: 0.95, institution: "University of Toronto" },
        { person_id: "ac002", name: "Michael Schmidt", match_type: "direct", score: 0.87, institution: "ETH Zurich" },
      ],
      matched_institutions: [
        { institution_id: "i001", canonical_name: "University of Toronto", is_partner: true, score: 0.95 },
        { institution_id: "i002", canonical_name: "ETH Zurich", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.95, hits: ["garnet", "solid-state", "electrolyte"] },
        { topic_id: "t002", name: "Lithium metal anodes", is_core: true, score: 0.88, hits: ["lithium metal", "anode"] },
      ],
      reasons: ["AC author Sarah Chen (primary)", "Partner institution UofT", "Core topic: solid-state electrolytes"],
      model_version: "v2.1",
      created_at: "2024-01-15T10:00:00Z",
      fulltext_evidence: [],
      graph_signals: { network_score: 0.78, citation_score: 0.71, second_degree_paths: [], citation_signals: [], cites_corpus: ["p004", "p007"] },
    },
    review: null,
  },
  {
    id: "p002",
    title: "Dendrite suppression strategies in lithium metal batteries: A comprehensive review",
    abstract: "Lithium dendrite growth remains the major bottleneck for commercial adoption of lithium metal anodes. This review covers electrolyte design, artificial SEI, and 3D host strategies.",
    year: 2023,
    venue: "Chemical Reviews",
    doi: "10.1021/acs.chemrev.3c00589",
    keywords: ["dendrite", "lithium metal", "SEI", "electrolyte"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Elena Rodriguez", order: 1, affiliation: "Imperial College London" },
      { name: "James Liu", order: 2, affiliation: "Argonne National Laboratory" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.91,
      author_score: 0.88,
      institution_score: 0.76,
      topic_score: 0.94,
      network_score: 0.62,
      fulltext_evidence_score: 0.82,
      citation_score: 0.69,
      matched_people: [
        { person_id: "ac003", name: "Elena Rodriguez", match_type: "direct", score: 0.91, institution: "Imperial College London" },
      ],
      matched_institutions: [
        { institution_id: "i003", canonical_name: "Imperial College London", is_partner: true, score: 0.91 },
        { institution_id: "i004", canonical_name: "Argonne National Laboratory", is_partner: false, score: 0.72 },
      ],
      matched_topics: [
        { topic_id: "t003", name: "Dendrite suppression", is_core: true, score: 0.97, hits: ["dendrite", "suppression", "lithium metal"] },
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.74, hits: ["electrolyte", "SEI"] },
      ],
      reasons: ["AC author Elena Rodriguez", "Core topic: dendrite suppression", "High citation overlap with corpus"],
      model_version: "v2.1",
      created_at: "2024-01-16T08:30:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: { paper_id: "p002", human_label: "CORE_RELEVANT", reviewer: "sissi.feng@utoronto.ca", notes: "Confirmed — strong match", created_at: "2024-02-01T12:00:00Z" },
  },
  {
    id: "p003",
    title: "Machine learning accelerated discovery of solid electrolyte materials",
    abstract: "We apply graph neural networks and active learning to screen 50,000 candidate inorganic electrolytes, identifying 12 novel compositions with predicted ionic conductivity > 10 mS/cm.",
    year: 2024,
    venue: "Nature Materials",
    doi: "10.1038/s41563-024-01821-x",
    keywords: ["machine learning", "solid electrolyte", "GNN", "materials discovery"],
    full_text_available: true,
    provenance: "discovered_auto",
    authors: [
      { name: "Wei Zhang", order: 1, affiliation: "Stanford University" },
      { name: "Sarah Chen", order: 2, affiliation: "University of Toronto" },
      { name: "Priya Sharma", order: 3, affiliation: "Carnegie Mellon University" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.89,
      author_score: 0.85,
      institution_score: 0.80,
      topic_score: 0.88,
      network_score: 0.74,
      fulltext_evidence_score: 0.79,
      citation_score: 0.65,
      matched_people: [
        { person_id: "ac001", name: "Sarah Chen", match_type: "direct", score: 0.95, institution: "University of Toronto" },
      ],
      matched_institutions: [
        { institution_id: "i001", canonical_name: "University of Toronto", is_partner: true, score: 0.95 },
        { institution_id: "i005", canonical_name: "Stanford University", is_partner: false, score: 0.70 },
      ],
      matched_topics: [
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.92, hits: ["solid electrolyte", "ionic conductivity"] },
        { topic_id: "t007", name: "Machine learning for batteries", is_core: true, score: 0.90, hits: ["GNN", "active learning", "machine learning"] },
      ],
      reasons: ["AC author Sarah Chen (co-author)", "Auto-discovered via citation network", "Core topics: solid electrolytes + ML"],
      model_version: "v2.1",
      created_at: "2024-03-01T09:00:00Z",
      fulltext_evidence: [],
      graph_signals: { network_score: 0.74, citation_score: 0.65, second_degree_paths: [], citation_signals: [], cites_corpus: ["p001"] },
    },
    review: null,
  },
  {
    id: "p004",
    title: "Fast-charging lithium-ion batteries: From electrode design to system management",
    abstract: "Fast charging capability is critical for EV adoption. We analyze the electrochemical limitations and engineering strategies across electrode, electrolyte, and BMS layers.",
    year: 2022,
    venue: "Advanced Energy Materials",
    doi: "10.1002/aenm.202201945",
    keywords: ["fast charging", "lithium-ion", "BMS", "electrode"],
    full_text_available: false,
    provenance: "manual",
    authors: [
      { name: "Yuki Tanaka", order: 1, affiliation: "NIMS" },
      { name: "Hana Kimura", order: 2, affiliation: "Toyota Central R&D" },
    ],
    classification: {
      label: "RELATED_RELEVANT",
      confidence: 0.77,
      author_score: 0.82,
      institution_score: 0.71,
      topic_score: 0.79,
      network_score: 0.55,
      fulltext_evidence_score: 0.0,
      citation_score: 0.60,
      matched_people: [
        { person_id: "ac004", name: "Yuki Tanaka", match_type: "direct", score: 0.88, institution: "NIMS" },
      ],
      matched_institutions: [
        { institution_id: "i006", canonical_name: "NIMS", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t005", name: "Fast charging", is_core: false, score: 0.84, hits: ["fast charging", "C-rate", "charging protocol"] },
        { topic_id: "t006", name: "Battery management systems", is_core: false, score: 0.76, hits: ["BMS", "system management"] },
      ],
      reasons: ["AC author Yuki Tanaka", "Related topic: fast charging", "No full text available"],
      model_version: "v2.1",
      created_at: "2024-01-17T14:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p005",
    title: "Thermal management strategies for lithium-ion battery packs in electric vehicles",
    abstract: "Battery thermal management is essential for safety and longevity. We evaluate phase-change materials, liquid cooling, and hybrid approaches for EV battery packs.",
    year: 2023,
    venue: "Journal of Power Sources",
    doi: "10.1016/j.jpowsour.2023.233456",
    keywords: ["thermal management", "EV", "phase-change material", "cooling"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Carlos Mendes", order: 1, affiliation: "University of São Paulo" },
      { name: "Michael Schmidt", order: 2, affiliation: "ETH Zurich" },
    ],
    classification: {
      label: "RELATED_RELEVANT",
      confidence: 0.72,
      author_score: 0.75,
      institution_score: 0.68,
      topic_score: 0.71,
      network_score: 0.50,
      fulltext_evidence_score: 0.65,
      citation_score: 0.52,
      matched_people: [
        { person_id: "ac002", name: "Michael Schmidt", match_type: "direct", score: 0.87, institution: "ETH Zurich" },
      ],
      matched_institutions: [
        { institution_id: "i002", canonical_name: "ETH Zurich", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t008", name: "Thermal management", is_core: false, score: 0.88, hits: ["thermal management", "cooling", "temperature"] },
      ],
      reasons: ["AC author Michael Schmidt (co-author)", "Related topic: thermal management"],
      model_version: "v2.1",
      created_at: "2024-01-18T11:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p006",
    title: "Sodium-ion batteries: Materials, mechanisms, and prospects",
    abstract: "Sodium-ion batteries are emerging as cost-effective alternatives to lithium-ion. We review cathode materials, hard carbon anodes, and electrolyte developments.",
    year: 2023,
    venue: "Chemical Society Reviews",
    doi: "10.1039/d3cs00346a",
    keywords: ["sodium-ion", "hard carbon", "cathode", "post-lithium"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "James Liu", order: 1, affiliation: "Argonne National Laboratory" },
      { name: "Priya Sharma", order: 2, affiliation: "Carnegie Mellon University" },
      { name: "Elena Rodriguez", order: 3, affiliation: "Imperial College London" },
    ],
    classification: {
      label: "ADJACENT",
      confidence: 0.58,
      author_score: 0.65,
      institution_score: 0.60,
      topic_score: 0.55,
      network_score: 0.42,
      fulltext_evidence_score: 0.58,
      citation_score: 0.48,
      matched_people: [
        { person_id: "ac003", name: "Elena Rodriguez", match_type: "direct", score: 0.91, institution: "Imperial College London" },
      ],
      matched_institutions: [
        { institution_id: "i003", canonical_name: "Imperial College London", is_partner: true, score: 0.91 },
      ],
      matched_topics: [
        { topic_id: "t009", name: "Sodium-ion batteries", is_core: false, score: 0.72, hits: ["sodium-ion", "Na-ion"] },
      ],
      reasons: ["AC author Elena Rodriguez (co-author)", "Adjacent topic: sodium-ion (not core focus)", "Low topic score"],
      model_version: "v2.1",
      created_at: "2024-01-19T16:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p007",
    title: "High-voltage cathode materials for next-generation lithium batteries",
    abstract: "We investigate spinel and layered oxide cathode materials operating above 4.5V vs Li+/Li, with emphasis on structural stability and electrolyte compatibility.",
    year: 2022,
    venue: "ACS Energy Letters",
    doi: "10.1021/acsenergylett.2c01756",
    keywords: ["cathode", "high voltage", "spinel", "layered oxide"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Sarah Chen", order: 1, affiliation: "University of Toronto" },
      { name: "Wei Zhang", order: 2, affiliation: "Stanford University" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.88,
      author_score: 0.92,
      institution_score: 0.85,
      topic_score: 0.85,
      network_score: 0.70,
      fulltext_evidence_score: 0.82,
      citation_score: 0.74,
      matched_people: [
        { person_id: "ac001", name: "Sarah Chen", match_type: "direct", score: 0.95, institution: "University of Toronto" },
      ],
      matched_institutions: [
        { institution_id: "i001", canonical_name: "University of Toronto", is_partner: true, score: 0.95 },
      ],
      matched_topics: [
        { topic_id: "t010", name: "Electrode materials", is_core: true, score: 0.88, hits: ["cathode", "spinel", "layered oxide"] },
      ],
      reasons: ["AC author Sarah Chen (primary)", "Core topic: electrode materials"],
      model_version: "v2.1",
      created_at: "2024-01-20T09:00:00Z",
      fulltext_evidence: [],
      graph_signals: { network_score: 0.70, citation_score: 0.74, second_degree_paths: [], citation_signals: [], cites_corpus: [] },
    },
    review: null,
  },
  {
    id: "p008",
    title: "Operando X-ray tomography of lithium dendrite formation at solid electrolyte interfaces",
    abstract: "Using synchrotron X-ray tomography, we capture real-time 3D visualization of dendrite nucleation and growth in garnet-type solid electrolytes under electrochemical cycling.",
    year: 2024,
    venue: "Joule",
    doi: "10.1016/j.joule.2024.02.018",
    keywords: ["operando", "X-ray tomography", "dendrite", "solid electrolyte"],
    full_text_available: true,
    provenance: "discovered_approved",
    authors: [
      { name: "Michael Schmidt", order: 1, affiliation: "ETH Zurich" },
      { name: "Lars Eriksson", order: 2, affiliation: "Uppsala University" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.93,
      author_score: 0.88,
      institution_score: 0.90,
      topic_score: 0.95,
      network_score: 0.72,
      fulltext_evidence_score: 0.90,
      citation_score: 0.68,
      matched_people: [
        { person_id: "ac002", name: "Michael Schmidt", match_type: "direct", score: 0.87, institution: "ETH Zurich" },
      ],
      matched_institutions: [
        { institution_id: "i002", canonical_name: "ETH Zurich", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t003", name: "Dendrite suppression", is_core: true, score: 0.90, hits: ["dendrite", "nucleation", "growth"] },
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.92, hits: ["solid electrolyte", "garnet"] },
      ],
      reasons: ["AC author Michael Schmidt (primary)", "Synchrotron study — high novelty", "Core topics: dendrites + solid electrolytes"],
      model_version: "v2.1",
      created_at: "2024-03-15T10:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p009",
    title: "Self-healing polymer electrolytes for mechanically robust solid-state batteries",
    abstract: "We design a polysiloxane-based polymer electrolyte with autonomous self-healing capability, achieving 98% conductivity recovery after mechanical damage.",
    year: 2023,
    venue: "Advanced Functional Materials",
    doi: "10.1002/adfm.202309312",
    keywords: ["self-healing", "polymer electrolyte", "polysiloxane", "solid-state"],
    full_text_available: false,
    provenance: "manual",
    authors: [
      { name: "Aiko Nakamura", order: 1, affiliation: "Kyoto University" },
      { name: "Yuki Tanaka", order: 2, affiliation: "NIMS" },
    ],
    classification: {
      label: "RELATED_RELEVANT",
      confidence: 0.74,
      author_score: 0.78,
      institution_score: 0.70,
      topic_score: 0.77,
      network_score: 0.52,
      fulltext_evidence_score: 0.0,
      citation_score: 0.58,
      matched_people: [
        { person_id: "ac004", name: "Yuki Tanaka", match_type: "direct", score: 0.88, institution: "NIMS" },
      ],
      matched_institutions: [
        { institution_id: "i006", canonical_name: "NIMS", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.82, hits: ["polymer electrolyte", "solid-state"] },
      ],
      reasons: ["AC author Yuki Tanaka (co-author)", "Related: polymer electrolytes"],
      model_version: "v2.1",
      created_at: "2024-02-10T14:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p010",
    title: "Carbon nanotube-reinforced silicon anodes for high-energy lithium-ion batteries",
    abstract: "Silicon anodes offer 10× higher theoretical capacity than graphite but suffer from volume expansion. We use CNT scaffolding to buffer mechanical stress and maintain cycle stability.",
    year: 2022,
    venue: "Nano Letters",
    doi: "10.1021/acs.nanolett.2c03144",
    keywords: ["silicon anode", "CNT", "volume expansion", "cycle stability"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Priya Sharma", order: 1, affiliation: "Carnegie Mellon University" },
      { name: "James Liu", order: 2, affiliation: "Argonne National Laboratory" },
    ],
    classification: {
      label: "UNCERTAIN",
      confidence: 0.52,
      author_score: 0.60,
      institution_score: 0.55,
      topic_score: 0.58,
      network_score: 0.38,
      fulltext_evidence_score: 0.50,
      citation_score: 0.44,
      matched_people: [],
      matched_institutions: [],
      matched_topics: [
        { topic_id: "t010", name: "Electrode materials", is_core: true, score: 0.62, hits: ["silicon anode", "anode"] },
      ],
      reasons: ["No AC authors matched directly", "Electrode materials topic — borderline", "Confidence below threshold"],
      model_version: "v2.1",
      created_at: "2024-01-22T10:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p011",
    title: "Quantum chemistry calculations for Li+ solvation in ether-based electrolytes",
    abstract: "DFT and MD simulations reveal the solvation shell structure of Li+ in DOL/DME electrolytes and predict optimal salt concentrations for reduced desolvation barriers.",
    year: 2023,
    venue: "Journal of Chemical Theory and Computation",
    doi: "10.1021/acs.jctc.3c00820",
    keywords: ["DFT", "MD simulation", "solvation", "ether electrolyte"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "Elena Rodriguez", order: 1, affiliation: "Imperial College London" },
      { name: "Thomas Müller", order: 2, affiliation: "Max Planck Institute" },
    ],
    classification: {
      label: "ADJACENT",
      confidence: 0.55,
      author_score: 0.70,
      institution_score: 0.65,
      topic_score: 0.50,
      network_score: 0.40,
      fulltext_evidence_score: 0.52,
      citation_score: 0.45,
      matched_people: [
        { person_id: "ac003", name: "Elena Rodriguez", match_type: "direct", score: 0.91, institution: "Imperial College London" },
      ],
      matched_institutions: [
        { institution_id: "i003", canonical_name: "Imperial College London", is_partner: true, score: 0.91 },
      ],
      matched_topics: [],
      reasons: ["AC author but topic (quantum chem) is adjacent to core program", "Low topic score"],
      model_version: "v2.1",
      created_at: "2024-01-23T11:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p012",
    title: "Electrochemical impedance spectroscopy for battery state-of-health estimation",
    abstract: "We propose an EIS-based SoH estimation protocol using equivalent circuit models and machine learning regression, validated across 500 commercial 18650 cells.",
    year: 2024,
    venue: "Journal of The Electrochemical Society",
    doi: "10.1149/1945-7111/ad4321",
    keywords: ["EIS", "SoH", "battery diagnostics", "machine learning"],
    full_text_available: true,
    provenance: "discovered_auto",
    authors: [
      { name: "Yuki Tanaka", order: 1, affiliation: "NIMS" },
      { name: "Sarah Chen", order: 2, affiliation: "University of Toronto" },
    ],
    classification: {
      label: "RELATED_RELEVANT",
      confidence: 0.79,
      author_score: 0.88,
      institution_score: 0.80,
      topic_score: 0.74,
      network_score: 0.65,
      fulltext_evidence_score: 0.75,
      citation_score: 0.62,
      matched_people: [
        { person_id: "ac004", name: "Yuki Tanaka", match_type: "direct", score: 0.88, institution: "NIMS" },
        { person_id: "ac001", name: "Sarah Chen", match_type: "direct", score: 0.95, institution: "University of Toronto" },
      ],
      matched_institutions: [
        { institution_id: "i006", canonical_name: "NIMS", is_partner: true, score: 0.88 },
        { institution_id: "i001", canonical_name: "University of Toronto", is_partner: true, score: 0.95 },
      ],
      matched_topics: [
        { topic_id: "t006", name: "Battery management systems", is_core: false, score: 0.80, hits: ["SoH", "state-of-health", "diagnostics"] },
        { topic_id: "t007", name: "Machine learning for batteries", is_core: true, score: 0.78, hits: ["machine learning", "regression"] },
      ],
      reasons: ["Two AC authors", "Related: BMS diagnostics", "ML for batteries topic"],
      model_version: "v2.1",
      created_at: "2024-03-20T12:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p013",
    title: "Recycling of spent lithium-ion batteries: Process design and life cycle assessment",
    abstract: "We present a hydrometallurgical recycling route for NMC cathodes with 98% Li recovery and perform LCA showing 65% reduction in CO₂ equivalent vs. virgin material.",
    year: 2022,
    venue: "Nature Sustainability",
    doi: "10.1038/s41893-022-00851-w",
    keywords: ["recycling", "NMC", "LCA", "hydrometallurgy"],
    full_text_available: false,
    provenance: "manual",
    authors: [
      { name: "Fatima Al-Rashid", order: 1, affiliation: "King Abdullah University" },
      { name: "Carlos Mendes", order: 2, affiliation: "University of São Paulo" },
    ],
    classification: {
      label: "EXCLUDE",
      confidence: 0.82,
      author_score: 0.20,
      institution_score: 0.15,
      topic_score: 0.25,
      network_score: 0.10,
      fulltext_evidence_score: 0.0,
      citation_score: 0.18,
      matched_people: [],
      matched_institutions: [],
      matched_topics: [],
      reasons: ["No AC authors or partner institutions", "Topic (recycling/LCA) outside core program", "High exclusion confidence"],
      model_version: "v2.1",
      created_at: "2024-01-25T15:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
  {
    id: "p014",
    title: "Interface engineering for stable solid-liquid electrolyte junctions in hybrid batteries",
    abstract: "Hybrid solid-liquid electrolyte systems can combine the safety of solid electrolytes with the kinetics of liquid electrolytes. We design in-situ polymerized interfaces for improved stability.",
    year: 2024,
    venue: "Energy & Environmental Science",
    doi: "10.1039/d4ee00123a",
    keywords: ["hybrid electrolyte", "interface", "in-situ polymerization", "safety"],
    full_text_available: true,
    provenance: "discovered_auto",
    authors: [
      { name: "Michael Schmidt", order: 1, affiliation: "ETH Zurich" },
      { name: "Elena Rodriguez", order: 2, affiliation: "Imperial College London" },
      { name: "Yuki Tanaka", order: 3, affiliation: "NIMS" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.94,
      author_score: 0.92,
      institution_score: 0.91,
      topic_score: 0.93,
      network_score: 0.80,
      fulltext_evidence_score: 0.88,
      citation_score: 0.75,
      matched_people: [
        { person_id: "ac002", name: "Michael Schmidt", match_type: "direct", score: 0.87, institution: "ETH Zurich" },
        { person_id: "ac003", name: "Elena Rodriguez", match_type: "direct", score: 0.91, institution: "Imperial College London" },
        { person_id: "ac004", name: "Yuki Tanaka", match_type: "direct", score: 0.88, institution: "NIMS" },
      ],
      matched_institutions: [
        { institution_id: "i002", canonical_name: "ETH Zurich", is_partner: true, score: 0.88 },
        { institution_id: "i003", canonical_name: "Imperial College London", is_partner: true, score: 0.91 },
        { institution_id: "i006", canonical_name: "NIMS", is_partner: true, score: 0.88 },
      ],
      matched_topics: [
        { topic_id: "t001", name: "Solid-state electrolytes", is_core: true, score: 0.95, hits: ["solid electrolyte", "hybrid", "interface"] },
        { topic_id: "t004", name: "Battery safety", is_core: true, score: 0.82, hits: ["safety", "stability"] },
      ],
      reasons: ["Three AC authors", "Three partner institutions", "Core topics: solid electrolytes + safety"],
      model_version: "v2.1",
      created_at: "2024-04-01T08:00:00Z",
      fulltext_evidence: [],
      graph_signals: { network_score: 0.80, citation_score: 0.75, second_degree_paths: [], citation_signals: [], cites_corpus: ["p001", "p002"] },
    },
    review: null,
  },
  {
    id: "p015",
    title: "Anode-free lithium metal batteries: Fundamentals and prospects",
    abstract: "Anode-free batteries maximize energy density by eliminating pre-deposited lithium. We review nucleation control, current collector surface engineering, and capacity retention strategies.",
    year: 2023,
    venue: "Advanced Materials",
    doi: "10.1002/adma.202307148",
    keywords: ["anode-free", "lithium metal", "energy density", "current collector"],
    full_text_available: true,
    provenance: "manual",
    authors: [
      { name: "James Liu", order: 1, affiliation: "Argonne National Laboratory" },
      { name: "Sarah Chen", order: 2, affiliation: "University of Toronto" },
    ],
    classification: {
      label: "CORE_RELEVANT",
      confidence: 0.90,
      author_score: 0.88,
      institution_score: 0.82,
      topic_score: 0.90,
      network_score: 0.68,
      fulltext_evidence_score: 0.85,
      citation_score: 0.72,
      matched_people: [
        { person_id: "ac001", name: "Sarah Chen", match_type: "direct", score: 0.95, institution: "University of Toronto" },
      ],
      matched_institutions: [
        { institution_id: "i001", canonical_name: "University of Toronto", is_partner: true, score: 0.95 },
      ],
      matched_topics: [
        { topic_id: "t002", name: "Lithium metal anodes", is_core: true, score: 0.95, hits: ["anode-free", "lithium metal", "nucleation"] },
        { topic_id: "t003", name: "Dendrite suppression", is_core: true, score: 0.78, hits: ["capacity retention", "surface engineering"] },
      ],
      reasons: ["AC author Sarah Chen (co-author)", "Core topics: lithium metal + dendrites"],
      model_version: "v2.1",
      created_at: "2024-02-20T09:00:00Z",
      fulltext_evidence: [],
      graph_signals: null,
    },
    review: null,
  },
];

// ─── Analytics Overview ───────────────────────────────────────────────────────

export const MOCK_OVERVIEW: AnalyticsOverview = {
  total_papers: 15,
  label_breakdown: {
    CORE_RELEVANT: 7,
    RELATED_RELEVANT: 4,
    ADJACENT: 2,
    UNCERTAIN: 1,
    EXCLUDE: 1,
  },
  years: [2020, 2021, 2022, 2023, 2024],
};

// ─── Review Queue ─────────────────────────────────────────────────────────────

export const MOCK_QUEUE: QueueItem[] = [
  {
    paper_id: "p010",
    title: "Carbon nanotube-reinforced silicon anodes for high-energy lithium-ion batteries",
    label: "UNCERTAIN",
    confidence: 0.52,
    priority: 1,
    reasons: ["No AC authors matched directly", "Electrode materials topic — borderline"],
    last_classified_at: "2024-01-22T10:00:00Z",
    provenance: "manual",
    has_human_review: false,
  },
  {
    paper_id: "p006",
    title: "Sodium-ion batteries: Materials, mechanisms, and prospects",
    label: "ADJACENT",
    confidence: 0.58,
    priority: 2,
    reasons: ["AC author Elena Rodriguez (co-author)", "Adjacent topic: sodium-ion"],
    last_classified_at: "2024-01-19T16:00:00Z",
    provenance: "manual",
    has_human_review: false,
  },
  {
    paper_id: "p011",
    title: "Quantum chemistry calculations for Li+ solvation in ether-based electrolytes",
    label: "ADJACENT",
    confidence: 0.55,
    priority: 3,
    reasons: ["AC author but topic (quantum chem) is adjacent to core program"],
    last_classified_at: "2024-01-23T11:00:00Z",
    provenance: "manual",
    has_human_review: false,
  },
  {
    paper_id: "p004",
    title: "Fast-charging lithium-ion batteries: From electrode design to system management",
    label: "RELATED_RELEVANT",
    confidence: 0.77,
    priority: 4,
    reasons: ["AC author Yuki Tanaka", "Related topic: fast charging"],
    last_classified_at: "2024-01-17T14:00:00Z",
    provenance: "manual",
    has_human_review: false,
  },
];

// ─── Pipeline Runs ────────────────────────────────────────────────────────────

export const MOCK_PIPELINE_RUNS: PipelineRun[] = [
  {
    run_id: "run-2024-04-15-001",
    status: "success",
    duration_seconds: 312,
    started_at: "2024-04-15T02:00:00Z",
    finished_at: "2024-04-15T02:05:12Z",
    discovered_candidates: 23,
    auto_ingested: 2,
    queued_for_review: 5,
    classified_new: 8,
    reclassified_stale: 3,
    enqueued_for_review: 4,
    error_message: null,
    triggered_by: "scheduler",
    steps: [
      { name: "discovery", status: "ok", started_at: "2024-04-15T02:00:00Z", candidates: 23 },
      { name: "fulltext_fetch", status: "ok", started_at: "2024-04-15T02:01:30Z", fetched: 18 },
      { name: "classify", status: "ok", started_at: "2024-04-15T02:03:00Z", classified: 11 },
      { name: "enqueue", status: "ok", started_at: "2024-04-15T02:04:50Z", enqueued: 4 },
    ],
  },
  {
    run_id: "run-2024-04-14-001",
    status: "success",
    duration_seconds: 287,
    started_at: "2024-04-14T02:00:00Z",
    finished_at: "2024-04-14T02:04:47Z",
    discovered_candidates: 18,
    auto_ingested: 1,
    queued_for_review: 3,
    classified_new: 6,
    reclassified_stale: 2,
    enqueued_for_review: 3,
    error_message: null,
    triggered_by: "scheduler",
    steps: [
      { name: "discovery", status: "ok", started_at: "2024-04-14T02:00:00Z", candidates: 18 },
      { name: "fulltext_fetch", status: "ok", started_at: "2024-04-14T02:01:20Z", fetched: 14 },
      { name: "classify", status: "ok", started_at: "2024-04-14T02:02:50Z", classified: 8 },
      { name: "enqueue", status: "ok", started_at: "2024-04-14T02:04:30Z", enqueued: 3 },
    ],
  },
  {
    run_id: "run-2024-04-13-001",
    status: "failed",
    duration_seconds: 45,
    started_at: "2024-04-13T02:00:00Z",
    finished_at: "2024-04-13T02:00:45Z",
    discovered_candidates: 0,
    auto_ingested: 0,
    queued_for_review: 0,
    classified_new: 0,
    reclassified_stale: 0,
    enqueued_for_review: 0,
    error_message: "OpenAlex API timeout after 3 retries",
    triggered_by: "scheduler",
    steps: [
      { name: "discovery", status: "error", started_at: "2024-04-13T02:00:00Z", error: "OpenAlex API timeout after 3 retries" },
    ],
  },
  {
    run_id: "run-2024-04-12-001",
    status: "success",
    duration_seconds: 341,
    started_at: "2024-04-12T02:00:00Z",
    finished_at: "2024-04-12T02:05:41Z",
    discovered_candidates: 31,
    auto_ingested: 3,
    queued_for_review: 7,
    classified_new: 12,
    reclassified_stale: 4,
    enqueued_for_review: 6,
    error_message: null,
    triggered_by: "manual",
    steps: [
      { name: "discovery", status: "ok", started_at: "2024-04-12T02:00:00Z", candidates: 31 },
      { name: "fulltext_fetch", status: "ok", started_at: "2024-04-12T02:01:45Z", fetched: 25 },
      { name: "classify", status: "ok", started_at: "2024-04-12T02:03:30Z", classified: 15 },
      { name: "enqueue", status: "ok", started_at: "2024-04-12T02:05:20Z", enqueued: 6 },
    ],
  },
];

// ─── Evidence Gaps ────────────────────────────────────────────────────────────

export const MOCK_EVIDENCE_GAPS: EvidenceGapReport = {
  total_papers_scanned: 15,
  buckets: [
    {
      bucket: "no_fulltext",
      label: "Missing Full Text",
      description: "Papers classified without full-text evidence — confidence may be lower",
      count: 3,
      entries: [
        { paper_id: "p004", title: "Fast-charging lithium-ion batteries", label: "RELATED_RELEVANT", confidence: 0.77, missing_types: ["fulltext"], present_types: ["author", "institution", "topic"], reason: "Full text unavailable from OpenAlex" },
        { paper_id: "p009", title: "Self-healing polymer electrolytes", label: "RELATED_RELEVANT", confidence: 0.74, missing_types: ["fulltext"], present_types: ["author", "institution", "topic"], reason: "Paywalled — no OA version found" },
        { paper_id: "p013", title: "Recycling of spent lithium-ion batteries", label: "EXCLUDE", confidence: 0.82, missing_types: ["fulltext"], present_types: ["author"], reason: "Excluded without full text" },
      ],
    },
    {
      bucket: "no_graph_signals",
      label: "Weak Graph Coverage",
      description: "Papers with no co-authorship or citation graph signals — network evidence missing",
      count: 5,
      entries: [
        { paper_id: "p004", title: "Fast-charging lithium-ion batteries", label: "RELATED_RELEVANT", confidence: 0.77, missing_types: ["graph"], present_types: ["author", "topic"], reason: "No shared co-authors in graph" },
        { paper_id: "p005", title: "Thermal management strategies", label: "RELATED_RELEVANT", confidence: 0.72, missing_types: ["graph"], present_types: ["author", "institution"], reason: "Isolated in citation network" },
        { paper_id: "p006", title: "Sodium-ion batteries", label: "ADJACENT", confidence: 0.58, missing_types: ["graph", "citation"], present_types: ["author"], reason: "Adjacent topic — low network relevance" },
        { paper_id: "p010", title: "CNT-reinforced silicon anodes", label: "UNCERTAIN", confidence: 0.52, missing_types: ["author", "institution", "graph"], present_types: ["topic"], reason: "No AC network connections found" },
        { paper_id: "p011", title: "Quantum chemistry for Li+ solvation", label: "ADJACENT", confidence: 0.55, missing_types: ["graph", "citation"], present_types: ["author"], reason: "Quantum chem outside co-author network" },
      ],
    },
    {
      bucket: "low_confidence_relevant",
      label: "Low-Confidence Inclusions",
      description: "Papers classified as relevant but with confidence < 0.65 — may need human review",
      count: 2,
      entries: [
        { paper_id: "p006", title: "Sodium-ion batteries", label: "ADJACENT", confidence: 0.58, missing_types: ["topic"], present_types: ["author", "institution"], reason: "Topic score below threshold for core inclusion" },
        { paper_id: "p010", title: "CNT-reinforced silicon anodes", label: "UNCERTAIN", confidence: 0.52, missing_types: ["author", "institution", "graph"], present_types: ["topic"], reason: "Needs human verification" },
      ],
    },
  ],
};

// ─── People Grid ──────────────────────────────────────────────────────────────

export const MOCK_PEOPLE_GRID: PeopleGrid = {
  total_people: 5,
  max_papers: 6,
  categories: [
    { id: "pi", label: "Principal Investigators", paper_count: 14 },
    { id: "postdoc", label: "Postdoctoral Researchers", paper_count: 8 },
    { id: "phd", label: "PhD Students", paper_count: 5 },
    { id: "collab", label: "Collaborators", paper_count: 6 },
  ],
  elements: [
    {
      person_id: "ac001",
      symbol: "SC",
      name: "Sarah Chen",
      atomic_number: 1,
      category: "pi",
      category_label: "Principal Investigators",
      institution: "University of Toronto",
      country: "Canada",
      orcid: "0000-0001-1234-5678",
      core_count: 4,
      related_count: 2,
      papers: [
        { id: "p001", title: "Solid-state lithium metal batteries with garnet-type electrolytes", year: 2023, label: "CORE_RELEVANT" },
        { id: "p003", title: "Machine learning accelerated discovery of solid electrolyte materials", year: 2024, label: "CORE_RELEVANT" },
        { id: "p007", title: "High-voltage cathode materials for next-generation lithium batteries", year: 2022, label: "CORE_RELEVANT" },
        { id: "p012", title: "Electrochemical impedance spectroscopy for battery state-of-health estimation", year: 2024, label: "RELATED_RELEVANT" },
        { id: "p015", title: "Anode-free lithium metal batteries: Fundamentals and prospects", year: 2023, label: "CORE_RELEVANT" },
      ],
    },
    {
      person_id: "ac002",
      symbol: "MS",
      name: "Michael Schmidt",
      atomic_number: 2,
      category: "pi",
      category_label: "Principal Investigators",
      institution: "ETH Zurich",
      country: "Switzerland",
      orcid: "0000-0002-2345-6789",
      core_count: 3,
      related_count: 1,
      papers: [
        { id: "p001", title: "Solid-state lithium metal batteries with garnet-type electrolytes", year: 2023, label: "CORE_RELEVANT" },
        { id: "p005", title: "Thermal management strategies for lithium-ion battery packs", year: 2023, label: "RELATED_RELEVANT" },
        { id: "p008", title: "Operando X-ray tomography of lithium dendrite formation", year: 2024, label: "CORE_RELEVANT" },
        { id: "p014", title: "Interface engineering for stable solid-liquid electrolyte junctions", year: 2024, label: "CORE_RELEVANT" },
      ],
    },
    {
      person_id: "ac003",
      symbol: "ER",
      name: "Elena Rodriguez",
      atomic_number: 3,
      category: "collab",
      category_label: "Collaborators",
      institution: "Imperial College London",
      country: "United Kingdom",
      orcid: "0000-0003-3456-7890",
      core_count: 2,
      related_count: 2,
      papers: [
        { id: "p002", title: "Dendrite suppression strategies in lithium metal batteries", year: 2023, label: "CORE_RELEVANT" },
        { id: "p006", title: "Sodium-ion batteries: Materials, mechanisms, and prospects", year: 2023, label: "ADJACENT" },
        { id: "p011", title: "Quantum chemistry calculations for Li+ solvation", year: 2023, label: "ADJACENT" },
        { id: "p014", title: "Interface engineering for stable solid-liquid electrolyte junctions", year: 2024, label: "CORE_RELEVANT" },
      ],
    },
    {
      person_id: "ac004",
      symbol: "YT",
      name: "Yuki Tanaka",
      atomic_number: 4,
      category: "collab",
      category_label: "Collaborators",
      institution: "NIMS",
      country: "Japan",
      orcid: "0000-0004-4567-8901",
      core_count: 1,
      related_count: 3,
      papers: [
        { id: "p001", title: "Solid-state lithium metal batteries with garnet-type electrolytes", year: 2023, label: "CORE_RELEVANT" },
        { id: "p004", title: "Fast-charging lithium-ion batteries", year: 2022, label: "RELATED_RELEVANT" },
        { id: "p009", title: "Self-healing polymer electrolytes", year: 2023, label: "RELATED_RELEVANT" },
        { id: "p012", title: "EIS for battery state-of-health estimation", year: 2024, label: "RELATED_RELEVANT" },
        { id: "p014", title: "Interface engineering for stable solid-liquid electrolyte junctions", year: 2024, label: "CORE_RELEVANT" },
      ],
    },
    {
      person_id: "ac005",
      symbol: "JL",
      name: "James Liu",
      atomic_number: 5,
      category: "postdoc",
      category_label: "Postdoctoral Researchers",
      institution: "Argonne National Laboratory",
      country: "United States",
      orcid: null,
      core_count: 2,
      related_count: 1,
      papers: [
        { id: "p002", title: "Dendrite suppression strategies in lithium metal batteries", year: 2023, label: "CORE_RELEVANT" },
        { id: "p006", title: "Sodium-ion batteries: Materials, mechanisms, and prospects", year: 2023, label: "ADJACENT" },
        { id: "p015", title: "Anode-free lithium metal batteries: Fundamentals and prospects", year: 2023, label: "CORE_RELEVANT" },
      ],
    },
  ],
};

// ─── Sankey ───────────────────────────────────────────────────────────────────

export const MOCK_SANKEY: SankeyPayload = {
  nodes: [
    // Institutions
    { id: "i001", name: "University of Toronto", layer: "institution" },
    { id: "i002", name: "ETH Zurich", layer: "institution" },
    { id: "i003", name: "Imperial College London", layer: "institution" },
    { id: "i006", name: "NIMS", layer: "institution" },
    { id: "i004", name: "Argonne National Lab", layer: "institution" },
    // Topics
    { id: "t001", name: "Solid-state Electrolytes", layer: "topic" },
    { id: "t002", name: "Lithium Metal Anodes", layer: "topic" },
    { id: "t003", name: "Dendrite Suppression", layer: "topic" },
    { id: "t007", name: "ML for Batteries", layer: "topic" },
    { id: "t010", name: "Electrode Materials", layer: "topic" },
    { id: "t005", name: "Fast Charging", layer: "topic" },
    // Labels
    { id: "CORE_RELEVANT", name: "Core Relevant", layer: "label" },
    { id: "RELATED_RELEVANT", name: "Related Relevant", layer: "label" },
    { id: "ADJACENT", name: "Adjacent", layer: "label" },
    { id: "UNCERTAIN", name: "Uncertain", layer: "label" },
  ],
  links: [
    // Institution → Topic
    { source: "i001", target: "t001", value: 4 },
    { source: "i001", target: "t002", value: 3 },
    { source: "i001", target: "t007", value: 2 },
    { source: "i001", target: "t010", value: 1 },
    { source: "i002", target: "t001", value: 3 },
    { source: "i002", target: "t003", value: 2 },
    { source: "i003", target: "t003", value: 2 },
    { source: "i003", target: "t002", value: 1 },
    { source: "i006", target: "t001", value: 2 },
    { source: "i006", target: "t005", value: 2 },
    { source: "i004", target: "t002", value: 2 },
    { source: "i004", target: "t010", value: 1 },
    // Topic → Label
    { source: "t001", target: "CORE_RELEVANT", value: 6 },
    { source: "t001", target: "RELATED_RELEVANT", value: 2 },
    { source: "t002", target: "CORE_RELEVANT", value: 4 },
    { source: "t002", target: "RELATED_RELEVANT", value: 1 },
    { source: "t003", target: "CORE_RELEVANT", value: 3 },
    { source: "t007", target: "CORE_RELEVANT", value: 2 },
    { source: "t007", target: "RELATED_RELEVANT", value: 1 },
    { source: "t010", target: "CORE_RELEVANT", value: 1 },
    { source: "t010", target: "UNCERTAIN", value: 1 },
    { source: "t005", target: "RELATED_RELEVANT", value: 2 },
  ],
};

// ─── Timeline ─────────────────────────────────────────────────────────────────

export const MOCK_TIMELINE_BY_TOPIC: TimelinePayload = {
  by: "topic",
  years: [2020, 2021, 2022, 2023, 2024],
  series: [
    { name: "Solid-state Electrolytes", data: [[2020, 2], [2021, 3], [2022, 4], [2023, 6], [2024, 5]] },
    { name: "Lithium Metal Anodes",     data: [[2020, 1], [2021, 2], [2022, 3], [2023, 5], [2024, 4]] },
    { name: "Dendrite Suppression",     data: [[2020, 1], [2021, 1], [2022, 2], [2023, 4], [2024, 3]] },
    { name: "ML for Batteries",         data: [[2020, 0], [2021, 1], [2022, 2], [2023, 3], [2024, 5]] },
    { name: "Fast Charging",            data: [[2020, 2], [2021, 2], [2022, 3], [2023, 3], [2024, 2]] },
    { name: "Electrode Materials",      data: [[2020, 3], [2021, 3], [2022, 4], [2023, 3], [2024, 2]] },
  ],
};

export const MOCK_TIMELINE_BY_LABEL: TimelinePayload = {
  by: "label",
  years: [2020, 2021, 2022, 2023, 2024],
  series: [
    { name: "CORE_RELEVANT",    data: [[2020, 3], [2021, 4], [2022, 5], [2023, 7], [2024, 6]] },
    { name: "RELATED_RELEVANT", data: [[2020, 2], [2021, 3], [2022, 4], [2023, 4], [2024, 3]] },
    { name: "ADJACENT",         data: [[2020, 1], [2021, 2], [2022, 2], [2023, 3], [2024, 2]] },
    { name: "UNCERTAIN",        data: [[2020, 1], [2021, 1], [2022, 1], [2023, 2], [2024, 1]] },
    { name: "EXCLUDE",          data: [[2020, 2], [2021, 2], [2022, 3], [2023, 2], [2024, 1]] },
  ],
};

// ─── Network ──────────────────────────────────────────────────────────────────

export const MOCK_COAUTHOR_NETWORK: NetworkPayload = {
  nodes: [
    { id: "ac001", label: "Sarah Chen", is_ac_member: true, institution: "University of Toronto", paper_count: 5 },
    { id: "ac002", label: "Michael Schmidt", is_ac_member: true, institution: "ETH Zurich", paper_count: 4 },
    { id: "ac003", label: "Elena Rodriguez", is_ac_member: true, institution: "Imperial College London", paper_count: 4 },
    { id: "ac004", label: "Yuki Tanaka", is_ac_member: true, institution: "NIMS", paper_count: 5 },
    { id: "ac005", label: "James Liu", is_ac_member: true, institution: "Argonne National Laboratory", paper_count: 3 },
    { id: "ext001", label: "Wei Zhang", is_ac_member: false, institution: "Stanford University", paper_count: 2 },
    { id: "ext002", label: "Priya Sharma", is_ac_member: false, institution: "Carnegie Mellon University", paper_count: 2 },
    { id: "ext003", label: "Lars Eriksson", is_ac_member: false, institution: "Uppsala University", paper_count: 1 },
    { id: "ext004", label: "Hana Kimura", is_ac_member: false, institution: "Toyota Central R&D", paper_count: 1 },
    { id: "ext005", label: "Aiko Nakamura", is_ac_member: false, institution: "Kyoto University", paper_count: 1 },
    { id: "ext006", label: "Carlos Mendes", is_ac_member: false, institution: "University of São Paulo", paper_count: 2 },
    { id: "ext007", label: "Thomas Müller", is_ac_member: false, institution: "Max Planck Institute", paper_count: 1 },
  ],
  edges: [
    { source: "ac001", target: "ac002", weight: 2, papers: ["p001"],        normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: true  },
    { source: "ac001", target: "ac004", weight: 2, papers: ["p001","p012"], normalized_weight: 0.4,    involves_ac: true,  is_ac_ac: true  },
    { source: "ac001", target: "ext001", weight: 2, papers: ["p003","p007"],normalized_weight: 1.0,    involves_ac: true,  is_ac_ac: false },
    { source: "ac001", target: "ext002", weight: 1, papers: ["p003"],       normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: false },
    { source: "ac001", target: "ac005", weight: 1, papers: ["p015"],        normalized_weight: 0.3333, involves_ac: true,  is_ac_ac: true  },
    { source: "ac002", target: "ac003", weight: 1, papers: ["p014"],        normalized_weight: 0.25,   involves_ac: true,  is_ac_ac: true  },
    { source: "ac002", target: "ac004", weight: 2, papers: ["p001","p014"], normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: true  },
    { source: "ac002", target: "ext003", weight: 1, papers: ["p008"],       normalized_weight: 1.0,    involves_ac: true,  is_ac_ac: false },
    { source: "ac002", target: "ext006", weight: 1, papers: ["p005"],       normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: false },
    { source: "ac003", target: "ac004", weight: 1, papers: ["p014"],        normalized_weight: 0.25,   involves_ac: true,  is_ac_ac: true  },
    { source: "ac003", target: "ac005", weight: 2, papers: ["p002","p006"], normalized_weight: 0.6667, involves_ac: true,  is_ac_ac: true  },
    { source: "ac003", target: "ext007", weight: 1, papers: ["p011"],       normalized_weight: 1.0,    involves_ac: true,  is_ac_ac: false },
    { source: "ac003", target: "ext002", weight: 1, papers: ["p006"],       normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: false },
    { source: "ac004", target: "ext005", weight: 1, papers: ["p009"],       normalized_weight: 1.0,    involves_ac: true,  is_ac_ac: false },
    { source: "ac004", target: "ext004", weight: 1, papers: ["p004"],       normalized_weight: 1.0,    involves_ac: true,  is_ac_ac: false },
    { source: "ac005", target: "ext002", weight: 1, papers: ["p010"],       normalized_weight: 0.5,    involves_ac: true,  is_ac_ac: false },
  ],
};

// ─── Institution Network ──────────────────────────────────────────────────────

export const MOCK_INSTITUTION_NETWORK: InstitutionNetworkPayload = {
  nodes: [
    { id: "i001", label: "University of Toronto", is_partner: true, country: "Canada", paper_count: 5 },
    { id: "i002", label: "ETH Zurich", is_partner: true, country: "Switzerland", paper_count: 4 },
    { id: "i003", label: "Imperial College London", is_partner: true, country: "United Kingdom", paper_count: 4 },
    { id: "i006", label: "NIMS", is_partner: true, country: "Japan", paper_count: 5 },
    { id: "i004", label: "Argonne National Laboratory", is_partner: false, country: "United States", paper_count: 3 },
    { id: "i005", label: "Stanford University", is_partner: false, country: "United States", paper_count: 2 },
    { id: "i007", label: "Carnegie Mellon University", is_partner: false, country: "United States", paper_count: 2 },
    { id: "i008", label: "Uppsala University", is_partner: false, country: "Sweden", paper_count: 1 },
    { id: "i009", label: "Kyoto University", is_partner: false, country: "Japan", paper_count: 1 },
    { id: "i010", label: "Toyota Central R&D", is_partner: false, country: "Japan", paper_count: 1 },
  ],
  edges: [
    { source: "i001", target: "i002", weight: 2, papers: ["p001"],        normalized_weight: 0.5,    involves_partner: true  },
    { source: "i001", target: "i006", weight: 2, papers: ["p001","p012"], normalized_weight: 0.4,    involves_partner: true  },
    { source: "i001", target: "i005", weight: 2, papers: ["p003","p007"], normalized_weight: 1.0,    involves_partner: true  },
    { source: "i001", target: "i004", weight: 1, papers: ["p015"],        normalized_weight: 0.3333, involves_partner: true  },
    { source: "i002", target: "i003", weight: 2, papers: ["p014"],        normalized_weight: 0.5,    involves_partner: true  },
    { source: "i002", target: "i006", weight: 2, papers: ["p001","p014"], normalized_weight: 0.5,    involves_partner: true  },
    { source: "i002", target: "i008", weight: 1, papers: ["p008"],        normalized_weight: 1.0,    involves_partner: true  },
    { source: "i003", target: "i004", weight: 2, papers: ["p002","p006"], normalized_weight: 0.6667, involves_partner: true  },
    { source: "i003", target: "i006", weight: 1, papers: ["p014"],        normalized_weight: 0.25,   involves_partner: true  },
    { source: "i006", target: "i009", weight: 1, papers: ["p009"],        normalized_weight: 1.0,    involves_partner: true  },
    { source: "i006", target: "i010", weight: 1, papers: ["p004"],        normalized_weight: 1.0,    involves_partner: true  },
  ],
};

// ─── Multi-Graph ──────────────────────────────────────────────────────────────

// Full corpus — papers span 2021-2025 so time filtering produces visible changes
const MG_ALL_NODES: MultiGraphPayload["nodes"] = [
  // ── Authors ──────────────────────────────────────────────────────────────
  { id: "ac001", type: "author", label: "Sarah Chen",       group: "University of Toronto",  metadata: { is_ac: true,  paper_count: 6 } },
  { id: "ac002", type: "author", label: "Michael Schmidt",  group: "ETH Zurich",              metadata: { is_ac: true,  paper_count: 6 } },
  { id: "ac003", type: "author", label: "Elena Rodriguez",  group: "Imperial College London", metadata: { is_ac: true,  paper_count: 5 } },
  { id: "ac004", type: "author", label: "Yuki Tanaka",      group: "NIMS",                    metadata: { is_ac: true,  paper_count: 5 } },
  { id: "ac005", type: "author", label: "James Liu",        group: "Other",                   metadata: { is_ac: true,  paper_count: 4 } },
  { id: "ext001", type: "author", label: "Wei Zhang",       group: "Other",                   metadata: { is_ac: false, paper_count: 3 } },
  { id: "ext002", type: "author", label: "Maria Oliveira",  group: "Other",                   metadata: { is_ac: false, paper_count: 2 } },
  { id: "ext003", type: "author", label: "Lars Eriksson",   group: "Other",                   metadata: { is_ac: false, paper_count: 2 } },
  // ── Institutions ─────────────────────────────────────────────────────────
  { id: "i001", type: "institution", label: "University of Toronto",  group: "University of Toronto",  metadata: { is_partner: true,  country: "Canada" } },
  { id: "i002", type: "institution", label: "ETH Zurich",             group: "ETH Zurich",             metadata: { is_partner: true,  country: "Switzerland" } },
  { id: "i003", type: "institution", label: "Imperial College London",group: "Imperial College London",metadata: { is_partner: true,  country: "UK" } },
  { id: "i004", type: "institution", label: "NIMS",                   group: "NIMS",                   metadata: { is_partner: true,  country: "Japan" } },
  { id: "i005", type: "institution", label: "Stanford University",    group: "Other",                   metadata: { is_partner: false, country: "USA" } },
  { id: "i006", type: "institution", label: "Uppsala University",     group: "Other",                   metadata: { is_partner: false, country: "Sweden" } },
  // ── Papers — each has `year` in metadata ─────────────────────────────────
  { id: "p001", type: "paper", label: "Solid-state Li metal batteries (garnet)",   group: "University of Toronto",  metadata: { year: 2021, label: "CORE_RELEVANT" } },
  { id: "p004", type: "paper", label: "Electrolyte design principles for Li-S",    group: "ETH Zurich",             metadata: { year: 2021, label: "CORE_RELEVANT" } },
  { id: "p012", type: "paper", label: "Multi-scale battery modeling (continuum)",  group: "NIMS",                   metadata: { year: 2021, label: "RELATED_RELEVANT" } },
  { id: "p005", type: "paper", label: "Anode interface stability in solid cells",  group: "University of Toronto",  metadata: { year: 2022, label: "CORE_RELEVANT" } },
  { id: "p006", type: "paper", label: "Cathode degradation mechanisms at 4V",      group: "NIMS",                   metadata: { year: 2022, label: "RELATED_RELEVANT" } },
  { id: "p002", type: "paper", label: "Dendrite suppression in garnet SE",         group: "Imperial College London",metadata: { year: 2022, label: "CORE_RELEVANT" } },
  { id: "p003", type: "paper", label: "ML-accelerated electrolyte discovery",      group: "University of Toronto",  metadata: { year: 2023, label: "CORE_RELEVANT" } },
  { id: "p007", type: "paper", label: "Fast-charging protocols for Li metal",      group: "Imperial College London",metadata: { year: 2023, label: "CORE_RELEVANT" } },
  { id: "p013", type: "paper", label: "Polymer electrolyte membranes: a review",   group: "Other",                  metadata: { year: 2023, label: "RELATED_RELEVANT" } },
  { id: "p008", type: "paper", label: "Operando X-ray tomography of anodes",       group: "ETH Zurich",             metadata: { year: 2024, label: "CORE_RELEVANT" } },
  { id: "p009", type: "paper", label: "AI-driven materials discovery platform",    group: "University of Toronto",  metadata: { year: 2024, label: "CORE_RELEVANT" } },
  { id: "p014", type: "paper", label: "Interface engineering solid-liquid hybrid", group: "ETH Zurich",             metadata: { year: 2024, label: "CORE_RELEVANT" } },
  { id: "p010", type: "paper", label: "Sodium-ion battery anodes: recent advances",group: "Imperial College London",metadata: { year: 2025, label: "CORE_RELEVANT" } },
  { id: "p011", type: "paper", label: "Composite electrolyte synthesis routes",    group: "NIMS",                   metadata: { year: 2025, label: "CORE_RELEVANT" } },
  { id: "p015", type: "paper", label: "Fluoride electrolytes for high-voltage cells", group: "Other",               metadata: { year: 2025, label: "RELATED_RELEVANT" } },
  // ── Topics ───────────────────────────────────────────────────────────────
  { id: "t001", type: "topic", label: "Solid-state Electrolytes", group: null, metadata: { is_core: true } },
  { id: "t002", type: "topic", label: "Lithium Metal Anodes",     group: null, metadata: { is_core: true } },
  { id: "t003", type: "topic", label: "Dendrite Suppression",     group: null, metadata: { is_core: true } },
  { id: "t004", type: "topic", label: "Fast Charging",            group: null, metadata: { is_core: false } },
  { id: "t007", type: "topic", label: "ML for Batteries",         group: null, metadata: { is_core: true } },
  { id: "t008", type: "topic", label: "Sodium-ion Batteries",     group: null, metadata: { is_core: false } },
  { id: "t009", type: "topic", label: "Multi-scale Modeling",     group: null, metadata: { is_core: false } },
  { id: "t010", type: "topic", label: "Electrode Degradation",    group: null, metadata: { is_core: false } },
  // ── Methods ──────────────────────────────────────────────────────────────
  { id: "m001", type: "method", label: "X-ray Tomography",     group: null, metadata: {} },
  { id: "m002", type: "method", label: "Graph Neural Networks",group: null, metadata: {} },
  { id: "m003", type: "method", label: "DFT Simulation",       group: null, metadata: {} },
  { id: "m004", type: "method", label: "Continuum Modeling",   group: null, metadata: {} },
];

const MG_ALL_EDGES: MultiGraphPayload["edges"] = [
  // authored (paper year drives author visibility)
  { source: "ac001", target: "p001", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p001", type: "authored", weight: 1, metadata: {} },
  { source: "ac004", target: "p001", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p004", type: "authored", weight: 1, metadata: {} },
  { source: "ac004", target: "p012", type: "authored", weight: 1, metadata: {} },
  { source: "ac001", target: "p005", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p005", type: "authored", weight: 1, metadata: {} },
  { source: "ac004", target: "p006", type: "authored", weight: 1, metadata: {} },
  { source: "ac005", target: "p006", type: "authored", weight: 1, metadata: {} },
  { source: "ac003", target: "p002", type: "authored", weight: 1, metadata: {} },
  { source: "ac005", target: "p002", type: "authored", weight: 1, metadata: {} },
  { source: "ac001", target: "p003", type: "authored", weight: 1, metadata: {} },
  { source: "ext001", target: "p003", type: "authored", weight: 1, metadata: {} },
  { source: "ac003", target: "p007", type: "authored", weight: 1, metadata: {} },
  { source: "ext002", target: "p007", type: "authored", weight: 1, metadata: {} },
  { source: "ext001", target: "p013", type: "authored", weight: 1, metadata: {} },
  { source: "ac003", target: "p013", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p008", type: "authored", weight: 1, metadata: {} },
  { source: "ac001", target: "p009", type: "authored", weight: 1, metadata: {} },
  { source: "ac005", target: "p009", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p014", type: "authored", weight: 1, metadata: {} },
  { source: "ac003", target: "p014", type: "authored", weight: 1, metadata: {} },
  { source: "ac004", target: "p014", type: "authored", weight: 1, metadata: {} },
  { source: "ac003", target: "p010", type: "authored", weight: 1, metadata: {} },
  { source: "ext003", target: "p010", type: "authored", weight: 1, metadata: {} },
  { source: "ac002", target: "p011", type: "authored", weight: 1, metadata: {} },
  { source: "ac004", target: "p011", type: "authored", weight: 1, metadata: {} },
  { source: "ext003", target: "p015", type: "authored", weight: 1, metadata: {} },
  { source: "ext001", target: "p015", type: "authored", weight: 1, metadata: {} },
  // affiliated_with (always present — institution is permanent)
  { source: "ac001", target: "i001", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ac002", target: "i002", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ac003", target: "i003", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ac004", target: "i004", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ac005", target: "i005", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ext001", target: "i005", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ext002", target: "i003", type: "affiliated_with", weight: 1, metadata: {} },
  { source: "ext003", target: "i006", type: "affiliated_with", weight: 1, metadata: {} },
  // cites
  { source: "p005", target: "p001", type: "cites", weight: 1, metadata: {} },
  { source: "p002", target: "p001", type: "cites", weight: 1, metadata: {} },
  { source: "p003", target: "p001", type: "cites", weight: 1, metadata: {} },
  { source: "p003", target: "p004", type: "cites", weight: 1, metadata: {} },
  { source: "p007", target: "p002", type: "cites", weight: 1, metadata: {} },
  { source: "p007", target: "p005", type: "cites", weight: 1, metadata: {} },
  { source: "p008", target: "p004", type: "cites", weight: 1, metadata: {} },
  { source: "p008", target: "p005", type: "cites", weight: 1, metadata: {} },
  { source: "p009", target: "p003", type: "cites", weight: 1, metadata: {} },
  { source: "p014", target: "p001", type: "cites", weight: 1, metadata: {} },
  { source: "p014", target: "p002", type: "cites", weight: 1, metadata: {} },
  { source: "p014", target: "p008", type: "cites", weight: 1, metadata: {} },
  { source: "p010", target: "p002", type: "cites", weight: 1, metadata: {} },
  { source: "p011", target: "p004", type: "cites", weight: 1, metadata: {} },
  { source: "p011", target: "p014", type: "cites", weight: 1, metadata: {} },
  { source: "p015", target: "p003", type: "cites", weight: 1, metadata: {} },
  { source: "p015", target: "p013", type: "cites", weight: 1, metadata: {} },
  // covers_topic
  { source: "p001", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p001", target: "t002", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p004", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p012", target: "t009", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p005", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p005", target: "t002", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p006", target: "t010", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p002", target: "t003", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p002", target: "t002", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p003", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p003", target: "t007", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p007", target: "t003", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p007", target: "t004", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p013", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p008", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p008", target: "t003", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p009", target: "t007", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p009", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p014", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p014", target: "t002", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p010", target: "t008", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p011", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p015", target: "t001", type: "covers_topic", weight: 1, metadata: {} },
  { source: "p015", target: "t007", type: "covers_topic", weight: 1, metadata: {} },
  // uses_method
  { source: "p012", target: "m004", type: "uses_method", weight: 1, metadata: {} },
  { source: "p003", target: "m002", type: "uses_method", weight: 1, metadata: {} },
  { source: "p008", target: "m001", type: "uses_method", weight: 1, metadata: {} },
  { source: "p009", target: "m002", type: "uses_method", weight: 1, metadata: {} },
  { source: "p011", target: "m003", type: "uses_method", weight: 1, metadata: {} },
  { source: "p004", target: "m003", type: "uses_method", weight: 1, metadata: {} },
  { source: "p014", target: "m001", type: "uses_method", weight: 1, metadata: {} },
  { source: "p015", target: "m002", type: "uses_method", weight: 1, metadata: {} },
];

const MG_GROUPS: MultiGraphPayload["groups"] = [
  { id: "University of Toronto",  label: "University of Toronto",  color: "#4f86c6", node_count: 0 },
  { id: "ETH Zurich",             label: "ETH Zurich",             color: "#e07b39", node_count: 0 },
  { id: "Imperial College London",label: "Imperial College London",color: "#6ab187", node_count: 0 },
  { id: "NIMS",                   label: "NIMS",                   color: "#c75c5c", node_count: 0 },
  { id: "Other",                  label: "Other / External",       color: "#9ab1c4", node_count: 0 },
];

export function getMockMultiGraph(params: {
  node_types?: string[];
  edge_types?: string[];
  year_from?: number;
  year_to?: number;
}): MultiGraphPayload {
  const yf = params.year_from ?? 2021;
  const yt = params.year_to   ?? 2025;

  // 1. Papers strictly in the year window — these are the temporal anchor
  const visiblePaperIds = new Set(
    MG_ALL_NODES
      .filter(n => n.type === "paper" && (n.metadata.year as number) >= yf && (n.metadata.year as number) <= yt)
      .map(n => n.id)
  );

  // 2. Authors who have at least one paper in the window
  const visibleAuthorIds = new Set(
    MG_ALL_EDGES
      .filter(e => e.type === "authored" && visiblePaperIds.has(e.target))
      .map(e => e.source)
  );

  // 3. Topics covered by visible papers
  const visibleTopicIds = new Set(
    MG_ALL_EDGES
      .filter(e => e.type === "covers_topic" && visiblePaperIds.has(e.source))
      .map(e => e.target)
  );

  // 4. Methods used by visible papers
  const visibleMethodIds = new Set(
    MG_ALL_EDGES
      .filter(e => e.type === "uses_method" && visiblePaperIds.has(e.source))
      .map(e => e.target)
  );

  // 5. Institutions affiliated with visible authors
  const visibleInstitutionIds = new Set(
    MG_ALL_EDGES
      .filter(e => e.type === "affiliated_with" && visibleAuthorIds.has(e.source))
      .map(e => e.target)
  );

  const reachableIds = new Set([
    ...visiblePaperIds,
    ...visibleAuthorIds,
    ...visibleTopicIds,
    ...visibleMethodIds,
    ...visibleInstitutionIds,
  ]);

  // 6. Filter nodes by requested types and reachability
  const activeTypes = params.node_types ?? ["author", "institution", "paper", "topic", "method"];
  const visibleNodes = MG_ALL_NODES.filter(n =>
    activeTypes.includes(n.type) && reachableIds.has(n.id)
  );
  const visibleNodeIds = new Set(visibleNodes.map(n => n.id));

  // 5. Filter edges
  const activeEdgeTypes = params.edge_types ?? ["authored", "affiliated_with", "cites", "covers_topic", "uses_method"];
  const visibleEdges = MG_ALL_EDGES.filter(e =>
    activeEdgeTypes.includes(e.type) &&
    visibleNodeIds.has(e.source) &&
    visibleNodeIds.has(e.target)
  );

  // 6. Recount groups
  const groupCounts: Record<string, number> = {};
  for (const n of visibleNodes) {
    if (n.group) groupCounts[n.group] = (groupCounts[n.group] ?? 0) + 1;
  }
  const groups = MG_GROUPS
    .map(g => ({ ...g, node_count: groupCounts[g.id] ?? 0 }))
    .filter(g => g.node_count > 0);

  // 7. Recalculate paper_count on authors/institutions from visible papers
  const papersByAuthor: Record<string, number> = {};
  for (const e of visibleEdges) {
    if (e.type === "authored") papersByAuthor[e.source] = (papersByAuthor[e.source] ?? 0) + 1;
  }
  const enrichedNodes = visibleNodes.map(n => {
    if (n.type === "author" && papersByAuthor[n.id] != null) {
      return { ...n, metadata: { ...n.metadata, paper_count: papersByAuthor[n.id] } };
    }
    return n;
  });

  return {
    available_node_types: ["author", "institution", "paper", "topic", "method"],
    available_edge_types: ["authored", "affiliated_with", "cites", "covers_topic", "uses_method"],
    available_group_keys: ["institution", "label", "year"],
    groups,
    nodes: enrichedNodes,
    edges: visibleEdges,
  };
}

// Keep static export for backwards compatibility with any other consumers
export const MOCK_MULTI_GRAPH: MultiGraphPayload = getMockMultiGraph({});

// ─── Geographic ───────────────────────────────────────────────────────────────

export const MOCK_GEOGRAPHIC: GeographicReport = {
  total_papers: 15,
  countries: [
    { country: "Canada", paper_count: 5, institution_count: 1, is_partner: true },
    { country: "Switzerland", paper_count: 4, institution_count: 1, is_partner: true },
    { country: "United Kingdom", paper_count: 4, institution_count: 1, is_partner: true },
    { country: "Japan", paper_count: 7, institution_count: 3, is_partner: true },
    { country: "United States", paper_count: 5, institution_count: 3, is_partner: false },
    { country: "Sweden", paper_count: 1, institution_count: 1, is_partner: false },
    { country: "Germany", paper_count: 1, institution_count: 1, is_partner: false },
    { country: "Brazil", paper_count: 2, institution_count: 1, is_partner: false },
  ],
  arcs: [
    { from: "Canada", to: "Switzerland", weight: 2 },
    { from: "Canada", to: "Japan", weight: 2 },
    { from: "Canada", to: "United States", weight: 3 },
    { from: "Switzerland", to: "United Kingdom", weight: 2 },
    { from: "Switzerland", to: "Japan", weight: 2 },
    { from: "Switzerland", to: "Sweden", weight: 1 },
    { from: "United Kingdom", to: "Japan", weight: 1 },
    { from: "United Kingdom", to: "United States", weight: 2 },
    { from: "Japan", to: "United States", weight: 1 },
  ],
  institutions: [
    { id: "i001", name: "University of Toronto", country: "Canada", is_partner: true, paper_count: 5 },
    { id: "i002", name: "ETH Zurich", country: "Switzerland", is_partner: true, paper_count: 4 },
    { id: "i003", name: "Imperial College London", country: "United Kingdom", is_partner: true, paper_count: 4 },
    { id: "i006", name: "NIMS", country: "Japan", is_partner: true, paper_count: 5 },
    { id: "i004", name: "Argonne National Laboratory", country: "United States", is_partner: false, paper_count: 3 },
    { id: "i005", name: "Stanford University", country: "United States", is_partner: false, paper_count: 2 },
    { id: "i007", name: "Carnegie Mellon University", country: "United States", is_partner: false, paper_count: 2 },
    { id: "i008", name: "Uppsala University", country: "Sweden", is_partner: false, paper_count: 1 },
    { id: "i009", name: "Kyoto University", country: "Japan", is_partner: false, paper_count: 1 },
    { id: "i010", name: "Toyota Central R&D", country: "Japan", is_partner: false, paper_count: 1 },
    { id: "i011", name: "Max Planck Institute", country: "Germany", is_partner: false, paper_count: 1 },
    { id: "i012", name: "University of São Paulo", country: "Brazil", is_partner: false, paper_count: 2 },
  ],
};

// ─── Impact Report ────────────────────────────────────────────────────────────

export const MOCK_IMPACT: ImpactReport = {
  window_from: 2020,
  window_to: 2024,
  yoy_attributed: {
    name: "Attributed Papers",
    points: [
      { year: 2020, value: 8 },
      { year: 2021, value: 11 },
      { year: 2022, value: 14 },
      { year: 2023, value: 19 },
      { year: 2024, value: 22 },
    ],
  },
  yoy_by_label: [
    {
      name: "CORE_RELEVANT",
      points: [
        { year: 2020, value: 3 }, { year: 2021, value: 4 }, { year: 2022, value: 5 },
        { year: 2023, value: 7 }, { year: 2024, value: 9 },
      ],
    },
    {
      name: "RELATED_RELEVANT",
      points: [
        { year: 2020, value: 2 }, { year: 2021, value: 3 }, { year: 2022, value: 4 },
        { year: 2023, value: 6 }, { year: 2024, value: 7 },
      ],
    },
    {
      name: "ADJACENT",
      points: [
        { year: 2020, value: 2 }, { year: 2021, value: 2 }, { year: 2022, value: 3 },
        { year: 2023, value: 4 }, { year: 2024, value: 4 },
      ],
    },
  ],
  citation_impact: {
    name: "Citation Count",
    points: [
      { year: 2020, value: 42 },
      { year: 2021, value: 78 },
      { year: 2022, value: 134 },
      { year: 2023, value: 201 },
      { year: 2024, value: 289 },
    ],
  },
  emerging_institutions: [
    { entity_type: "institution", id: "i002", label: "ETH Zurich", first_year: 2022, paper_count: 4, is_partner: true },
    { entity_type: "institution", id: "i005", label: "Stanford University", first_year: 2022, paper_count: 2, is_partner: false },
    { entity_type: "institution", id: "i008", label: "Uppsala University", first_year: 2024, paper_count: 1, is_partner: false },
  ],
  emerging_authors: [
    { entity_type: "author", id: "ac001", label: "Sarah Chen", first_year: 2020, paper_count: 5 },
    { entity_type: "author", id: "ext001", label: "Wei Zhang", first_year: 2022, paper_count: 2 },
    { entity_type: "author", id: "ext003", label: "Lars Eriksson", first_year: 2024, paper_count: 1 },
  ],
  top_growing_themes: [
    { topic_id: "t007", name: "ML for Batteries", value_now: 5, value_then: 1, delta_pct: 400 },
    { topic_id: "t001", name: "Solid-state Electrolytes", value_now: 6, value_then: 2, delta_pct: 200 },
    { topic_id: "t003", name: "Dendrite Suppression", value_now: 4, value_then: 1, delta_pct: 300 },
    { topic_id: "t002", name: "Lithium Metal Anodes", value_now: 5, value_then: 3, delta_pct: 67 },
    { topic_id: "t009", name: "Sodium-ion Batteries", value_now: 2, value_then: 0, delta_pct: "new" },
  ],
};

// ─── Drift Report ─────────────────────────────────────────────────────────────

export const MOCK_DRIFT: DriftReport = {
  drift_threshold: 0.75,
  per_year: [
    {
      year: 2021,
      total_papers: 11,
      top_topics: [
        { topic_id: "t010", name: "Electrode Materials", share: 0.38, paper_count: 4 },
        { topic_id: "t001", name: "Solid-state Electrolytes", share: 0.27, paper_count: 3 },
        { topic_id: "t005", name: "Fast Charging", share: 0.18, paper_count: 2 },
        { topic_id: "t006", name: "Battery Management Systems", share: 0.09, paper_count: 1 },
      ],
    },
    {
      year: 2022,
      total_papers: 14,
      top_topics: [
        { topic_id: "t010", name: "Electrode Materials", share: 0.29, paper_count: 4 },
        { topic_id: "t001", name: "Solid-state Electrolytes", share: 0.29, paper_count: 4 },
        { topic_id: "t003", name: "Dendrite Suppression", share: 0.14, paper_count: 2 },
        { topic_id: "t005", name: "Fast Charging", share: 0.14, paper_count: 2 },
        { topic_id: "t007", name: "ML for Batteries", share: 0.14, paper_count: 2 },
      ],
    },
    {
      year: 2023,
      total_papers: 19,
      top_topics: [
        { topic_id: "t001", name: "Solid-state Electrolytes", share: 0.32, paper_count: 6 },
        { topic_id: "t002", name: "Lithium Metal Anodes", share: 0.26, paper_count: 5 },
        { topic_id: "t003", name: "Dendrite Suppression", share: 0.21, paper_count: 4 },
        { topic_id: "t007", name: "ML for Batteries", share: 0.16, paper_count: 3 },
        { topic_id: "t010", name: "Electrode Materials", share: 0.05, paper_count: 1 },
      ],
    },
    {
      year: 2024,
      total_papers: 22,
      top_topics: [
        { topic_id: "t001", name: "Solid-state Electrolytes", share: 0.30, paper_count: 7 },
        { topic_id: "t007", name: "ML for Batteries", share: 0.23, paper_count: 5 },
        { topic_id: "t002", name: "Lithium Metal Anodes", share: 0.18, paper_count: 4 },
        { topic_id: "t003", name: "Dendrite Suppression", share: 0.14, paper_count: 3 },
        { topic_id: "t004", name: "Battery Safety", share: 0.09, paper_count: 2 },
        { topic_id: "t009", name: "Sodium-ion Batteries", share: 0.05, paper_count: 1 },
      ],
    },
  ],
  drift_events: [
    {
      from_year: 2021,
      to_year: 2022,
      cosine_similarity: 0.81,
      new_topics: ["Dendrite Suppression", "ML for Batteries"],
      faded_topics: [],
    },
    {
      from_year: 2022,
      to_year: 2023,
      cosine_similarity: 0.72,
      new_topics: ["Lithium Metal Anodes"],
      faded_topics: ["Electrode Materials (dominant → minor)"],
    },
    {
      from_year: 2023,
      to_year: 2024,
      cosine_similarity: 0.78,
      new_topics: ["Battery Safety", "Sodium-ion Batteries"],
      faded_topics: [],
    },
  ],
};

// ─── Eval Report ──────────────────────────────────────────────────────────────

export const MOCK_EVAL: EvalReport = {
  n_evaluated: 42,
  k: 5,
  evidence_recall_at_k: 0.84,
  macro_precision: 0.87,
  macro_recall: 0.83,
  macro_f1: 0.85,
  accuracy: 0.88,
  per_label: [
    { label: "CORE_RELEVANT",    precision: 0.94, recall: 0.91, f1: 0.92, support: 18 },
    { label: "RELATED_RELEVANT", precision: 0.86, recall: 0.82, f1: 0.84, support: 11 },
    { label: "ADJACENT",         precision: 0.78, recall: 0.75, f1: 0.76, support: 8 },
    { label: "UNCERTAIN",        precision: 0.80, recall: 0.80, f1: 0.80, support: 3 },
    { label: "EXCLUDE",          precision: 0.97, recall: 0.95, f1: 0.96, support: 20 },
  ],
  confusion: {
    CORE_RELEVANT:    { CORE_RELEVANT: 16, RELATED_RELEVANT: 1, ADJACENT: 0, UNCERTAIN: 1, EXCLUDE: 0 },
    RELATED_RELEVANT: { CORE_RELEVANT: 1,  RELATED_RELEVANT: 9, ADJACENT: 1, UNCERTAIN: 0, EXCLUDE: 0 },
    ADJACENT:         { CORE_RELEVANT: 0,  RELATED_RELEVANT: 1, ADJACENT: 6, UNCERTAIN: 1, EXCLUDE: 0 },
    UNCERTAIN:        { CORE_RELEVANT: 0,  RELATED_RELEVANT: 0, ADJACENT: 0, UNCERTAIN: 3, EXCLUDE: 0 },
    EXCLUDE:          { CORE_RELEVANT: 0,  RELATED_RELEVANT: 0, ADJACENT: 0, UNCERTAIN: 1, EXCLUDE: 19 },
  },
};

// ─── Discovery Queue ──────────────────────────────────────────────────────────

export const MOCK_DISCOVERY: DiscoveryCandidate[] = [
  {
    id: "disc001",
    external_id: "openalex:W4387654321",
    doi: "10.1039/d4ee01234b",
    title: "Superionic conductors for all-solid-state batteries: Challenges and opportunities",
    abstract: "We review the landscape of superionic conductors including sulfide, oxide, and halide electrolytes, with emphasis on processability and electrochemical stability windows.",
    year: 2024,
    venue: "Energy & Environmental Science",
    authors: [{ name: "David Park" }, { name: "Sarah Chen" }, { name: "Mei Lin" }],
    affiliations: ["MIT", "University of Toronto", "Peking University"],
    source: "openalex",
    triggers: [
      { strategy: "citation_expansion", source: "p001", detail: "Cited by core paper p001", weight: 0.8 },
      { strategy: "author_following", source: "ac001", detail: "AC author Sarah Chen", weight: 0.9 },
    ],
    confidence: 0.87,
    auto_eligible: false,
    status: "queued",
    reviewer: null,
    review_notes: null,
    resulting_paper_id: null,
    created_at: "2024-04-14T03:00:00Z",
    reviewed_at: null,
  },
  {
    id: "disc002",
    external_id: "openalex:W4391234567",
    doi: "10.1002/adma.202309876",
    title: "Lithium-oxygen batteries: Recent advances and remaining challenges",
    abstract: "Li-O₂ batteries offer theoretical energy densities 5× higher than Li-ion. This review covers cathode catalyst design, electrolyte stability, and practical cell engineering.",
    year: 2024,
    venue: "Advanced Materials",
    authors: [{ name: "Yuki Tanaka" }, { name: "Kenji Watanabe" }],
    affiliations: ["NIMS", "Waseda University"],
    source: "openalex",
    triggers: [
      { strategy: "author_following", source: "ac004", detail: "AC author Yuki Tanaka (primary)", weight: 0.92 },
      { strategy: "topic_expansion", source: "t002", detail: "Li-O2 related to lithium metal program", weight: 0.65 },
    ],
    confidence: 0.78,
    auto_eligible: true,
    status: "queued",
    reviewer: null,
    review_notes: null,
    resulting_paper_id: null,
    created_at: "2024-04-14T03:01:00Z",
    reviewed_at: null,
  },
  {
    id: "disc003",
    external_id: "openalex:W4401111222",
    doi: "10.1021/acs.nanolett.4c00234",
    title: "In-situ TEM observation of Li plating dynamics in solid electrolytes",
    abstract: "We use aberration-corrected TEM with an electrochemical cell to directly visualize Li plating and stripping at grain boundaries in LLZO solid electrolyte.",
    year: 2024,
    venue: "Nano Letters",
    authors: [{ name: "Michael Schmidt" }, { name: "Lukas Bauer" }, { name: "Elena Rodriguez" }],
    affiliations: ["ETH Zurich", "Paul Scherrer Institute", "Imperial College London"],
    source: "semantic_scholar",
    triggers: [
      { strategy: "author_following", source: "ac002", detail: "AC author Michael Schmidt (primary)", weight: 0.95 },
      { strategy: "author_following", source: "ac003", detail: "AC author Elena Rodriguez", weight: 0.91 },
      { strategy: "citation_expansion", source: "p008", detail: "Same research line as p008", weight: 0.88 },
    ],
    confidence: 0.94,
    auto_eligible: true,
    status: "approved",
    reviewer: "sissi.feng@utoronto.ca",
    review_notes: "Strong match — same operando imaging program",
    resulting_paper_id: null,
    created_at: "2024-04-12T03:00:00Z",
    reviewed_at: "2024-04-13T09:00:00Z",
  },
];

// ─── Report ───────────────────────────────────────────────────────────────────

export const MOCK_REPORT: ReportResult = {
  period_label: "2022–2024",
  generated_at: "2024-04-15T10:00:00Z",
  backend: "mock",
  sections: [
    {
      key: "overview",
      title: "Portfolio Overview",
      prose: "The AC Research attribution corpus contains 15 papers spanning 2022–2024, with 7 classified as Core Relevant, 4 as Related Relevant, 2 as Adjacent, 1 Uncertain, and 1 Excluded. Partner institutions (UofT, ETH Zurich, Imperial College, NIMS) account for 85% of attributed papers. The portfolio shows strong growth in solid-state electrolyte research (+200% since 2020) and emerging presence in ML-for-batteries (5 papers in 2024).",
      metrics: [
        { key: "total_papers", label: "Total Papers", value: 15, source_link: "/papers" },
        { key: "core_relevant", label: "Core Relevant", value: 7, source_link: "/papers?label=CORE_RELEVANT" },
        { key: "partner_coverage", label: "Partner Institution Coverage", value: "85%", source_link: "/people" },
        { key: "avg_confidence", label: "Avg. Classification Confidence", value: "0.79", source_link: "/eval" },
      ],
    },
    {
      key: "topics",
      title: "Topic Landscape",
      prose: "Solid-state electrolytes and lithium metal anodes dominate the core portfolio, collectively representing 58% of core-relevant papers. A notable shift in 2024 is the growth of ML-for-batteries (3 new papers), reflecting the AC's strategic pivot toward data-driven materials discovery. Dendrite suppression research remains strong, anchored by operando characterization work at ETH Zurich.",
      metrics: [
        { key: "top_topic", label: "Leading Topic", value: "Solid-state Electrolytes", source_link: "/timeline" },
        { key: "fastest_growing", label: "Fastest Growing Topic", value: "ML for Batteries (+400%)", source_link: "/impact" },
        { key: "topic_count", label: "Active Topics", value: 8, source_link: "/drift" },
      ],
    },
    {
      key: "people",
      title: "People & Institutions",
      prose: "Five AC members appear in the corpus: Sarah Chen (UofT, 5 papers, PI), Michael Schmidt (ETH Zurich, 4 papers, PI), Elena Rodriguez (Imperial College, 4 papers, collaborator), Yuki Tanaka (NIMS, 5 papers, collaborator), and James Liu (Argonne, 3 papers, postdoc). The network exhibits high clustering between UofT and ETH Zurich, with NIMS serving as a bridge to Japanese collaborators.",
      metrics: [
        { key: "ac_authors", label: "AC Authors in Corpus", value: 5, source_link: "/people" },
        { key: "partner_institutions", label: "Partner Institutions Active", value: 4, source_link: "/geographic" },
        { key: "most_collaborative", label: "Most Collaborative Author", value: "Sarah Chen (5 papers)", source_link: "/network" },
      ],
    },
    {
      key: "gaps",
      title: "Evidence Gaps",
      prose: "3 papers lack full-text evidence, reducing classification confidence. 5 papers have weak graph signals — particularly p010 (UNCERTAIN) and p006 (ADJACENT) which may benefit from human review. The classifier achieves 0.88 accuracy and 0.85 macro-F1 on the held-out evaluation set.",
      metrics: [
        { key: "no_fulltext", label: "Papers Missing Full Text", value: 3, source_link: "/evidence-gaps" },
        { key: "weak_graph", label: "Papers with Weak Graph Coverage", value: 5, source_link: "/evidence-gaps" },
        { key: "needs_review", label: "Papers Queued for Review", value: 4, source_link: "/queue" },
        { key: "classifier_f1", label: "Classifier Macro-F1", value: "0.85", source_link: "/eval" },
      ],
    },
  ],
};

// ─── Missed Paper Groups ──────────────────────────────────────────────────────

export const MOCK_MISSED_GROUPS: MissedPaperGroup[] = [
  {
    key: "low_confidence_adjacent",
    label: "Low-confidence Adjacent papers",
    description: "Adjacent papers that may have been misclassified — author score suggests potential relevance",
    candidate_ids: ["p006", "p011"],
  },
  {
    key: "uncertain_no_fulltext",
    label: "Uncertain papers missing full text",
    description: "UNCERTAIN papers that could not be disambiguated due to missing full-text evidence",
    candidate_ids: ["p010"],
  },
];

// ─── Graph Explanation ────────────────────────────────────────────────────────

export function getMockGraphExplanation(paperId: string): GraphExplanation {
  return {
    paper_id: paperId,
    summary: `This paper is connected to the AC Research network through shared authorship and co-citation patterns. The classification is supported by direct author matches and topic overlap with the core program.`,
    direct_ac_authors: ["Sarah Chen", "Michael Schmidt"],
    second_degree_paths: [],
    citation_signals: [],
    cites_corpus: ["p001", "p007"],
    cited_by_corpus: [],
  };
}

// ── Research Network Growth mock data ────────────────────────────────────────

import type {
  NetworkGrowthPayload,
  TopicStreamPayload,
  InstTopicHeatmapPayload,
  HubScorePayload,
} from "@/types";

export const MOCK_NETWORK_GROWTH: NetworkGrowthPayload = {
  yearly: [
    { year: 2021, papers: 12,  authors: 18,  institutions: 5,  countries: 3,  collaborations: 8  },
    { year: 2022, papers: 19,  authors: 28,  institutions: 7,  countries: 5,  collaborations: 15 },
    { year: 2023, papers: 31,  authors: 48,  institutions: 12, countries: 8,  collaborations: 28 },
    { year: 2024, papers: 44,  authors: 67,  institutions: 18, countries: 13, collaborations: 45 },
    { year: 2025, papers: 28,  authors: 42,  institutions: 11, countries: 9,  collaborations: 31 },
  ],
  cumulative: [
    { year: 2021, papers: 12,  authors: 18,  institutions: 5,  countries: 3,  collaborations: 8   },
    { year: 2022, papers: 31,  authors: 46,  institutions: 12, countries: 8,  collaborations: 23  },
    { year: 2023, papers: 62,  authors: 94,  institutions: 24, countries: 16, collaborations: 51  },
    { year: 2024, papers: 106, authors: 161, institutions: 42, countries: 29, collaborations: 96  },
    { year: 2025, papers: 134, authors: 203, institutions: 53, countries: 38, collaborations: 127 },
  ],
};

const _TOPICS = [
  "Self-Driving Labs",
  "Closed-Loop Exp.",
  "Automation",
  "Materials Discovery",
  "Software Research",
] as const;

// themeRiver format: [year_string, count, topic_name]
export const MOCK_TOPIC_STREAM: TopicStreamPayload = {
  topics: [..._TOPICS],
  data: [
    // 2021
    ["2021", 2,  "Self-Driving Labs"],
    ["2021", 1,  "Closed-Loop Exp."],
    ["2021", 2,  "Automation"],
    ["2021", 5,  "Materials Discovery"],
    ["2021", 0.5,"Software Research"],
    // 2022
    ["2022", 5,  "Self-Driving Labs"],
    ["2022", 3,  "Closed-Loop Exp."],
    ["2022", 4,  "Automation"],
    ["2022", 6,  "Materials Discovery"],
    ["2022", 1,  "Software Research"],
    // 2023
    ["2023", 11, "Self-Driving Labs"],
    ["2023", 8,  "Closed-Loop Exp."],
    ["2023", 7,  "Automation"],
    ["2023", 8,  "Materials Discovery"],
    ["2023", 3,  "Software Research"],
    // 2024
    ["2024", 17, "Self-Driving Labs"],
    ["2024", 14, "Closed-Loop Exp."],
    ["2024", 10, "Automation"],
    ["2024", 12, "Materials Discovery"],
    ["2024", 7,  "Software Research"],
    // 2025
    ["2025", 12, "Self-Driving Labs"],
    ["2025", 9,  "Closed-Loop Exp."],
    ["2025", 6,  "Automation"],
    ["2025", 7,  "Materials Discovery"],
    ["2025", 5,  "Software Research"],
  ],
};

const _INSTS = ["UofT", "ETH Zurich", "Imperial College", "Argonne", "NIMS", "Stanford", "MIT", "Oxford"];

export const MOCK_INST_TOPIC_HEATMAP: InstTopicHeatmapPayload = {
  institutions: _INSTS,
  topics: [..._TOPICS],
  year: null,
  cells: [
    // UofT
    { institution: "UofT",             topic: "Self-Driving Labs",    count: 28 },
    { institution: "UofT",             topic: "Closed-Loop Exp.",     count: 19 },
    { institution: "UofT",             topic: "Automation",           count: 15 },
    { institution: "UofT",             topic: "Materials Discovery",  count: 22 },
    { institution: "UofT",             topic: "Software Research",    count: 12 },
    // ETH Zurich
    { institution: "ETH Zurich",       topic: "Self-Driving Labs",    count: 12 },
    { institution: "ETH Zurich",       topic: "Closed-Loop Exp.",     count: 8  },
    { institution: "ETH Zurich",       topic: "Automation",           count: 6  },
    { institution: "ETH Zurich",       topic: "Materials Discovery",  count: 9  },
    { institution: "ETH Zurich",       topic: "Software Research",    count: 5  },
    // Imperial College
    { institution: "Imperial College", topic: "Self-Driving Labs",    count: 9  },
    { institution: "Imperial College", topic: "Closed-Loop Exp.",     count: 6  },
    { institution: "Imperial College", topic: "Automation",           count: 4  },
    { institution: "Imperial College", topic: "Materials Discovery",  count: 7  },
    { institution: "Imperial College", topic: "Software Research",    count: 3  },
    // Argonne
    { institution: "Argonne",          topic: "Self-Driving Labs",    count: 6  },
    { institution: "Argonne",          topic: "Closed-Loop Exp.",     count: 5  },
    { institution: "Argonne",          topic: "Automation",           count: 8  },
    { institution: "Argonne",          topic: "Materials Discovery",  count: 14 },
    { institution: "Argonne",          topic: "Software Research",    count: 4  },
    // NIMS
    { institution: "NIMS",             topic: "Self-Driving Labs",    count: 4  },
    { institution: "NIMS",             topic: "Closed-Loop Exp.",     count: 3  },
    { institution: "NIMS",             topic: "Automation",           count: 5  },
    { institution: "NIMS",             topic: "Materials Discovery",  count: 18 },
    { institution: "NIMS",             topic: "Software Research",    count: 2  },
    // Stanford
    { institution: "Stanford",         topic: "Self-Driving Labs",    count: 7  },
    { institution: "Stanford",         topic: "Closed-Loop Exp.",     count: 4  },
    { institution: "Stanford",         topic: "Automation",           count: 3  },
    { institution: "Stanford",         topic: "Materials Discovery",  count: 8  },
    { institution: "Stanford",         topic: "Software Research",    count: 6  },
    // MIT
    { institution: "MIT",              topic: "Self-Driving Labs",    count: 8  },
    { institution: "MIT",              topic: "Closed-Loop Exp.",     count: 5  },
    { institution: "MIT",              topic: "Automation",           count: 5  },
    { institution: "MIT",              topic: "Materials Discovery",  count: 10 },
    { institution: "MIT",              topic: "Software Research",    count: 8  },
    // Oxford
    { institution: "Oxford",           topic: "Self-Driving Labs",    count: 5  },
    { institution: "Oxford",           topic: "Closed-Loop Exp.",     count: 3  },
    { institution: "Oxford",           topic: "Automation",           count: 2  },
    { institution: "Oxford",           topic: "Materials Discovery",  count: 6  },
    { institution: "Oxford",           topic: "Software Research",    count: 3  },
  ],
};

export const MOCK_HUB_SCORE: HubScorePayload = {
  institution: "University of Toronto",
  data: [
    { year: 2021, degree_centrality: 0.24, betweenness_centrality: 0.18, partner_count: 4,  intl_collab_count: 3,  hub_score: 0.22 },
    { year: 2022, degree_centrality: 0.35, betweenness_centrality: 0.28, partner_count: 7,  intl_collab_count: 6,  hub_score: 0.34 },
    { year: 2023, degree_centrality: 0.52, betweenness_centrality: 0.44, partner_count: 13, intl_collab_count: 11, hub_score: 0.50 },
    { year: 2024, degree_centrality: 0.71, betweenness_centrality: 0.63, partner_count: 21, intl_collab_count: 18, hub_score: 0.68 },
    { year: 2025, degree_centrality: 0.78, betweenness_centrality: 0.72, partner_count: 26, intl_collab_count: 22, hub_score: 0.76 },
  ],
};
