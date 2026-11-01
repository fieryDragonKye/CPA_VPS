import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { AutocompleteInput } from '@/components/ui/AutocompleteInput';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { useAuthStore } from '@/stores';
import { apiClient } from '@/services/api/client';
import { insightsApi, type Credential, type UsageQuery } from '@/services/api/insights';
import { formatEstimatedCost, formatTtft } from '@/features/insights/metrics';
import shared from '@/features/insights/InsightsPage.module.scss';
import styles from './CredentialsPage.module.scss';
import { resolveCredentialSelection, sortCredentials, type CredentialSort } from './logic';
import { useCredentialResource } from './useCredentialResource';

const count = (value: number | null | undefined) => (value == null ? '—' : value.toLocaleString());
const percent = (value: number | null | undefined) =>
  value == null ? '—' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
const clock = (value?: string | null) => (value ? new Date(value).toLocaleString() : '—');

export function CredentialsPage() {
  const apiBase = useAuthStore((s) => s.apiBase);
  const hasKey = Boolean(useAuthStore((s) => s.managementKey));
  const revision = apiClient.getConnectionRevision();
  return <CredentialWorkspace key={`${apiBase}:${revision}:${hasKey}`} apiBase={apiBase} />;
}

function CredentialWorkspace({ apiBase }: { apiBase: string }) {
  const { t } = useTranslation();
  const api = useMemo(() => insightsApi(apiBase), [apiBase]);
  const [mode, setMode] = useState<'details' | 'compare'>('details');
  const [pane, setPane] = useState<'trend' | 'models' | 'events'>('trend');
  const [range, setRange] = useState('24h');
  const [group, setGroup] = useState('');
  const [selected, setSelected] = useState('');
  const [search, setSearch] = useState('');
  const [model, setModel] = useState('');
  const [modelDraft, setModelDraft] = useState('');
  const [result, setResult] = useState('');
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [auto, setAuto] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [sort, setSort] = useState<CredentialSort>('total_tokens');
  const [ascending, setAscending] = useState(false);
  const [editing, setEditing] = useState<Credential | null>(null);
  const [notice, setNotice] = useState('');
  const [exporting, setExporting] = useState(false);

  const loadRegistry = useCallback(
    async (signal: AbortSignal) => {
      const [credentials, status] = await Promise.all([
        api.credentials(signal),
        api.status(signal).catch(() => null),
      ]);
      return { credentials, status };
    },
    [api]
  );
  const registry = useCredentialResource('registry', loadRegistry, true, reload);
  const credentials = useMemo(() => registry.data?.credentials ?? [], [registry.data]);
  const groups = [...new Set(credentials.map((c) => c.group_name).filter(Boolean))].sort();
  const visible = useMemo(
    () =>
      credentials.filter(
        (c) => (showArchived || !c.archived) && (!group || c.group_name === group)
      ),
    [credentials, showArchived, group]
  );
  const options = visible.filter(
    (c) =>
      c.id === selected ||
      `${c.alias} ${c.provider}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())
  );
  const credential = credentials.find((c) => c.id === selected);
  const validSelection = selected === 'unlinked' ? !group : visible.some((c) => c.id === selected);

  useEffect(() => {
    if (mode === 'compare' || !registry.data || validSelection) return;
    setSelected((current) => resolveCredentialSelection(current, visible, !group));
  }, [mode, registry.data, validSelection, visible, group]);
  useEffect(() => {
    setPage(1);
  }, [selected]);
  useEffect(() => {
    if (modelDraft.trim() === model) return;
    const timer = window.setTimeout(() => {
      setModel(modelDraft.trim());
      setPage(1);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [modelDraft, model]);

  const queryCredential = mode === 'details' ? selected : '';
  const query = useMemo<UsageQuery>(
    () => ({
      range,
      group_name: group,
      model,
      result,
      provider: '',
      source: '',
      client: '',
      page: 1,
      credential_id: queryCredential,
    }),
    [range, group, model, result, queryCredential]
  );
  const queryKey = JSON.stringify(query);
  const enabled = mode === 'compare' || validSelection;
  const loadReport = useCallback(
    (signal: AbortSignal) => api.credentialReport(query, signal),
    [api, query]
  );
  const report = useCredentialResource(queryKey, loadReport, enabled, reload);
  const loadSummary = useCallback(
    (signal: AbortSignal) => api.summary(query, signal),
    [api, query]
  );
  const summary = useCredentialResource(
    queryKey,
    loadSummary,
    mode === 'details' && validSelection && pane !== 'events',
    reload
  );
  const loadEvents = useCallback(
    (signal: AbortSignal) => api.events({ ...query, page }, signal),
    [api, query, page]
  );
  const events = useCredentialResource(
    `${queryKey}:${page}`,
    loadEvents,
    mode === 'details' && validSelection && pane === 'events',
    reload
  );
  const busy = registry.busy || report.busy || summary.busy || events.busy;
  const busyRef = useRef(busy);
  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);
  useEffect(() => {
    if (!auto) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !busyRef.current) setReload((n) => n + 1);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [auto]);

  const choose = (id: string) => {
    setSelected(id);
    setPage(1);
    setMode('details');
    if (id === 'unlinked') setGroup('');
  };
  const stats =
    selected === 'unlinked'
      ? report.data?.unlinked
      : report.data?.credentials.find((c) => c.id === selected);
  const status = registry.data?.status;
  const rows = sortCredentials(
    (report.data?.credentials ?? []).filter((c) => showArchived || !c.archived),
    sort,
    ascending
  );
  const error = registry.error || report.error || summary.error || events.error;
  const exportCsv = async () => {
    const revision = apiClient.getConnectionRevision();
    setExporting(true);
    try {
      const response = await api.export({ ...query, page });
      if (revision !== apiClient.getConnectionRevision()) return;
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `cpa-credentials-${range}.csv`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(t('insights.exportLimit'));
    } catch {
      if (revision === apiClient.getConnectionRevision()) setNotice(t('insights.actionFailed'));
    } finally {
      if (revision === apiClient.getConnectionRevision()) setExporting(false);
    }
  };
  const switchTab = (next: 'details' | 'compare') => {
    setMode(next);
    setPage(1);
  };
  const changeModel = (value: string) => {
    setModelDraft(value);
    setModel(value);
    setPage(1);
  };

  return (
    <div className={`${shared.page} ${styles.page}`} data-personal-workspace>
      <header className={shared.hero}>
        <div>
          <span className={shared.eyebrow}>CPA / PERSONAL WORKSPACE</span>
          <h1>
            {t('credentialAnalytics.title')}
            <span className={shared.titleDot}>.</span>
          </h1>
          <p>{t('credentialAnalytics.subtitle')}</p>
          <div className={shared.heroMeta}>
            <span>{t('credentialAnalytics.executionBasis')}</span>
            <span>{t('credentialAnalytics.metadataOnly')}</span>
            <Link to="/">{t('credentialAnalytics.openOverview')}</Link>
          </div>
        </div>
        <div className={shared.heroActions}>
          <label className={shared.autoRefresh}>
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            {t('insights.auto')}
          </label>
          <Button variant="secondary" loading={busy} onClick={() => setReload((n) => n + 1)}>
            {t('insights.refresh')}
          </Button>
          <Button
            loading={exporting}
            disabled={mode !== 'details' || !stats?.requests || busy}
            onClick={() => void exportCsv()}
          >
            {t('insights.export')}
          </Button>
        </div>
      </header>
      {error && (
        <div className={shared.alert} role="alert">
          {t('credentialAnalytics.unavailable')}
        </div>
      )}
      {notice && (
        <div className={shared.notice} role="status">
          {notice}
          <button type="button" onClick={() => setNotice('')} aria-label={t('insights.dismiss')}>
            ×
          </button>
        </div>
      )}
      <div className={shared.tabs} role="tablist" aria-label={t('credentialAnalytics.views')}>
        {(['details', 'compare'] as const).map((tab, i, tabs) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`credential-tab-${tab}`}
            aria-selected={mode === tab}
            aria-controls={`credential-panel-${tab}`}
            tabIndex={mode === tab ? 0 : -1}
            onClick={() => switchTab(tab)}
            onKeyDown={(e) => {
              const next =
                e.key === 'Home'
                  ? 0
                  : e.key === 'End'
                    ? tabs.length - 1
                    : e.key === 'ArrowRight'
                      ? (i + 1) % tabs.length
                      : e.key === 'ArrowLeft'
                        ? (i + tabs.length - 1) % tabs.length
                        : -1;
              if (next >= 0) {
                e.preventDefault();
                switchTab(tabs[next]);
                document.getElementById(`credential-tab-${tabs[next]}`)?.focus();
              }
            }}
          >
            {t(`credentialAnalytics.${tab}`)}
          </button>
        ))}
      </div>
      <section className={styles.filters} aria-label={t('insights.filters')}>
        <label>
          {t('insights.timeRange')}
          <Select
            className={styles.select}
            ariaLabel={t('insights.timeRange')}
            value={range}
            onChange={(value) => {
              setRange(value);
              setPage(1);
            }}
            options={['1h', '5h', '24h', '7d', '30d'].map((r) => ({
              value: r,
              label: t(`insights.range.${r}`),
            }))}
          />
        </label>
        <label>
          {t('credentialAnalytics.group')}
          <Select
            className={styles.select}
            ariaLabel={t('credentialAnalytics.group')}
            value={group}
            onChange={(value) => {
              setGroup(value);
              setSelected('');
              setPage(1);
            }}
            options={[
              { value: '', label: t('insights.all') },
              ...groups.map((g) => ({ value: g, label: g })),
            ]}
          />
        </label>
        {mode === 'details' && (
          <>
            <label>
              {t('credentialAnalytics.search')}
              <input
                type="search"
                value={search}
                placeholder={t('credentialAnalytics.searchHint')}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              {t('credentialAnalytics.credential')}
              <Select
                className={styles.select}
                ariaLabel={t('credentialAnalytics.credential')}
                placeholder={t('credentialAnalytics.choose')}
                value={validSelection ? selected : ''}
                onChange={choose}
                options={[
                  ...options.map((c) => ({
                    value: c.id,
                    label: `${c.alias} · ${c.provider}${c.archived ? ` · ${t('credentialAnalytics.archived')}` : ''}${!c.configured ? ` · ${t('credentialAnalytics.removed')}` : ''}`,
                  })),
                  ...(!group
                    ? [{ value: 'unlinked', label: t('credentialAnalytics.unlinked') }]
                    : []),
                ]}
              />
            </label>
          </>
        )}
        <label>
          {t('insights.model')}
          <AutocompleteInput
            id="credential-model"
            variant="select"
            ariaLabel={t('insights.model')}
            wrapperClassName={styles.modelAutocomplete}
            value={modelDraft}
            onChange={setModelDraft}
            placeholder={t('credentialAnalytics.modelHint')}
            options={summary.data?.options.model ?? []}
          />
        </label>
        <label>
          {t('insights.result')}
          <Select
            className={styles.select}
            ariaLabel={t('insights.result')}
            value={result}
            onChange={(value) => {
              setResult(value);
              setPage(1);
            }}
            options={[
              { value: '', label: t('insights.all') },
              { value: 'success', label: t('insights.success') },
              { value: 'failed', label: t('insights.failed') },
            ]}
          />
        </label>
        <label className={styles.check}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          {t('credentialAnalytics.showArchived')}
        </label>
      </section>
      <section
        role="tabpanel"
        id={`credential-panel-${mode}`}
        aria-labelledby={`credential-tab-${mode}`}
        aria-busy={busy}
      >
        {mode === 'compare' ? (
          <article className={shared.panel}>
            <div className={`${shared.panelHeading} ${styles.compareHeading}`}>
              <h2>{t('credentialAnalytics.compare')}</h2>
              <div className={styles.sort}>
                <label>
                  {t('credentialAnalytics.sort')}
                  <Select
                    className={styles.select}
                    ariaLabel={t('credentialAnalytics.sort')}
                    value={sort}
                    onChange={(value) => setSort(value as CredentialSort)}
                    options={(
                      [
                        'total_tokens',
                        'requests',
                        'estimated_cost',
                        'success_rate',
                        'ttft_p50_ms',
                      ] as const
                    ).map((k) => ({ value: k, label: t(`credentialAnalytics.sortFields.${k}`) }))}
                  />
                </label>
                <Button variant="secondary" size="sm" onClick={() => setAscending((v) => !v)}>
                  {t(
                    ascending ? 'credentialAnalytics.ascending' : 'credentialAnalytics.descending'
                  )}
                </Button>
              </div>
            </div>
            <p className={shared.subtle}>{t('credentialAnalytics.comparisonHint')}</p>
            <div
              className={shared.tableScroll}
              role="region"
              tabIndex={0}
              aria-label={t('credentialAnalytics.compare')}
            >
              <table className={styles.table}>
                <thead>
                  <tr>
                    {[
                      'credential',
                      'executions',
                      'tokens',
                      'successRate',
                      'ttft',
                      'cost',
                      'lastUsed',
                    ].map((k) => (
                      <th key={k} scope="col">
                        {t(
                          k === 'ttft'
                            ? 'credentialAnalytics.sortFields.ttft_p50_ms'
                            : `credentialAnalytics.${k}`
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <th scope="row">
                        <button
                          type="button"
                          className={styles.linkButton}
                          onClick={() => choose(row.id)}
                        >
                          {row.alias}
                        </button>
                        <small>
                          {row.provider} · {row.group_name || t('credentialAnalytics.ungrouped')}
                          {row.archived ? ` · ${t('credentialAnalytics.archived')}` : ''}
                        </small>
                      </th>
                      <td>{count(row.requests)}</td>
                      <td>{count(row.total_tokens)}</td>
                      <td>{percent(row.success_rate)}</td>
                      <td>
                        {formatTtft(row.ttft_p50_ms)}
                        <small>
                          {t('credentialAnalytics.samples', { count: row.ttft_samples })}
                        </small>
                      </td>
                      <td>{formatEstimatedCost(row.estimated_cost)}</td>
                      <td>{clock(row.last_used)}</td>
                    </tr>
                  ))}
                  {!group && report.data && (
                    <tr>
                      <th scope="row">
                        <button
                          type="button"
                          className={styles.linkButton}
                          onClick={() => choose('unlinked')}
                        >
                          {t('credentialAnalytics.unlinked')}
                        </button>
                      </th>
                      <td>{count(report.data.unlinked.requests)}</td>
                      <td>{count(report.data.unlinked.total_tokens)}</td>
                      <td>{percent(report.data.unlinked.success_rate)}</td>
                      <td>—</td>
                      <td>{formatEstimatedCost(report.data.unlinked.estimated_cost)}</td>
                      <td>{clock(report.data.unlinked.last_used)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {!rows.length && !busy && (
              <p className={styles.empty}>{t('credentialAnalytics.noCredentials')}</p>
            )}
          </article>
        ) : (
          <>
            <div className={styles.identity}>
              <div>
                <h2>
                  {selected === 'unlinked'
                    ? t('credentialAnalytics.unlinked')
                    : (credential?.alias ?? t('credentialAnalytics.choose'))}
                </h2>
                <p>
                  {credential
                    ? `${credential.provider} · ${credential.group_name || t('credentialAnalytics.ungrouped')} · ${credential.id.slice(0, 8)}`
                    : t('credentialAnalytics.legacyHint')}
                </p>
              </div>
              {credential && (
                <Button variant="secondary" onClick={() => setEditing(credential)}>
                  {t('credentialAnalytics.edit')}
                </Button>
              )}
            </div>
            {stats?.requests === 0 && !busy && (
              <p className={styles.empty}>{t('credentialAnalytics.zeroUsage')}</p>
            )}
            <div className={shared.metrics}>
              <Metric
                label={t('credentialAnalytics.executions')}
                value={count(stats?.requests)}
                hint={stats ? t('insights.failures', { count: stats.failures }) : '—'}
              />
              <Metric
                label={t('insights.tokens')}
                value={count(stats?.total_tokens)}
                hint={t('credentialAnalytics.reportedOnly')}
              />
              <Metric
                label={t('credentialAnalytics.successRate')}
                value={percent(stats?.success_rate)}
                hint={t('credentialAnalytics.executionBasis')}
              />
              <Metric
                label={t('insights.cost')}
                value={formatEstimatedCost(stats?.estimated_cost)}
                hint={
                  stats
                    ? t('credentialAnalytics.priced', {
                        priced: stats.priced_requests,
                        total: stats.requests,
                      })
                    : '—'
                }
              />
            </div>
            <div className={styles.secondary}>
              <Metric
                label={t('credentialAnalytics.ttft')}
                value={`${formatTtft(stats?.ttft_p50_ms)} / ${formatTtft(stats?.ttft_p95_ms)}`}
                hint={stats ? t('credentialAnalytics.samples', { count: stats.ttft_samples }) : '—'}
              />
              <Metric
                label={t('credentialAnalytics.duration')}
                value={`${formatTtft(stats?.latency_p50_ms)} / ${formatTtft(stats?.latency_p95_ms)}`}
                hint={
                  stats ? t('credentialAnalytics.samples', { count: stats.latency_samples }) : '—'
                }
              />
              <Metric
                label={t('insights.cacheRate')}
                value={
                  stats &&
                  stats.requests > 0 &&
                  stats.accounted_requests === stats.requests &&
                  summary.data &&
                  summary.data.input_tokens > 0
                    ? percent(
                        Math.min(
                          100,
                          (summary.data.cached_tokens / summary.data.input_tokens) * 100
                        )
                      )
                    : '—'
                }
                hint={t('credentialAnalytics.cacheHint')}
              />
            </div>
            <p className={styles.hint}>
              {t('credentialAnalytics.ttftHint')}
              {stats && stats.ttft_samples < 20 ? ` ${t('credentialAnalytics.lowSamples')}` : ''}
            </p>
            {selected === 'unlinked' && (
              <p className={styles.hint}>{t('credentialAnalytics.legacyHint')}</p>
            )}
            <article className={shared.panel}>
              <div
                className={styles.panes}
                role="group"
                aria-label={t('credentialAnalytics.breakdown')}
              >
                {(['trend', 'models', 'events'] as const).map((p) => (
                  <button
                    type="button"
                    key={p}
                    aria-pressed={pane === p}
                    onClick={() => setPane(p)}
                  >
                    {t(`credentialAnalytics.${p}`)}
                  </button>
                ))}
              </div>
              {pane === 'trend' && (
                <>
                  <div
                    className={styles.trend}
                    role="img"
                    aria-label={t('credentialAnalytics.trend')}
                  >
                    {(summary.data?.trend ?? []).map((point) => (
                      <div
                        key={point.timestamp}
                        title={`${clock(point.timestamp)} · ${point.requests}`}
                        style={{
                          height: `${Math.max(2, (point.requests / Math.max(1, ...(summary.data?.trend.map((p) => p.requests) ?? []))) * 100)}%`,
                        }}
                      />
                    ))}
                  </div>
                  <p className={shared.subtle}>{t('insights.hourly')}</p>
                  {!summary.data?.trend.length && !busy && (
                    <p className={styles.empty}>{t('credentialAnalytics.noRecords')}</p>
                  )}
                </>
              )}
              {pane === 'models' && (
                <div className={styles.models}>
                  {summary.data?.models.map((m) => (
                    <button type="button" key={m.model} onClick={() => changeModel(m.model)}>
                      <span>{m.model}</span>
                      <strong>{count(m.total_tokens)} Token</strong>
                      <small>
                        {t('credentialAnalytics.executions')}: {count(m.requests)}
                      </small>
                    </button>
                  ))}
                  {!summary.data?.models.length && !busy && (
                    <p className={styles.empty}>{t('credentialAnalytics.noRecords')}</p>
                  )}
                </div>
              )}
              {pane === 'events' && (
                <>
                  <div
                    className={shared.tableScroll}
                    role="region"
                    tabIndex={0}
                    aria-label={t('credentialAnalytics.events')}
                  >
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          {['time', 'model', 'tokens', 'result', 'ttft', 'duration', 'cost'].map(
                            (k) => (
                              <th key={k} scope="col">
                                {t(`insights.${k}`)}
                              </th>
                            )
                          )}
                          <th scope="col">{t('credentialAnalytics.accounting')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {events.data?.rows.map((e, i) => (
                          <tr key={`${e.timestamp}-${i}`}>
                            <td>{clock(e.timestamp)}</td>
                            <td>{e.model}</td>
                            <td>{count(e.total_tokens)}</td>
                            <td>{t(e.failed ? 'insights.failed' : 'insights.success')}</td>
                            <td>{formatTtft(e.ttft_ms)}</td>
                            <td>{formatTtft(e.latency_ms)}</td>
                            <td>{formatEstimatedCost(e.estimated_cost)}</td>
                            <td>
                              {t(
                                `credentialAnalytics.quality.${['complete', 'inconsistent', 'unclassified'].includes(e.token_quality ?? '') ? e.token_quality : 'legacy'}`
                              )}
                              {e.association_state === 'ambiguous' && (
                                <small>{t('credentialAnalytics.ambiguous')}</small>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {!events.data?.rows.length && !busy && (
                    <p className={styles.empty}>{t('credentialAnalytics.noRecords')}</p>
                  )}
                  <div className={shared.pagination}>
                    <Button
                      variant="secondary"
                      disabled={page <= 1 || busy}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      {t('insights.previous')}
                    </Button>
                    <span>
                      {page} / {Math.max(1, Math.ceil((events.data?.total ?? 0) / 25))}
                    </span>
                    <Button
                      variant="secondary"
                      disabled={page * 25 >= (events.data?.total ?? 0) || busy}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      {t('insights.next')}
                    </Button>
                  </div>
                </>
              )}
            </article>
            {stats && (
              <p className={styles.hint}>
                {t('credentialAnalytics.coverage', {
                  indexed: stats.indexed_requests,
                  executions: stats.execution_identified_requests,
                  accounted: stats.accounted_requests,
                  total: stats.requests,
                })}
              </p>
            )}
          </>
        )}
      </section>
      <footer className={styles.footer}>
        <span>
          {t('credentialAnalytics.lastPoll')}: {clock(status?.last_poll)}
        </span>
        <span>
          {t('insights.updated')}: {clock(status?.last_collected)}
        </span>
        <span>{t(`insights.state.${error ? 'offline' : (status?.state ?? 'connecting')}`)}</span>
        {status?.metadata_error && (
          <span role="status">{t('credentialAnalytics.metadataError')}</span>
        )}
        <p>
          {t('credentialAnalytics.costHint')} <Link to="/quota">{t('insights.openQuota')}</Link>
        </p>
      </footer>
      {editing && (
        <CredentialEditor
          credential={editing}
          api={api}
          onClose={() => setEditing(null)}
          onSaved={(archived) => {
            setShowArchived((v) => v || archived);
            setGroup('');
            setEditing(null);
            setReload((n) => n + 1);
            setNotice(t('credentialAnalytics.saved'));
          }}
        />
      )}
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: ReactNode; hint: ReactNode }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

function CredentialEditor({
  credential,
  api,
  onClose,
  onSaved,
}: {
  credential: Credential;
  api: ReturnType<typeof insightsApi>;
  onClose: () => void;
  onSaved: (archived: boolean) => void;
}) {
  const { t } = useTranslation();
  const [alias, setAlias] = useState(credential.alias);
  const [group, setGroup] = useState(credential.group_name);
  const [archived, setArchived] = useState(Boolean(credential.archived));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const save = async () => {
    const revision = apiClient.getConnectionRevision();
    setSaving(true);
    setError(false);
    try {
      await api.editCredential({
        id: credential.id,
        alias: alias.trim(),
        group_name: group.trim(),
        archived,
      });
      if (revision === apiClient.getConnectionRevision()) onSaved(archived);
    } catch {
      if (revision === apiClient.getConnectionRevision()) setError(true);
    } finally {
      if (revision === apiClient.getConnectionRevision()) setSaving(false);
    }
  };
  return (
    <Modal
      open
      title={t('credentialAnalytics.edit')}
      onClose={onClose}
      closeDisabled={saving}
      footer={
        <>
          <Button variant="secondary" disabled={saving} onClick={onClose}>
            {t('credentialAnalytics.cancel')}
          </Button>
          <Button loading={saving} disabled={!alias.trim()} onClick={() => void save()}>
            {t('credentialAnalytics.save')}
          </Button>
        </>
      }
    >
      <p className={styles.hint}>{t('credentialAnalytics.metadataOnly')}</p>
      <Input
        label={t('credentialAnalytics.alias')}
        value={alias}
        maxLength={80}
        disabled={saving}
        onChange={(e) => setAlias(e.target.value)}
      />
      <Input
        label={t('credentialAnalytics.group')}
        value={group}
        maxLength={80}
        disabled={saving}
        onChange={(e) => setGroup(e.target.value)}
      />
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={archived}
          disabled={saving}
          onChange={(e) => setArchived(e.target.checked)}
        />
        {t('credentialAnalytics.archive')}
      </label>
      {error && (
        <p role="alert" className={shared.alert}>
          {t('insights.actionFailed')}
        </p>
      )}
    </Modal>
  );
}
