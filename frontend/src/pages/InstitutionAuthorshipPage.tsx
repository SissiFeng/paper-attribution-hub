import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EChart } from "@/components/EChart";
import {
  getInstitutionAuthorshipOptions,
  getInstitutionAuthorshipReport,
  institutionAuthorshipExportUrl,
  tier1AuthorInstitutionMetadataExportUrl,
} from "@/lib/api";
import type {
  InstitutionAuthorshipOptions,
  InstitutionAuthorshipReport,
} from "@/types";
import styles from "./InstitutionAuthorshipPage.module.css";


const DEFAULTS = {
  corpus: "tier1",
  credit_scheme: "lead_balanced",
  author_role: "all",
  affiliation_allocation: "fractional",
  focus_scope: "strict",
  min_affiliation_confidence: "0.8",
  limit: "30",
};

const FALLBACK_SCHEMES = [
  { value: "lead_balanced", label: "First/last balanced" },
  { value: "lead_heavy", label: "First/last heavy" },
  { value: "equal_fractional", label: "Equal fractional" },
  { value: "full_counting", label: "Full counting" },
];

const FALLBACK_AUTHOR_ROLES = [
  {
    value: "all",
    label: "All authors",
    description: "Includes every author in the ordered author list.",
  },
  {
    value: "first",
    label: "First author only",
    description: "Includes only the first-listed author, independent of corresponding-author status.",
  },
  {
    value: "corresponding",
    label: "Corresponding author only",
    description: "Includes only explicitly marked corresponding authors, independent of author order.",
  },
  {
    value: "last",
    label: "Last author only",
    description: "Includes only the last-listed author.",
  },
  {
    value: "middle",
    label: "Middle authors only",
    description: "Includes authors who are neither first-listed nor last-listed.",
  },
];

function compactHash(value: string) {
  return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;
}

function formatCredit(value: number) {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: value < 10 ? 2 : 1,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function motionDuration(duration: number) {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? 0
    : duration;
}

const NETWORK_SHORT_NAMES: Record<string, string> = {
  "Centre National de la Recherche Scientifique": "CNRS",
  "Technical University of Denmark": "DTU",
  "Karlsruhe Institute of Technology": "KIT",
  "Argonne National Laboratory": "Argonne",
  "Lawrence Berkeley National Laboratory": "Berkeley Lab",
  "Commissariat à l'Énergie Atomique et aux Énergies Alternatives": "CEA",
  "University of Toronto": "U of T",
  "University of Washington": "U Washington",
  "University of Liverpool": "U Liverpool",
  "The University of Tokyo": "U Tokyo",
};

function compactInstitutionName(name: string) {
  return NETWORK_SHORT_NAMES[name]
    ?? name
      .replace(/^University of /, "U ")
      .replace(/ National Laboratory$/, " Lab")
      .replace(/ Institute of Technology$/, " Tech");
}

function networkEdgeKey(source: string, target: string) {
  return source < target ? `${source}::${target}` : `${target}::${source}`;
}

export default function InstitutionAuthorshipPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [report, setReport] = useState<InstitutionAuthorshipReport | null>(null);
  const [options, setOptions] = useState<InstitutionAuthorshipOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [searchDraft, setSearchDraft] = useState(searchParams.get("search") ?? "");
  const [networkMode, setNetworkMode] = useState<"spotlight" | "full">("spotlight");
  const query = searchParams.toString();
  const selectedCorpus = searchParams.get("corpus") === "tier1_tier2"
    ? "tier1_tier2"
    : "tier1";
  const selectedCorpusLabel = selectedCorpus === "tier1_tier2"
    ? "Tier 1 + Tier 2"
    : "Tier 1";

  useEffect(() => {
    let active = true;
    setOptions(null);
    getInstitutionAuthorshipOptions(selectedCorpus)
      .then((value) => {
        if (active) setOptions(value);
      })
      .catch(() => {
        if (active) setOptions(null);
      });
    return () => {
      active = false;
    };
  }, [selectedCorpus]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setReport(null);
    getInstitutionAuthorshipReport(new URLSearchParams(query))
      .then((value) => {
        if (active) setReport(value);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load the report.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, retry]);

  useEffect(() => {
    setSearchDraft(searchParams.get("search") ?? "");
  }, [searchParams]);

  const valueFor = (key: keyof typeof DEFAULTS) =>
    searchParams.get(key) ?? DEFAULTS[key];

  const selectedRoleFallback = FALLBACK_AUTHOR_ROLES.find(
    (option) => option.value === valueFor("author_role"),
  ) ?? FALLBACK_AUTHOR_ROLES[0];

  const updateParam = (key: string, value: string, defaultValue?: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === defaultValue) next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const applySearch = (event: FormEvent) => {
    event.preventDefault();
    updateParam("search", searchDraft.trim());
  };

  const resetFilters = () => {
    const next = new URLSearchParams();
    if (selectedCorpus !== DEFAULTS.corpus) next.set("corpus", selectedCorpus);
    setSearchParams(next, { replace: true });
  };

  const topInstitutionsOption = useMemo(() => {
    const rows = [...(report?.institutions.slice(0, 12) ?? [])].reverse();
    return {
      animationDuration: 280,
      tooltip: {
        trigger: "item",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51", fontFamily: "'JetBrains Mono', monospace" },
        formatter: (item: { data: { name: string; value: number; papers: number } }) =>
          `${item.data.name}<br/><strong>${formatCredit(item.data.value)}</strong> weighted credit<br/>${item.data.papers} distinct papers (any author)`,
      },
      grid: { left: 190, right: 42, top: 8, bottom: 24 },
      xAxis: {
        type: "value",
        axisLabel: { color: "#6594B1", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.07)", type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLabel: {
          color: "#213C51",
          fontSize: 10,
          width: 170,
          overflow: "truncate",
        },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 17,
          data: rows.map((row) => ({
            name: row.name,
            value: row.weighted_credit,
            papers: row.paper_count,
            itemStyle: {
              color: row.contributes_to_focus ? "#DDAED3" : "#6594B1",
              borderRadius: [0, 4, 4, 0],
            },
          })),
          label: {
            show: true,
            position: "right",
            color: "#213C51",
            fontSize: 10,
            formatter: (item: { value: number }) => formatCredit(item.value),
          },
        },
      ],
    };
  }, [report]);

  const yearlyOption = useMemo(() => {
    const rows = report?.yearly ?? [];
    return {
      animationDuration: 280,
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51", fontFamily: "'JetBrains Mono', monospace" },
      },
      legend: {
        top: 0,
        right: 0,
        textStyle: { color: "#6594B1", fontSize: 10 },
      },
      grid: { left: 52, right: 18, top: 42, bottom: 32 },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.year),
        axisLabel: { color: "#6594B1", fontSize: 10 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#6594B1", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.07)", type: "dashed" } },
      },
      series: [
        {
          name: "U of T credit",
          type: "line",
          smooth: true,
          symbolSize: 6,
          data: rows.map((row) => row.focus_weighted_credit),
          lineStyle: { color: "#C783B7", width: 2.5 },
          itemStyle: { color: "#C783B7" },
          areaStyle: { color: "rgba(221,174,211,0.18)" },
        },
        {
          name: "Other credit",
          type: "line",
          smooth: true,
          symbolSize: 5,
          data: rows.map((row) => row.other_weighted_credit),
          lineStyle: { color: "#6594B1", width: 2 },
          itemStyle: { color: "#6594B1" },
        },
      ],
    };
  }, [report]);

  const uoftPaperSharePeak = useMemo(() => {
    const rows = report?.yearly ?? [];
    return rows.reduce<(typeof rows)[number] | null>(
      (peak, row) => !peak || row.focus_paper_share_of_corpus > peak.focus_paper_share_of_corpus ? row : peak,
      null,
    );
  }, [report]);

  const uoftPaperShareOption = useMemo(() => {
    const rows = report?.yearly ?? [];
    const percentages = rows.map((row) => Number((row.focus_paper_share_of_corpus * 100).toFixed(2)));
    const overallPercentage = (report?.focus.share_of_corpus_papers ?? 0) * 100;
    const yAxisMaximum = Math.max(
      5,
      Math.ceil((Math.max(overallPercentage, ...percentages, 0) + 0.75) * 2) / 2,
    );
    return {
      animationDuration: motionDuration(360),
      animationEasing: "cubicOut",
      aria: {
        enabled: true,
        description: `University of Toronto share of ${selectedCorpusLabel} papers by year for the current selection.`,
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: "rgba(33,60,81,0.18)" } },
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        extraCssText: "box-shadow: 0 12px 30px rgba(33,60,81,0.12); border-radius: 10px;",
        textStyle: { color: "#213C51", fontFamily: "'JetBrains Mono', monospace" },
        formatter: (items: Array<{ dataIndex: number }>) => {
          const row = rows[items[0]?.dataIndex];
          if (!row) return "";
          return `${row.year}<br/><strong>${formatPercent(row.focus_paper_share_of_corpus)}</strong> of ${selectedCorpusLabel} papers<br/>${row.focus_papers} U of T papers / ${row.corpus_papers} papers in current selection`;
        },
      },
      grid: { left: 54, right: 30, top: 58, bottom: 34 },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.year),
        axisLabel: { color: "#5F7F92", fontSize: 10, margin: 13 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(33,60,81,0.16)" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: yAxisMaximum,
        interval: 1,
        name: "share of papers",
        nameTextStyle: { color: "#7A96A6", fontSize: 9, align: "left", padding: [0, 0, 8, 0] },
        axisLabel: {
          color: "#7A96A6",
          fontSize: 10,
          formatter: (value: number) => `${value}%`,
        },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.065)", type: "dashed" } },
      },
      series: [
        {
          name: "Annual share",
          type: "bar",
          barWidth: 4,
          itemStyle: { color: "#C783B7" },
          data: percentages.map((value, index) => ({
            value,
            itemStyle: {
              color: rows[index]?.focus_papers ? "#C783B7" : "rgba(101,148,177,0.2)",
              borderRadius: [8, 8, 0, 0],
            },
          })),
          label: {
            show: true,
            position: "top",
            distance: 13,
            color: "#7B4F73",
            fontSize: 10,
            fontWeight: 700,
            formatter: (item: { dataIndex: number; value: number }) =>
              rows[item.dataIndex]?.focus_papers ? `${Number(item.value).toFixed(1)}%` : "",
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#7894A6", width: 1, type: "dashed" },
            label: {
              show: true,
              position: "insideEndTop",
              color: "#5F7F92",
              fontSize: 9,
              formatter: `All years ${overallPercentage.toFixed(1)}%`,
            },
            data: [{ yAxis: Number(overallPercentage.toFixed(2)) }],
          },
          z: 2,
        },
        {
          name: "U of T paper count",
          type: "scatter",
          itemStyle: { color: "#DDAED3" },
          data: percentages.map((value, index) => ({
            value,
            focus_papers: rows[index]?.focus_papers ?? 0,
            itemStyle: rows[index]?.focus_papers
              ? {
                  color: "#DDAED3",
                  borderColor: "#FFFFFF",
                  borderWidth: 3,
                  shadowBlur: 12,
                  shadowColor: "rgba(199,131,183,0.28)",
                }
              : {
                  color: "#D8E3E9",
                  borderColor: "#FFFFFF",
                  borderWidth: 2,
                },
          })),
          symbolSize: (_value: number, item: { data: { focus_papers: number } }) =>
            item.data.focus_papers === 0
              ? 8
              : Math.min(24, 11 + Math.sqrt(item.data.focus_papers) * 3.2),
          z: 4,
        },
      ],
      media: [
        {
          query: { maxWidth: 420 },
          option: {
            grid: { left: 46, right: 16, top: 58, bottom: 34 },
            series: [
              {
                label: {
                  show: true,
                  distance: 18,
                  formatter: (item: { dataIndex: number; value: number }) => {
                    const row = rows[item.dataIndex];
                    const peakValue = Math.max(...percentages, 0);
                    return row && (row.year === 2020 || row.year === 2025 || Number(item.value) === peakValue)
                      ? `${Number(item.value).toFixed(1)}%`
                      : "";
                  },
                },
                markLine: { label: { show: false } },
              },
              {},
            ],
          },
        },
      ],
    };
  }, [report, selectedCorpusLabel]);

  const uoftPaperCountOption = useMemo(() => {
    const rows = report?.yearly ?? [];
    return {
      animationDuration: 280,
      aria: {
        enabled: true,
        description: `Number of ${selectedCorpusLabel} papers with a University of Toronto affiliation by year for the current selection.`,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#ffffff",
        borderColor: "rgba(33,60,81,0.18)",
        textStyle: { color: "#213C51", fontFamily: "'JetBrains Mono', monospace" },
        formatter: (items: Array<{ dataIndex: number }>) => {
          const row = rows[items[0]?.dataIndex];
          if (!row) return "";
          return `${row.year}<br/><strong>${row.focus_papers}</strong> U of T papers<br/>${row.corpus_papers} ${selectedCorpusLabel} papers in current selection`;
        },
      },
      grid: { left: 48, right: 18, top: 22, bottom: 32 },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.year),
        axisLabel: { color: "#6594B1", fontSize: 10 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(33,60,81,0.12)" } },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: "#6594B1", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(33,60,81,0.07)", type: "dashed" } },
      },
      series: [
        {
          name: "U of T papers",
          type: "bar",
          barMaxWidth: 24,
          data: rows.map((row) => row.focus_papers),
          itemStyle: { color: "#C783B7", borderRadius: [4, 4, 0, 0] },
          label: {
            show: true,
            position: "top",
            color: "#213C51",
            fontSize: 9,
          },
        },
      ],
    };
  }, [report, selectedCorpusLabel]);

  const institutionNetworkOption = useMemo(() => {
    const network = report?.network;
    const nodes = network?.nodes ?? [];
    const names = new Map(nodes.map((node) => [node.id, node.name]));
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const focusId = network?.focus?.id;
    const directIds = new Set<string>();
    const focusPaperCounts = new Map<string, number>();
    (network?.edges ?? []).forEach((edge) => {
      if (edge.source === focusId) {
        directIds.add(edge.target);
        focusPaperCounts.set(edge.target, edge.paper_count);
      } else if (edge.target === focusId) {
        directIds.add(edge.source);
        focusPaperCounts.set(edge.source, edge.paper_count);
      }
    });

    const directNodes = nodes
      .filter((node) => !node.is_focus && directIds.has(node.id))
      .sort((left, right) =>
        (focusPaperCounts.get(right.id) ?? 0) - (focusPaperCounts.get(left.id) ?? 0)
        || right.collaborator_count - left.collaborator_count
      );
    const leaderNodes = nodes
      .filter((node) => !node.is_focus && !directIds.has(node.id))
      .sort((left, right) => left.rank - right.rank);
    const focusNode = nodes.find((node) => node.is_focus);

    const adjacency = new Map<string, Array<{
      neighborId: string;
      edge: { source: string; target: string; paper_count: number };
    }>>();
    nodes.forEach((node) => adjacency.set(node.id, []));
    (network?.edges ?? []).forEach((edge) => {
      if (!adjacency.has(edge.source) || !adjacency.has(edge.target)) return;
      adjacency.get(edge.source)?.push({ neighborId: edge.target, edge });
      adjacency.get(edge.target)?.push({ neighborId: edge.source, edge });
    });

    const parentByNode = new Map<string, string>();
    const parentEdgeByNode = new Map<string, { source: string; target: string; paper_count: number }>();
    const branchByNode = new Map<string, string>();
    const branchRoots = directNodes;
    if (focusId && adjacency.has(focusId) && branchRoots.length) {
      const visited = new Set([focusId, ...branchRoots.map((node) => node.id)]);
      const branchSizes = new Map(branchRoots.map((node) => [node.id, 1]));
      branchRoots.forEach((root) => {
        const focusEdge = adjacency.get(focusId)?.find((item) => item.neighborId === root.id)?.edge;
        parentByNode.set(root.id, focusId);
        branchByNode.set(root.id, root.id);
        if (focusEdge) parentEdgeByNode.set(root.id, focusEdge);
      });

      let frontier = branchRoots.map((node) => node.id);
      while (frontier.length) {
        const candidates = new Map<string, Array<{
          parentId: string;
          branchId: string;
          edge: { source: string; target: string; paper_count: number };
        }>>();
        frontier.forEach((parentId) => {
          const branchId = branchByNode.get(parentId);
          if (!branchId) return;
          (adjacency.get(parentId) ?? []).forEach(({ neighborId, edge }) => {
            if (visited.has(neighborId) || neighborId === focusId) return;
            const choices = candidates.get(neighborId) ?? [];
            choices.push({ parentId, branchId, edge });
            candidates.set(neighborId, choices);
          });
        });

        const nextFrontier: string[] = [];
        [...candidates.entries()]
          .sort(([leftId], [rightId]) =>
            (nodeById.get(leftId)?.rank ?? 9999) - (nodeById.get(rightId)?.rank ?? 9999)
          )
          .forEach(([nodeId, choices]) => {
            const choice = [...choices].sort((left, right) =>
              (branchSizes.get(left.branchId) ?? 0) - (branchSizes.get(right.branchId) ?? 0)
              || right.edge.paper_count - left.edge.paper_count
              || (nodeById.get(left.parentId)?.rank ?? 9999) - (nodeById.get(right.parentId)?.rank ?? 9999)
            )[0];
            if (!choice || visited.has(nodeId)) return;
            visited.add(nodeId);
            parentByNode.set(nodeId, choice.parentId);
            parentEdgeByNode.set(nodeId, choice.edge);
            branchByNode.set(nodeId, choice.branchId);
            branchSizes.set(choice.branchId, (branchSizes.get(choice.branchId) ?? 0) + 1);
            nextFrontier.push(nodeId);
          });
        frontier = nextFrontier;
      }
    }

    const positions = new Map<string, { x: number; y: number; angle: number }>();
    if (focusId) positions.set(focusId, { x: 0, y: 0, angle: -Math.PI / 2 });
    branchRoots.forEach((root, rootIndex) => {
      const branchAngle = -Math.PI * 3 / 4 + (rootIndex * Math.PI * 2) / Math.max(branchRoots.length, 1);
      positions.set(root.id, {
        x: Math.cos(branchAngle) * 105,
        y: Math.sin(branchAngle) * 105,
        angle: branchAngle,
      });
    });
    leaderNodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(leaderNodes.length, 1);
      const radius = 218 + (index % 2) * 22;
      positions.set(node.id, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        angle,
      });
    });

    const positionedIds = new Set(positions.keys());
    const unpositionedNodes = nodes.filter((node) => !positionedIds.has(node.id));
    unpositionedNodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(unpositionedNodes.length, 1);
      positions.set(node.id, { x: Math.cos(angle) * 236, y: Math.sin(angle) * 236, angle });
    });

    const treeLinks = [...parentEdgeByNode.entries()].map(([childId, edge]) => ({
      source: parentByNode.get(childId) ?? edge.source,
      target: childId,
      paper_count: edge.paper_count,
    }));
    const treeEdgeKeys = new Set(treeLinks.map((edge) => networkEdgeKey(edge.source, edge.target)));
    const visibleLinks = networkMode === "spotlight" ? treeLinks : network?.edges ?? [];
    const bloomNodes = [
      ...(focusNode ? [focusNode] : []),
      ...branchRoots,
      ...leaderNodes,
      ...directNodes.filter((node) => !branchRoots.some((root) => root.id === node.id)),
    ];

    return {
      animationDuration: motionDuration(460),
      animationDurationUpdate: motionDuration(240),
      animationEasing: "cubicOut",
      aria: {
        enabled: true,
        description: network
          ? `Dandelion-shaped institution collaboration network from ${network.scope.complete_papers} papers with complete institution metadata. U of T is the flower centre; every branch shown is a real shared-paper connection.`
          : "Institution collaboration network.",
      },
      tooltip: {
        backgroundColor: "rgba(255, 255, 255, 0.97)",
        borderColor: "rgba(33, 60, 81, 0.16)",
        extraCssText: "box-shadow: 0 16px 38px rgba(33,60,81,0.14); border-radius: 10px;",
        textStyle: { color: "#213C51", fontFamily: "'JetBrains Mono', monospace" },
        formatter: (item: {
          dataType: "node" | "edge";
          data: {
            name?: string;
            collaborator_count?: number;
            collaboration_paper_count?: number;
            paper_count?: number;
            source?: string;
            target?: string;
          };
        }) => {
          if (item.dataType === "edge") {
            return `${names.get(item.data.source ?? "") ?? "Institution"} ↔ ${names.get(item.data.target ?? "") ?? "Institution"}<br/><strong>${item.data.paper_count ?? 0}</strong> shared papers`;
          }
          return `${item.data.name}<br/><strong>${item.data.collaborator_count ?? 0}</strong> distinct collaborators<br/>${item.data.collaboration_paper_count ?? 0} collaboration papers`;
        },
      },
      legend: { show: false },
      series: [
        {
          type: "graph",
          layout: "none",
          left: "8%",
          right: "8%",
          top: "8%",
          bottom: "25%",
          roam: false,
          draggable: false,
          focusNodeAdjacency: true,
          data: bloomNodes.map((node) => {
            const position = positions.get(node.id) ?? { x: 0, y: 0, angle: 0 };
            const isDirect = directIds.has(node.id);
            const labelPosition = node.is_focus
              ? "inside"
              : Math.abs(position.x) < 18
                ? position.y < 0 ? "top" : "bottom"
                : !isDirect && Math.abs(position.x) > 175
                  ? position.x < 0 ? "right" : "left"
                  : position.x < 0 ? "left" : "right";
            return {
              ...node,
              x: position.x,
              y: position.y,
              short_name: compactInstitutionName(node.name),
              category: node.is_focus ? 0 : isDirect ? 1 : 2,
              symbolSize: node.is_focus
                ? 48
                : isDirect
                  ? Math.max(20, Math.min(30, 14 + Math.sqrt(focusPaperCounts.get(node.id) ?? 1) * 5))
                  : Math.max(11, Math.min(19, 7 + Math.sqrt(node.collaborator_count) * 1.2)),
              itemStyle: {
                color: node.is_focus
                  ? "#D987BF"
                  : isDirect
                    ? "#4FB9AD"
                    : "#91AABD",
                borderColor: node.is_focus ? "#FFFFFF" : "#F8FBFC",
                borderWidth: node.is_focus ? 5 : 2.5,
                shadowBlur: node.is_focus ? 24 : isDirect ? 12 : 4,
                shadowColor: node.is_focus
                  ? "rgba(199, 131, 183, 0.42)"
                  : isDirect ? "rgba(79, 185, 173, 0.25)" : "rgba(33,60,81,0.12)",
              },
              label: {
                show: node.is_focus || isDirect || node.rank <= 10,
                position: labelPosition,
                distance: node.is_focus ? 0 : 7,
                formatter: node.is_focus
                  ? "U of T"
                  : (item: { data: { short_name: string } }) => item.data.short_name,
                color: node.is_focus ? "#FFFFFF" : isDirect ? "#276E68" : "#466579",
                fontSize: node.is_focus ? 10 : isDirect ? 10 : 9,
                fontWeight: node.is_focus || isDirect ? 700 : 600,
                textBorderColor: "rgba(255,255,255,0.92)",
                textBorderWidth: node.is_focus ? 0 : 4,
              },
            };
          }),
          links: visibleLinks.map((edge, index) => {
            const isFocusEdge = edge.source === focusId || edge.target === focusId;
            const isTreeEdge = treeEdgeKeys.has(networkEdgeKey(edge.source, edge.target));
            return {
              ...edge,
              lineStyle: {
                color: isFocusEdge ? "#D987BF" : isTreeEdge ? "#66BFB5" : "#86A1B3",
                opacity: isFocusEdge ? 0.86 : isTreeEdge ? 0.54 : 0.1,
                width: isFocusEdge
                  ? Math.min(5, 1.5 + Math.sqrt(edge.paper_count))
                  : isTreeEdge ? Math.min(3, 0.9 + Math.sqrt(edge.paper_count) * 0.65) : 0.8,
                curveness: networkMode === "full" ? ((index % 3) - 1) * 0.08 : 0.08,
              },
            };
          }),
          categories: [
            { name: "U of T" },
            { name: "Direct U of T collaborator" },
            { name: "Other network leader" },
          ],
          labelLayout: { hideOverlap: true },
          emphasis: {
            focus: "adjacency",
            scale: 1.2,
            label: { show: true },
            lineStyle: { opacity: 0.92 },
          },
          blur: {
            itemStyle: { opacity: 0.24 },
            lineStyle: { opacity: 0.035 },
            label: { opacity: 0.2 },
          },
        },
      ],
      media: [
        {
          query: { maxWidth: 420 },
          option: {
            series: [
              {
                left: "10%",
                right: "10%",
                top: "9%",
                bottom: "27%",
              },
            ],
          },
        },
      ],
    };
  }, [networkMode, report]);

  const schemes = options?.credit_schemes ?? FALLBACK_SCHEMES;
  const exportUrl = institutionAuthorshipExportUrl(new URLSearchParams(query));
  const metadataExportUrl = tier1AuthorInstitutionMetadataExportUrl();
  const latestRun = options?.latest_enrichment_run;

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>{selectedCorpusLabel} · paper-specific metadata</div>
          <div className={styles.titleRow}>
            <h1>Institution contribution comparison</h1>
            <label className={styles.corpusPicker}>
              <span>Corpus</span>
              <select
                aria-label="Institution comparison corpus"
                value={selectedCorpus}
                onChange={(event) => updateParam("corpus", event.target.value, DEFAULTS.corpus)}
              >
                <option value="tier1">Tier 1</option>
                <option value="tier1_tier2">Tier 1 + Tier 2</option>
              </select>
            </label>
          </div>
          <p>
            Confirmed paper footprint counts a paper for every resolved institution
            represented by any author. Author position and multi-affiliation rules
            affect only weighted contribution scores. Full-text Markdown, extracted
            evidence, classifications, and reviews are not inputs to this page. The
            selected corpus loads its own immutable metadata snapshot.
          </p>
        </div>
        <div className={styles.heroActions}>
          <span className={`${styles.status} ${latestRun?.status === "succeeded" ? styles.ready : ""}`}>
            <span aria-hidden="true" />
            {latestRun ? `Metadata ${latestRun.status.replaceAll("_", " ")}` : "No metadata run"}
          </span>
          <a className={styles.exportButton} href={exportUrl}>
            Export comparison CSV
          </a>
          {selectedCorpus === "tier1" ? (
            <a className={styles.exportButton} href={metadataExportUrl}>
              Download 829-paper metadata
            </a>
          ) : null}
        </div>
      </header>

      <section className={styles.filterPanel} aria-label="Comparison filters">
        <div className={styles.filterGrid}>
          <label>
            <span>Credit model</span>
            <select
              value={valueFor("credit_scheme")}
              onChange={(event) => updateParam("credit_scheme", event.target.value, DEFAULTS.credit_scheme)}
            >
              {schemes.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Author credit filter</span>
            <select
              value={valueFor("author_role")}
              onChange={(event) => updateParam("author_role", event.target.value, DEFAULTS.author_role)}
            >
              {(options?.author_roles ?? FALLBACK_AUTHOR_ROLES).map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Multiple affiliations</span>
            <select
              value={valueFor("affiliation_allocation")}
              onChange={(event) => updateParam("affiliation_allocation", event.target.value, DEFAULTS.affiliation_allocation)}
            >
              <option value="fractional">Divide author credit</option>
              <option value="full">Full credit for each</option>
            </select>
          </label>
          <label>
            <span>U of T scope</span>
            <select
              value={valueFor("focus_scope")}
              onChange={(event) => updateParam("focus_scope", event.target.value, DEFAULTS.focus_scope)}
            >
              <option value="strict">Exact institution only</option>
              <option value="lineage">Include descendants</option>
            </select>
          </label>
          <label>
            <span>Affiliation confidence</span>
            <select
              value={valueFor("min_affiliation_confidence")}
              onChange={(event) => updateParam("min_affiliation_confidence", event.target.value, DEFAULTS.min_affiliation_confidence)}
            >
              <option value="0.5">At least 50%</option>
              <option value="0.8">At least 80%</option>
              <option value="0.95">At least 95%</option>
            </select>
          </label>
          <label>
            <span>Year from</span>
            <input
              type="number"
              min={options?.years[0]}
              max={options?.years.at(-1)}
              value={searchParams.get("year_from") ?? ""}
              placeholder={options?.years[0] ? String(options.years[0]) : "Any"}
              onChange={(event) => updateParam("year_from", event.target.value)}
            />
          </label>
          <label>
            <span>Year to</span>
            <input
              type="number"
              min={options?.years[0]}
              max={options?.years.at(-1)}
              value={searchParams.get("year_to") ?? ""}
              placeholder={options?.years.at(-1) ? String(options.years.at(-1)) : "Any"}
              onChange={(event) => updateParam("year_to", event.target.value)}
            />
          </label>
          <form className={styles.searchForm} onSubmit={applySearch}>
            <label>
              <span>Paper title or abstract</span>
              <div className={styles.searchControl}>
                <input
                  type="text"
                  value={searchDraft}
                  placeholder="Filter paper set"
                  onChange={(event) => setSearchDraft(event.target.value)}
                />
                <button type="submit">Apply</button>
              </div>
            </label>
          </form>
        </div>
        <div className={styles.filterFooter}>
          <p>
            {report?.configuration.credit_scheme_description ?? "First and last author credit is emphasized by default."}
            {" "}<strong>Role filter:</strong>{" "}
            {report?.configuration.author_role_description ?? selectedRoleFallback.description}
          </p>
          <button type="button" onClick={resetFilters}>Reset filters</button>
        </div>
      </section>

      {error ? (
        <section className={styles.notice} role="alert">
          <div>
            <strong>The comparison could not be loaded.</strong>
            <p>{error}</p>
          </div>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>Try again</button>
        </section>
      ) : loading && !report ? (
        <section className={styles.loading} aria-live="polite">
          <span /> Loading authorship metadata and contribution scores…
        </section>
      ) : report && !report.available ? (
        <section className={styles.notice}>
          <div>
            <strong>Authorship metadata is not populated yet.</strong>
            <p>The enrichment agent must finish before this comparison has evidence to display.</p>
          </div>
        </section>
      ) : report ? (
        <>
          <section className={styles.kpiGrid} aria-label="Comparison summary">
            <article className={`${styles.kpi} ${styles.focusKpi}`}>
              <span>U of T weighted credit</span>
              <strong>{formatCredit(report.focus.weighted_credit)}</strong>
              <small>{formatPercent(report.focus.share_of_resolved_credit)} of resolved credit</small>
            </article>
            <article className={styles.kpi}>
              <span>Non-U of T weighted credit</span>
              <strong>{formatCredit(report.comparison.other_institutions_weighted_credit)}</strong>
              <small>
                {report.comparison.other_institutions_paper_count.toLocaleString()} distinct papers with ≥1 resolved non-U of T affiliation · may overlap U of T
              </small>
            </article>
            <article className={styles.kpi}>
              <span>U of T weighted-credit rank</span>
              <strong>{report.focus.rank ? `#${report.focus.rank}` : "—"}</strong>
              <small>
                {report.focus.paper_count.toLocaleString()} distinct papers with ≥1 resolved U of T affiliation · may overlap non-U of T
              </small>
            </article>
            <article className={styles.kpi}>
              <span>Affiliation coverage</span>
              <strong>{formatPercent(report.scope.affiliation_credit_coverage)}</strong>
              <small>{report.scope.authorships_with_resolved_affiliations.toLocaleString()} selected authorships resolved</small>
            </article>
          </section>

          <section className={styles.chartGrid}>
            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span>Institution ranking</span>
                  <h2>Weighted contribution leaders</h2>
                </div>
                <span className={styles.legend}><i /> U of T scope</span>
              </div>
              <EChart option={topInstitutionsOption} style={{ height: 390 }} />
            </article>
            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span>Time series</span>
                  <h2>U of T versus other credit</h2>
                </div>
              </div>
              <EChart option={yearlyOption} style={{ height: 390 }} />
            </article>
          </section>

          <section className={styles.chartGrid} aria-label={`U of T ${selectedCorpusLabel} paper footprint over time`}>
            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span>Annual contribution pulse</span>
                  <h2>U of T paper share, year by year</h2>
                </div>
                <div className={styles.chartHeaderStats} aria-label="Paper share highlights">
                  <span>
                    <strong>{formatPercent(report.focus.share_of_corpus_papers)}</strong>
                    <small>all years</small>
                  </span>
                  {uoftPaperSharePeak ? (
                    <span>
                      <strong>{formatPercent(uoftPaperSharePeak.focus_paper_share_of_corpus)}</strong>
                      <small>{uoftPaperSharePeak.year} peak</small>
                    </span>
                  ) : null}
                </div>
              </div>
              <EChart option={uoftPaperShareOption} style={{ height: 330 }} />
              <p className={styles.chartNote}>
                Each stem is one calendar year; dot size tracks the number of U of T papers. The dashed line is the all-year share for the current selection.
              </p>
            </article>
            <article className={styles.panel}>
              <div className={styles.panelHeader}>
                <div>
                  <span>Paper count over time</span>
                  <h2>{selectedCorpusLabel} papers with a U of T affiliation</h2>
                </div>
                <span>{report.focus.paper_count.toLocaleString()} distinct papers</span>
              </div>
              <EChart option={uoftPaperCountOption} style={{ height: 330 }} />
            </article>
            <table className={styles.srOnly}>
              <caption>U of T {selectedCorpusLabel} paper footprint by year</caption>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>All {selectedCorpusLabel} papers</th>
                  <th>U of T papers</th>
                  <th>U of T share</th>
                </tr>
              </thead>
              <tbody>
                {report.yearly.map((row) => (
                  <tr key={row.year}>
                    <td>{row.year}</td>
                    <td>{row.corpus_papers}</td>
                    <td>{row.focus_papers}</td>
                    <td>{formatPercent(row.focus_paper_share_of_corpus)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <article className={`${styles.panel} ${styles.networkPanel}`}>
            <div className={styles.panelHeader}>
              <div>
                <span>Institution collaboration network</span>
                <h2>
                  Connections across {report.network.scope.complete_papers.toLocaleString()} fully mapped papers
                </h2>
              </div>
              <div className={styles.networkMode} role="group" aria-label="Network display mode">
                <button
                  type="button"
                  className={networkMode === "spotlight" ? styles.activeNetworkMode : undefined}
                  aria-pressed={networkMode === "spotlight"}
                  onClick={() => setNetworkMode("spotlight")}
                >
                  U of T bloom
                </button>
                <button
                  type="button"
                  className={networkMode === "full" ? styles.activeNetworkMode : undefined}
                  aria-pressed={networkMode === "full"}
                  onClick={() => setNetworkMode("full")}
                >
                  All 160 links
                </button>
              </div>
            </div>
            {report.network.available ? (
              <div className={styles.networkLayout}>
                <div className={styles.networkChart}>
                  <div className={`${styles.networkStage} ${styles.dandelionStage}`}>
                    <div className={styles.networkOrbitMeta} aria-hidden="true">
                      <span>Dandelion · top {report.network.scope.displayed_node_count.toLocaleString()}</span>
                      <span>{networkMode === "spotlight" ? "Truthful spanning branches" : `${report.network.scope.displayed_connection_count.toLocaleString()} visible links`}</span>
                    </div>
                    <div className={styles.networkCanvas}>
                      <EChart option={institutionNetworkOption} style={{ height: 550 }} />
                    </div>
                    {report.network.focus ? (
                      <div className={styles.bloomMetrics} aria-label="U of T collaboration network summary">
                        <span className={styles.bloomLeafLeft}>
                          <small>Network rank</small>
                          <strong>#{report.network.focus.rank}</strong>
                        </span>
                        <span className={styles.bloomLeafRight}>
                          <small>Collaborators</small>
                          <strong>{report.network.focus.collaborator_count.toLocaleString()}</strong>
                        </span>
                        <em>
                          Top {formatPercent(1 - report.network.focus.fraction_of_institutions_with_fewer_collaborators)}
                        </em>
                      </div>
                    ) : null}
                    <div className={styles.networkLegend} aria-label="Network legend">
                      <span><i className={styles.focusLegendDot} />U of T flower centre</span>
                      <span><i className={styles.directLegendDot} />Direct collaborator</span>
                      <span><i className={styles.leaderLegendDot} />Outer network seed</span>
                    </div>
                  </div>
                  <p className={styles.chartNote}>
                    Dandelion view rooted at U of T. Every displayed branch is a real shared-paper connection; outer seeds may connect through a direct U of T collaborator rather than directly to U of T.
                    Switch to All 160 links to reveal the complete Top-25 structure, or hover a seed to isolate its relationships.
                  </p>
                </div>
                <div className={styles.networkRanking}>
                  <h3>Most connected institutions</h3>
                  {report.network.focus ? (
                    <p>
                      U of T has more distinct collaborators than {report.network.focus.institutions_with_fewer_collaborators.toLocaleString()} of the other institutions
                      ({formatPercent(report.network.focus.fraction_of_institutions_with_fewer_collaborators)}).
                    </p>
                  ) : (
                    <p>No U of T institution node exists in the current filtered paper set.</p>
                  )}
                  <div className={styles.networkTableWrap}>
                    <table>
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Institution</th>
                          <th>Connections</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.network.ranking.map((node) => (
                          <tr key={node.id} className={node.is_focus ? styles.focusNetworkRow : undefined}>
                            <td>#{node.rank}</td>
                            <td>{node.name}</td>
                            <td>{node.collaborator_count.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className={styles.networkMethod}>
                    A connection requires different authors from two institutions on the same fully mapped paper.
                    The U of T node always uses the exact U of T ROR/OpenAlex identity so it remains comparable to individual institutions.
                  </p>
                </div>
              </div>
            ) : (
              <p className={styles.networkEmpty}>No cross-institution connections exist in the current filtered paper set.</p>
            )}
          </article>

          <section className={styles.tablePanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>Detailed comparison</span>
                <h2>Institution credit table</h2>
              </div>
              <span>{report.scope.institution_count.toLocaleString()} institutions in scope</span>
            </div>
            <div className={styles.tableWrap}>
              <table>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Institution</th>
                    <th>Country</th>
                    <th>Weighted credit</th>
                    <th>Share</th>
                    <th>Confirmed papers (any author)</th>
                    <th>First-author credit</th>
                    <th>Last-author credit</th>
                    <th>Corresponding-author credit</th>
                    <th>Authorships</th>
                  </tr>
                </thead>
                <tbody>
                  {report.institutions.map((row) => (
                    <tr key={row.id ?? `${row.name}-${row.rank}`} className={row.contributes_to_focus ? styles.focusRow : undefined}>
                      <td className={styles.numeric}>#{row.rank}</td>
                      <td>
                        <div className={styles.institutionName}>
                          {row.name}
                          {row.contributes_to_focus && <span>U of T scope</span>}
                        </div>
                      </td>
                      <td>{row.country_code ?? "—"}</td>
                      <td className={styles.numericStrong}>{formatCredit(row.weighted_credit)}</td>
                      <td className={styles.numeric}>{formatPercent(row.share_of_resolved_credit)}</td>
                      <td className={styles.numeric}>{row.paper_count.toLocaleString()}</td>
                      <td className={styles.numeric}>{formatCredit(row.first_author_credit)}</td>
                      <td className={styles.numeric}>{formatCredit(row.last_author_credit)}</td>
                      <td className={styles.numeric}>{formatCredit(row.corresponding_author_credit)}</td>
                      <td className={styles.numeric}>{row.authorship_count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className={styles.auditGrid}>
            <article className={styles.methodCard}>
              <span>Current rule</span>
              <h2>{report.configuration.credit_scheme_label}</h2>
              <p>{report.configuration.credit_scheme_description}</p>
              <dl>
                <div><dt>Corpus</dt><dd>{selectedCorpusLabel}</dd></div>
                <div>
                  <dt>Role</dt>
                  <dd>{report.configuration.author_role_label ?? selectedRoleFallback.label}</dd>
                </div>
                <div><dt>Multi-affiliation</dt><dd>{report.configuration.affiliation_allocation}</dd></div>
                <div><dt>Paper count</dt><dd>any affiliated author</dd></div>
                <div><dt>U of T identity</dt><dd>{report.configuration.focus_scope}</dd></div>
              </dl>
            </article>
            <article className={styles.methodCard}>
              <span>Evidence coverage</span>
              <h2>
                {report.scope.papers_with_complete_institution_membership.toLocaleString()}
                /{report.scope.corpus_papers.toLocaleString()} papers complete
              </h2>
              <p>
                {report.scope.papers_with_incomplete_institution_membership.toLocaleString()} papers have at least one incomplete author affiliation;
                {" "}{report.scope.papers_without_authorship_metadata.toLocaleString()} have no authorship metadata.
                {" "}{report.scope.unresolved_affiliation_assertions.toLocaleString()} unresolved affiliation assertions remain excluded.
              </p>
              <dl>
                <div><dt>Filter fingerprint</dt><dd title={report.audit.filter_fingerprint}>{compactHash(report.audit.filter_fingerprint)}</dd></div>
                <div><dt>Paper set</dt><dd title={report.audit.paper_set_sha256}>{compactHash(report.audit.paper_set_sha256)}</dd></div>
                <div><dt>Algorithm</dt><dd>{report.audit.algorithm}</dd></div>
              </dl>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
