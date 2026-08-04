import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getFilterOptions } from "@/lib/api";
import {
  LABEL_OPTIONS,
  filterFromSearchParams,
  mergeFilterSearchParams,
} from "@/lib/filter";
import type { FilterOptions, PaperFilterState, RelevanceLabel } from "@/types";
import { DEFAULT_FILTER } from "@/types";

interface Props {
  hideLabels?: boolean;
}

interface FacetOption {
  value: string;
  label: string;
}

interface FacetPickerProps {
  label: string;
  values: string[];
  options: FacetOption[];
  onChange: (values: string[]) => void;
}

const SDL_OPTIONS = ["CONFIRMED_SDL", "PROBABLE_SDL", "SDL_ADJACENT", "NOT_SDL", "INSUFFICIENT_EVIDENCE"];
const AC_OPTIONS = ["AC_RELEVANT", "NOT_AC_RELEVANT", "INSUFFICIENT_EVIDENCE"];
const AI_OPTIONS = ["AI_FOR_SCIENCE", "NOT_AI_FOR_SCIENCE", "INSUFFICIENT_EVIDENCE"];
const REVIEW_OPTIONS = ["PENDING", "PARTIAL", "COMPLETED", "NEEDS_FULLTEXT"];
const STRICT_SDL_SCOPE = ["CONFIRMED_SDL", "PROBABLE_SDL"]; // SDL-adjacent remains a separate non-strict facet

function FacetPicker({ label, values, options, onChange }: FacetPickerProps) {
  const remaining = options.filter((option) => !values.includes(option.value));
  const labelByValue = new Map(options.map((option) => [option.value, option.label]));

  return (
    <div className="filter-facet">
      <label>
        <span>{label}</span>
        <select
          value=""
          onChange={(event) => {
            if (event.target.value) onChange([...values, event.target.value]);
          }}
          aria-label={`Add ${label} filter`}
        >
          <option value="">Add…</option>
          {remaining.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      {values.length > 0 && (
        <div className="filter-facet-values">
          {values.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onChange(values.filter((item) => item !== value))}
              title={`Remove ${labelByValue.get(value) ?? value}`}
            >
              {labelByValue.get(value) ?? value.replace(/_/g, " ")} ×
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function enumOptions(values: string[]): FacetOption[] {
  return values.map((value) => ({ value, label: value.replace(/_/g, " ") }));
}

function parseTriState(value: string): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

export function FilterBar({ hideLabels = false }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const filter = filterFromSearchParams(searchParams);

  useEffect(() => {
    let cancelled = false;
    getFilterOptions().then((result) => {
      if (!cancelled) setOptions(result);
    }).catch(() => {
      if (!cancelled) setOptions(null);
    });
    return () => { cancelled = true; };
  }, []);

  const update = (next: PaperFilterState) =>
    setSearchParams(mergeFilterSearchParams(searchParams, next));
  const invalidYearRange = filter.yearFrom != null && filter.yearTo != null && filter.yearFrom > filter.yearTo;
  const invalidConfidenceRange = filter.minConfidence != null
    && filter.maxConfidence != null
    && filter.minConfidence > filter.maxConfidence;

  const toggleLabel = (label: RelevanceLabel) => {
    const has = filter.labels.includes(label);
    update({
      ...filter,
      labels: has ? filter.labels.filter((item) => item !== label) : [...filter.labels, label],
    });
  };

  const institutionOptions = (options?.institutions ?? []).map((institution) => ({
    value: institution.id,
    label: `${institution.name}${institution.country ? ` · ${institution.country}` : ""}`,
  }));
  const strictSdlOnly = filter.sdlJudgements.length === STRICT_SDL_SCOPE.length
    && STRICT_SDL_SCOPE.every((value) => filter.sdlJudgements.includes(value))
    && filter.acRelevanceJudgements.length === 0;
  const acReportingOnly = filter.acRelevanceJudgements.length === 1
    && filter.acRelevanceJudgements[0] === "AC_RELEVANT"
    && filter.sdlJudgements.length === 0;

  return (
    <section className="filter-bar" aria-label="Shared evidence filters">
      <div className="filter-primary-row">
        <input
          type="search"
          placeholder="Search title or abstract…"
          value={filter.search ?? ""}
          onChange={(event) => update({ ...filter, search: event.target.value || undefined })}
          className="filter-search"
        />
        <label>
          Year
          <input
            type="number"
            placeholder="from"
            value={filter.yearFrom ?? ""}
            onChange={(event) => update({
              ...filter,
              yearFrom: event.target.value ? Number(event.target.value) : undefined,
            })}
          />
          <span aria-hidden="true">–</span>
          <input
            type="number"
            placeholder="to"
            value={filter.yearTo ?? ""}
            onChange={(event) => update({
              ...filter,
              yearTo: event.target.value ? Number(event.target.value) : undefined,
            })}
          />
        </label>
        <label>
          Confidence
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            placeholder="min"
            value={filter.minConfidence ?? ""}
            onChange={(event) => update({
              ...filter,
              minConfidence: event.target.value ? Number(event.target.value) : undefined,
            })}
          />
          <span aria-hidden="true">–</span>
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            placeholder="max"
            value={filter.maxConfidence ?? ""}
            onChange={(event) => update({
              ...filter,
              maxConfidence: event.target.value ? Number(event.target.value) : undefined,
            })}
          />
        </label>
        <button type="button" onClick={() => update(DEFAULT_FILTER)}>
          Reset
        </button>
      </div>

      {(invalidYearRange || invalidConfidenceRange) && (
        <div className="filter-error" role="alert">
          {invalidYearRange ? "Start year must not exceed end year. " : ""}
          {invalidConfidenceRange ? "Minimum confidence must not exceed maximum confidence." : ""}
        </div>
      )}

      {!hideLabels && (
        <div className="label-chips" aria-label="Classification labels">
          {LABEL_OPTIONS.map((label) => (
            <button
              type="button"
              key={label}
              className={`chip-toggle ${filter.labels.includes(label) ? `active ${label}` : ""}`}
              onClick={() => toggleLabel(label)}
              aria-pressed={filter.labels.includes(label)}
            >
              {label.replace(/_/g, " ")}
            </button>
          ))}
          <button
            type="button"
            className={`chip-toggle ${filter.labels.length === 0 ? "active" : ""}`}
            onClick={() => update({ ...filter, labels: [] })}
            aria-pressed={filter.labels.length === 0}
          >
            All classifications
          </button>
        </div>
      )}

      <div className="filter-scope-presets" aria-label="SDL and AC analysis scope">
        <span>Analysis scope</span>
        <button
          type="button"
          className={strictSdlOnly ? "active" : ""}
          aria-pressed={strictSdlOnly}
          onClick={() => update({
            ...filter,
            sdlJudgements: [...STRICT_SDL_SCOPE],
            acRelevanceJudgements: [],
          })}
          title="Include confirmed or probable SDL papers and exclude AC-relevant papers judged not SDL"
        >
          Strict SDL only
        </button>
        <button
          type="button"
          className={acReportingOnly ? "active" : ""}
          aria-pressed={acReportingOnly}
          onClick={() => update({
            ...filter,
            sdlJudgements: [],
            acRelevanceJudgements: ["AC_RELEVANT"],
          })}
          title="Use the independent AC reporting judgement, including AC-relevant papers that are not SDL"
        >
          AC reporting scope
        </button>
        <button
          type="button"
          aria-pressed={!filter.sdlJudgements.length && !filter.acRelevanceJudgements.length}
          onClick={() => update({
            ...filter,
            sdlJudgements: [],
            acRelevanceJudgements: [],
          })}
        >
          No SDL/AC restriction
        </button>
        <small>
          Strict SDL explicitly excludes AC-relevant papers judged not SDL; the selected judgement values are recorded in the URL and audit.
        </small>
      </div>

      <details className="filter-advanced">
        <summary>Advanced evidence scope</summary>
        <p>Selections within one dimension use OR; different dimensions combine with AND.</p>
        <div className="filter-state-row">
          <label>Full text
            <select
              value={filter.hasFulltext == null ? "" : String(filter.hasFulltext)}
              onChange={(event) => update({ ...filter, hasFulltext: parseTriState(event.target.value) })}
            >
              <option value="">Any</option><option value="true">Available</option><option value="false">Missing</option>
            </select>
          </label>
          <label>Human review
            <select
              value={filter.hasReview == null ? "" : String(filter.hasReview)}
              onChange={(event) => update({ ...filter, hasReview: parseTriState(event.target.value) })}
            >
              <option value="">Any</option><option value="true">Present</option><option value="false">Missing</option>
            </select>
          </label>
          <label className="checkbox"><input type="checkbox" checked={filter.partnerOnly} onChange={(event) => update({ ...filter, partnerOnly: event.target.checked })} />AC partner institution</label>
          <label className="checkbox"><input type="checkbox" checked={filter.acAuthorOnly} onChange={(event) => update({ ...filter, acAuthorOnly: event.target.checked })} />AC author</label>
        </div>
        <div className="filter-facet-grid">
          <FacetPicker label="Country" values={filter.countries} options={enumOptions(options?.countries ?? [])} onChange={(countries) => update({ ...filter, countries })} />
          <FacetPicker label="Institution" values={filter.institutionIds} options={institutionOptions} onChange={(institutionIds) => update({ ...filter, institutionIds })} />
          <FacetPicker label="Topic" values={filter.topicIds} options={(options?.topics ?? []).map((topic) => ({ value: topic.id, label: topic.name }))} onChange={(topicIds) => update({ ...filter, topicIds })} />
          <FacetPicker label="Field" values={filter.fields} options={enumOptions(options?.fields ?? [])} onChange={(fields) => update({ ...filter, fields })} />
          <FacetPicker label="Corpus source" values={filter.corpusSources} options={enumOptions(options?.corpus_sources ?? [])} onChange={(corpusSources) => update({ ...filter, corpusSources })} />
          <FacetPicker label="SDL judgement" values={filter.sdlJudgements} options={enumOptions(SDL_OPTIONS)} onChange={(sdlJudgements) => update({ ...filter, sdlJudgements })} />
          <FacetPicker label="AC relevance" values={filter.acRelevanceJudgements} options={enumOptions(AC_OPTIONS)} onChange={(acRelevanceJudgements) => update({ ...filter, acRelevanceJudgements })} />
          <FacetPicker label="AI for science" values={filter.aiForScienceJudgements} options={enumOptions(AI_OPTIONS)} onChange={(aiForScienceJudgements) => update({ ...filter, aiForScienceJudgements })} />
          <FacetPicker label="Review status" values={filter.reviewStatuses} options={enumOptions(REVIEW_OPTIONS)} onChange={(reviewStatuses) => update({ ...filter, reviewStatuses })} />
        </div>
      </details>
    </section>
  );
}
