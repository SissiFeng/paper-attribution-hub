import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { ClassificationBadge, ConfidenceBar } from "@/components/ClassificationBadge";
import { RagStatusBadge } from "@/components/RagStatusBadge";
import type { Paper } from "@/types";

interface Props {
  papers: Paper[];
  selectedId: string | null;
  onSelect: (paper: Paper) => void;
  metadataOnly?: boolean;
  readOnly?: boolean;
}

export function PaperTable({
  papers,
  selectedId,
  onSelect,
  metadataOnly = false,
  readOnly = false,
}: Props) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "confidence", desc: true },
  ]);

  const columns = useMemo<ColumnDef<Paper>[]>(
    () => metadataOnly ? [
      {
        id: "markdown",
        header: "Markdown",
        accessorFn: (row) => row.full_text_available,
        cell: ({ getValue }) => (
          <span className={`status-chip ${getValue<boolean>() ? "success" : ""}`}>
            {getValue<boolean>() ? "Imported from S3" : "Pending"}
          </span>
        ),
      },
      {
        id: "title",
        header: "Title",
        accessorFn: (row) => row.title,
        cell: ({ row }) => (
          <div>
            <div style={{ fontWeight: 500 }}>{row.original.title}</div>
            <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              {row.original.year} · {row.original.venue ?? "—"}
            </div>
          </div>
        ),
      },
      {
        id: "authors",
        header: "Authors",
        accessorFn: (row) => row.authors.map((author) => author.name).join(", "),
        cell: ({ getValue }) => getValue<string>() || "—",
      },
      {
        id: "doi",
        header: "DOI",
        accessorFn: (row) => row.doi ?? "",
        cell: ({ getValue }) => getValue<string>() || "—",
      },
    ] : [
      {
        id: "label",
        header: "Label",
        accessorFn: (row) => row.classification?.label ?? "—",
        cell: ({ getValue }) => <ClassificationBadge label={getValue<string>()} />,
        sortingFn: (a, b) => {
          const order = [
            "CORE_RELEVANT",
            "RELATED_RELEVANT",
            "UNCERTAIN",
            "ADJACENT",
            "EXCLUDE",
          ];
          return (
            order.indexOf(a.original.classification?.label ?? "EXCLUDE") -
            order.indexOf(b.original.classification?.label ?? "EXCLUDE")
          );
        },
      },
      {
        id: "confidence",
        header: "Confidence",
        accessorFn: (row) => row.classification?.confidence ?? 0,
        cell: ({ getValue, row }) => readOnly && !row.original.classification ? <span>—</span> : <ConfidenceBar value={getValue<number>()} />,
      },
      {
        id: "rag",
        header: readOnly ? "Source" : "RAG",
        accessorFn: (row) => row.rag_status?.status ?? "missing_fulltext",
        cell: ({ row }) => readOnly ? <span>{row.original.full_text_available ? 'Full text' : row.original.abstract ? 'Abstract' : 'Metadata'}</span> : <RagStatusBadge status={row.original.rag_status} compact />,
      },
      {
        id: "title",
        header: "Title",
        accessorFn: (row) => row.title,
        cell: ({ row }) => (
          <div>
            <div style={{ fontWeight: 500 }}>
              {row.original.title}
              {row.original.provenance &&
                row.original.provenance.startsWith("discovered") && (
                  <span className={`provenance-badge ${row.original.provenance}`}>
                    {row.original.provenance === "discovered_auto"
                      ? "auto-discovered"
                      : "discovered (approved)"}
                  </span>
                )}
            </div>
            <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              {row.original.year} · {row.original.venue ?? "—"}
            </div>
          </div>
        ),
      },
      {
        id: "people",
        header: "Matched AC people",
        accessorFn: (row) =>
          (row.classification?.matched_people ?? [])
            .map((m) => m.name)
            .join(", "),
        cell: ({ getValue }) => (
          <span style={{ color: "var(--color-steel)" }}>{getValue<string>() || "—"}</span>
        ),
      },
      {
        id: "topics",
        header: "Topics",
        accessorFn: (row) =>
          (row.classification?.matched_topics ?? [])
            .filter((t) => t.is_core)
            .map((t) => t.name)
            .join(", "),
        cell: ({ getValue }) => getValue<string>() || "—",
      },
      {
        id: "review",
        header: "Human",
        accessorFn: (row) => row.review?.human_label ?? "",
        cell: ({ getValue }) => {
          const v = getValue<string>();
          return v ? <ClassificationBadge label={v} /> : <span style={{ color: "var(--muted)" }}>—</span>;
        },
      },
    ],
    [metadataOnly, readOnly]
  );

  const table = useReactTable({
    data: papers,
    columns,
    state: { sorting, columnVisibility: { review: !readOnly } },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (papers.length === 0) {
    return <div className="empty">No papers match the current filters.</div>;
  }

  return (
    <table className="papers">
      <thead>
        {table.getHeaderGroups().map((hg) => (
          <tr key={hg.id}>
            {hg.headers.map((h) => (
              <th
                key={h.id}
                onClick={h.column.getToggleSortingHandler()}
                style={{ cursor: h.column.getCanSort() ? "pointer" : "default" }}
              >
                {flexRender(h.column.columnDef.header, h.getContext())}
                {h.column.getIsSorted() === "asc" && " ▲"}
                {h.column.getIsSorted() === "desc" && " ▼"}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr
            key={row.id}
            onClick={() => onSelect(row.original)}
            style={{
              background:
                row.original.id === selectedId
                  ? "rgba(101, 148, 177, 0.10)"
                  : undefined,
            }}
          >
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
