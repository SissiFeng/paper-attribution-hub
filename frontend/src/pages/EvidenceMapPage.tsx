import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import {
  buildEvidenceStarModel,
  formatEvidenceType,
  formatPageRange,
  type EvidenceStarItem,
} from "@/lib/evidenceStarMap";
import { getAttributionEvidenceTree, getPaper } from "@/lib/api";
import {
  deriveEvidenceMapFromPaper,
  type EvidenceMapDataset,
} from "@/lib/paperEvidenceTree";
import type {
  AttributionEvidencePath,
  AttributionEvidenceTree,
  AttributionTreeNode,
} from "@/types";

import styles from "./EvidenceMapPage.module.css";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue} title={value}>
        {value}
      </span>
    </div>
  );
}

function ChunkList({ chunkIds }: { chunkIds: string[] }) {
  if (chunkIds.length === 0) return null;
  return (
    <>
      <h3 className={styles.sectionTitle}>Source chunks</h3>
      <div className={styles.chunkList}>
        {chunkIds.map((chunkId) => (
          <code className={styles.chunk} key={chunkId}>
            {chunkId}
          </code>
        ))}
      </div>
    </>
  );
}

function TreeNodeDetails({
  node,
  source,
}: {
  node: AttributionTreeNode;
  source: EvidenceMapDataset["source"];
}) {
  const pageRange = formatPageRange(node.page_start, node.page_end);
  return (
    <>
      {node.summary && <p className={styles.summary}>{node.summary}</p>}
      <div className={styles.metricGrid}>
        <Metric label="Node type" value={formatEvidenceType(node.node_type)} />
        <Metric label="Location" value={pageRange ?? "Not page-bound"} />
        <Metric label="Evidence chunks" value={String(node.source_chunk_ids.length)} />
        <Metric
          label={source === "paper_payload" ? "Signal group" : "Section"}
          value={node.section_type ?? "Paper root"}
        />
      </div>
      <h3 className={styles.sectionTitle}>Evidence path</h3>
      <div className={styles.pathLine}>{node.path.join(" → ")}</div>
      <ChunkList chunkIds={node.source_chunk_ids} />
    </>
  );
}

function EvidencePathDetails({ path }: { path: AttributionEvidencePath }) {
  const pageRange = formatPageRange(path.page_start, path.page_end);
  return (
    <>
      <blockquote className={styles.quote}>{path.quote}</blockquote>
      <div className={styles.pathLine}>{path.path.join(" → ")}</div>
      <div className={styles.metricGrid}>
        <Metric label="Polarity" value={formatEvidenceType(path.polarity)} />
        <Metric label="Centrality" value={formatEvidenceType(path.centrality)} />
        <Metric label="Weight" value={path.weight.toFixed(3)} />
        <Metric label="Raw score" value={path.raw_score.toFixed(3)} />
        <Metric
          label="Confidence"
          value={path.confidence == null ? "Not reported" : `${Math.round(path.confidence * 100)}%`}
        />
        <Metric label="Location" value={pageRange ?? "Not page-bound"} />
        <Metric label="Detector" value={formatEvidenceType(path.detector_type)} />
        <Metric label="Metadata" value={formatEvidenceType(path.metadata_status)} />
      </div>
      <ChunkList chunkIds={path.source_chunk_ids} />
    </>
  );
}

function Inspector({
  selected,
  tree,
  source,
  onSelect,
}: {
  selected: EvidenceStarItem | null;
  tree: AttributionEvidenceTree;
  source: EvidenceMapDataset["source"];
  onSelect: (id: string) => void;
}) {
  const evidenceByWeight = useMemo(
    () =>
      [...tree.evidence_paths].sort(
        (a, b) => Math.abs(b.weight) - Math.abs(a.weight) || a.rank - b.rank
      ),
    [tree.evidence_paths]
  );

  return (
    <aside className={styles.inspector} aria-label="Evidence detail">
      <div className={styles.inspectorHeader}>
        <div className={styles.inspectorKind}>
          {selected
            ? selected.kind === "evidence"
              ? `${selected.evidencePath.polarity} evidence`
              : selected.treeNode.node_type
            : "Map guide"}
        </div>
        <h2 className={styles.inspectorTitle}>
          {selected?.label ?? "Select a star to inspect its evidence"}
        </h2>
      </div>
      <div className={styles.inspectorBody}>
        {tree.evidence_review_recommended && (
          <div className={styles.reviewNotice}>
            <strong>Human evidence review recommended</strong>
            {tree.evidence_review_reasons
              .map((reason) => formatEvidenceType(reason.replace(/^AET_/, "")))
              .join(" · ")}
          </div>
        )}

        {!selected && (
          <p className={styles.guide}>
            The paper sits at the center. Sections and unlocated sources occupy the
            inner orbit; normalized evidence paths occupy the outer orbit. Drag to
            pan, scroll to zoom, and select any star for its provenance.
          </p>
        )}
        {selected?.kind === "tree" && (
          <TreeNodeDetails node={selected.treeNode} source={source} />
        )}
        {selected?.kind === "evidence" && (
          <EvidencePathDetails path={selected.evidencePath} />
        )}

        <h3 className={styles.sectionTitle}>Evidence index</h3>
        <div className={styles.evidenceIndex}>
          {evidenceByWeight.map((path) => {
            const active = selected?.id === path.path_id;
            return (
              <button
                className={styles.evidenceButton}
                key={path.path_id}
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(path.path_id)}
                title={path.quote}
              >
                <span
                  className={`${styles.evidenceDot} ${
                    path.polarity === "positive" ? styles.positive : styles.negative
                  }`}
                />
                <span className={styles.evidenceName}>
                  {formatEvidenceType(path.evidence_type)}
                </span>
                <span className={styles.evidenceWeight}>{path.weight.toFixed(2)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

export default function EvidenceMapPage() {
  const { paperId } = useParams<{ paperId: string }>();
  const [dataset, setDataset] = useState<EvidenceMapDataset | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mapKey, setMapKey] = useState(0);

  const load = useCallback(async () => {
    if (!paperId) {
      setError("The evidence-map route is missing a paper ID.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      let nextDataset: EvidenceMapDataset;
      try {
        nextDataset = {
          source: "server_aet",
          tree: await getAttributionEvidenceTree(paperId),
        };
      } catch {
        const paper = await getPaper(paperId);
        nextDataset = deriveEvidenceMapFromPaper(paper);
      }
      setDataset(nextDataset);
      const nextTree = nextDataset.tree;
      const root = nextTree.nodes.find((node) => node.node_type === "root");
      setSelectedId(root?.node_id ?? null);
    } catch (err) {
      setDataset(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [paperId]);

  useEffect(() => {
    void load();
  }, [load]);

  const tree = dataset?.tree ?? null;
  const source = dataset?.source ?? "server_aet";
  const model = useMemo(
    () => (tree ? buildEvidenceStarModel(tree, selectedId, source) : null),
    [tree, selectedId, source]
  );
  const selected = selectedId && model ? model.byId.get(selectedId) ?? null : null;
  const root = tree?.nodes.find((node) => node.node_type === "root") ?? null;
  const positiveCount =
    tree?.evidence_paths.filter((path) => path.polarity === "positive").length ?? 0;
  const negativeCount =
    tree?.evidence_paths.filter((path) => path.polarity === "negative").length ?? 0;

  const onChartEvent = useMemo(
    () => ({
      click: (params: unknown) => {
        const event = params as {
          dataType?: string;
          data?: { id?: string };
        };
        if (event.dataType === "node" && event.data?.id) {
          setSelectedId(event.data.id);
        }
      },
    }),
    []
  );

  return (
    <div className={styles.page}>
      <Link className={styles.breadcrumb} to="/">
        ← Papers
      </Link>

      {loading && (
        <div className={styles.state} aria-live="polite">
          <div>
            <strong>Deriving evidence constellation…</strong>
            <p>Reading this paper's live classification and evidence signals.</p>
          </div>
        </div>
      )}

      {!loading && error && (
        <div className={styles.state} role="alert">
          <div>
            <strong>Evidence map unavailable</strong>
            <p>{error}</p>
            <p>
              The paper could not be read from the current live API.
            </p>
            <button className={styles.stateButton} type="button" onClick={() => void load()}>
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && tree && model && (
        <>
          <header className={styles.header}>
            <div>
              <div className={styles.eyebrow}>Attribution Evidence Star Map</div>
              <h1 className={styles.title}>{root?.title ?? `Paper ${tree.paper_id}`}</h1>
              <p className={styles.subtitle}>
                {source === "server_aet"
                  ? "A read-only constellation of server-normalized evidence paths, polarity, confidence, and provenance."
                  : "Derived in the browser from this paper's live classification reasons, matches, scores, graph signals, and full-text evidence."}
              </p>
            </div>
            <div className={styles.generation}>
              Generation
              <strong>{tree.generation_id}</strong>
              {tree.tree_version}
            </div>
          </header>

          <div className={styles.summaryStrip}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Source nodes</span>
              <span className={styles.summaryValue}>{tree.nodes.length}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Evidence paths</span>
              <span className={styles.summaryValue}>{tree.evidence_paths.length}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Positive</span>
              <span className={`${styles.summaryValue} ${styles.positive}`}>
                {positiveCount}
              </span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Negative</span>
              <span className={`${styles.summaryValue} ${styles.negative}`}>
                {negativeCount}
              </span>
            </div>
          </div>

          {tree.nodes.length === 0 ? (
            <div className={styles.state}>
              <div>
                <strong>No evidence structure was derived</strong>
                <p>The API returned an empty tree for this paper.</p>
              </div>
            </div>
          ) : (
            <div className={styles.workspace}>
              <section
                className={styles.mapPanel}
                aria-label={
                  source === "paper_payload"
                    ? "Interactive live classification signal map"
                    : "Interactive evidence map"
                }
              >
                <div className={styles.mapToolbar}>
                  <button
                    className={styles.mapButton}
                    type="button"
                    onClick={() => setMapKey((value) => value + 1)}
                  >
                    Reset view
                  </button>
                </div>
                <div className={styles.mapCanvas}>
                  <EChart
                    key={mapKey}
                    option={model.option}
                    notMerge={false}
                    style={{ height: "100%", width: "100%" }}
                    onEvents={onChartEvent}
                  />
                </div>
                <div className={styles.mapFooter}>
                  <div className={styles.legend} aria-label="Star map legend">
                    {(source === "paper_payload"
                      ? [
                          ["Paper root", styles.legendRoot],
                          ["Signal group", styles.legendSource],
                          ["Positive signal", styles.legendPositive],
                          ["Negative signal", styles.legendNegative],
                        ]
                      : [
                          ["Paper root", styles.legendRoot],
                          ["Section", styles.legendSection],
                          ["Unlocated source", styles.legendSource],
                          ["Positive evidence", styles.legendPositive],
                          ["Negative evidence", styles.legendNegative],
                        ]
                    ).map(([label, colorClass]) => (
                      <span className={styles.legendItem} key={label}>
                        <span className={`${styles.legendMark} ${colorClass}`} />
                        {label}
                      </span>
                    ))}
                  </div>
                  <div className={styles.mapHint}>drag to pan · scroll to zoom · click to inspect</div>
                </div>
              </section>
              <Inspector
                selected={selected}
                tree={tree}
                source={source}
                onSelect={setSelectedId}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
