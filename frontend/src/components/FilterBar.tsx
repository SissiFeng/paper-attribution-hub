import { useSearchParams } from "react-router-dom";

import { LABEL_OPTIONS, filterFromSearchParams, filterToSearchParams } from "@/lib/filter";
import type { PaperFilterState, RelevanceLabel } from "@/types";
import { EMPTY_FILTER } from "@/types";

interface Props {
  // If true the filter bar shows a smaller subset (used in pages where the
  // chart already encodes the label dimension).
  hideLabels?: boolean;
}

export function FilterBar({ hideLabels = false }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = filterFromSearchParams(searchParams);

  const update = (next: PaperFilterState) => {
    setSearchParams(filterToSearchParams(next));
  };

  const toggleLabel = (label: RelevanceLabel) => {
    const has = filter.labels.includes(label);
    update({
      ...filter,
      labels: has ? filter.labels.filter((l) => l !== label) : [...filter.labels, label],
    });
  };

  return (
    <div className="filter-bar">
      <input
        type="text"
        placeholder="Search title or abstract…"
        value={filter.search ?? ""}
        onChange={(e) => update({ ...filter, search: e.target.value || undefined })}
        className="filter-search"
      />
      <label>
        Year:&nbsp;
        <input
          type="number"
          placeholder="from"
          value={filter.yearFrom ?? ""}
          onChange={(e) =>
            update({
              ...filter,
              yearFrom: e.target.value ? Number(e.target.value) : undefined,
            })
          }
          style={{ width: 70 }}
        />
        &nbsp;–&nbsp;
        <input
          type="number"
          placeholder="to"
          value={filter.yearTo ?? ""}
          onChange={(e) =>
            update({
              ...filter,
              yearTo: e.target.value ? Number(e.target.value) : undefined,
            })
          }
          style={{ width: 70 }}
        />
      </label>
      <label>
        Min confidence:&nbsp;
        <input
          type="number"
          step="0.05"
          min={0}
          max={1}
          value={filter.minConfidence ?? ""}
          onChange={(e) =>
            update({
              ...filter,
              minConfidence: e.target.value ? Number(e.target.value) : undefined,
            })
          }
          style={{ width: 70 }}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={filter.partnerOnly}
          onChange={(e) => update({ ...filter, partnerOnly: e.target.checked })}
        />{" "}
        AC partner only
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={filter.acAuthorOnly}
          onChange={(e) => update({ ...filter, acAuthorOnly: e.target.checked })}
        />{" "}
        AC author only
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={filter.hasFulltext ?? false}
          onChange={(e) =>
            update({ ...filter, hasFulltext: e.target.checked ? true : undefined })
          }
        />{" "}
        Full-text only
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={filter.hasReview === true}
          onChange={(e) =>
            update({
              ...filter,
              hasReview: e.target.checked ? true : undefined,
            })
          }
        />{" "}
        Reviewed
      </label>

      {!hideLabels && (
        <div className="label-chips">
          {LABEL_OPTIONS.map((l) => (
            <button
              key={l}
              className={`chip-toggle ${filter.labels.includes(l) ? `active ${l}` : ""}`}
              onClick={() => toggleLabel(l)}
            >
              {l.replace("_", " ")}
            </button>
          ))}
        </div>
      )}

      <button onClick={() => setSearchParams(filterToSearchParams(EMPTY_FILTER))}>
        Clear
      </button>
    </div>
  );
}
