import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { IconSidebarDashboard, IconSidebarQuota, IconSidebarLogs } from '@/components/ui/icons';
import { authFilesApi } from '@/services/api';
import { apiClient } from '@/services/api/client';
import { useAuthStore } from '@/stores';
import {
  insightsApi,
  type KeeperStatus,
  type ModelPrice,
  type UsageEvent,
  type UsageQuery,
  type UsageSummary,
} from '@/services/api/insights';
import styles from './InsightsPage.module.scss';

const initialQuery: UsageQuery = {
  range: '24h',
  model: '',
  provider: '',
  source: '',
  client: '',
  result: '',
  page: 1,
};
const number = (value: number) => value.toLocaleString(undefined, { maximumFractionDigits: 1 });
const compact = (value: number) =>
  value.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 });
const money = (value: number | null) => (value === null ? '—' : `$${value.toFixed(4)}`);
const clock = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');

export function InsightsPage() {
  const { t } = useTranslation();
  const apiBase = useAuthStore((state) => state.apiBase);
  const serverVersion = useAuthStore((state) => state.serverVersion);
  const api = useMemo(() => insightsApi(apiBase), [apiBase]);
  const [query, setQuery] = useState(initialQuery);
  const [tab, setTab] = useState<'overview' | 'events' | 'pricing'>('overview');
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [status, setStatus] = useState<KeeperStatus | null>(null);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);
  const [prices, setPrices] = useState<ModelPrice[]>([]);
  const [price, setPrice] = useState<ModelPrice>({ model: '', input: 0, output: 0, cache: 0 });
  const [accounts, setAccounts] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const sequence = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++sequence.current;
    const revision = apiClient.getConnectionRevision();
    const current = () =>
      request === sequence.current && revision === apiClient.getConnectionRevision();
    setBusy(true);
    try {
      const [nextSummary, nextStatus, nextEvents, nextPrices] = await Promise.all([
        api.summary(query),
        api.status(),
        api.events(query),
        api.prices(),
      ]);
      if (!current()) return;
      setSummary(nextSummary);
      setStatus(nextStatus);
      setEvents(nextEvents.rows);
      setEventCount(nextEvents.total);
      setPrices(nextPrices);
      setError('');
    } catch {
      if (current()) setError(t('insights.unavailable'));
    } finally {
      if (current()) setBusy(false);
    }
  }, [api, query, t]);

  useEffect(() => {
    setSummary(null);
    setStatus(null);
    setEvents([]);
    setEventCount(0);
    setPrices([]);
    setAccounts(null);
    setError('');
  }, [apiBase]);

  useEffect(() => {
    void refresh();
    const timer = autoRefresh
      ? window.setInterval(() => {
          if (document.visibilityState === 'visible') void refresh();
        }, 15000)
      : undefined;
    return () => {
      sequence.current += 1;
      window.clearInterval(timer);
    };
  }, [refresh, autoRefresh]);

  useEffect(() => {
    let cancelled = false;
    authFilesApi
      .list()
      .then((result) => {
        if (!cancelled) setAccounts(result.files.length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const filter = (key: keyof UsageQuery, value: string) => {
    setQuery((previous) => ({ ...previous, [key]: value, page: 1 }));
    setExpanded(null);
  };
  const total = summary?.total_tokens ?? 0;
  const cacheRatio =
    summary && summary.input_tokens > 0
      ? Math.min(100, (summary.cached_tokens / summary.input_tokens) * 100)
      : null;
  const trend = summary?.trend ?? [];
  const maxTrend = Math.max(1, ...trend.map((point) => point.requests));
  const tokenSegments = summary
    ? [
        {
          name: t('insights.input'),
          value: Math.max(0, summary.input_tokens - summary.cached_tokens),
          color: 'var(--primary-color)',
        },
        {
          name: t('insights.output'),
          value: summary.output_tokens,
          color: 'var(--insight-violet)',
        },
        {
          name: t('insights.cached'),
          value: Math.min(summary.cached_tokens, summary.input_tokens),
          color: 'var(--insight-teal)',
        },
      ]
    : [];
  const segmentTotal = tokenSegments.reduce((sum, item) => sum + item.value, 0);
  let offset = 0;
  const donut = tokenSegments.map((segment) => {
    const length = segmentTotal ? (segment.value / segmentTotal) * 100 : 0;
    const result = { ...segment, length, offset };
    offset += length;
    return result;
  });

  const exportCsv = async () => {
    setNotice('');
    try {
      const response = await api.export(query);
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `cpa-usage-${query.range}.csv`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(t('insights.exportLimit'));
    } catch {
      setNotice(t('insights.actionFailed'));
    }
  };

  const savePrice = async () => {
    const revision = apiClient.getConnectionRevision();
    setBusy(true);
    try {
      await api.savePrice(price);
      if (revision !== apiClient.getConnectionRevision()) return;
      setNotice(t('insights.saved'));
      await refresh();
    } catch {
      if (revision === apiClient.getConnectionRevision()) setNotice(t('insights.actionFailed'));
    } finally {
      if (revision === apiClient.getConnectionRevision()) setBusy(false);
    }
  };

  return (
    <div className={styles.page} data-personal-workspace>
      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>CPA / PERSONAL WORKSPACE</span>
          <h1>
            {t('insights.title')}
            <span className={styles.titleDot}>.</span>
          </h1>
          <p>{t('insights.subtitle')}</p>
          <div className={styles.heroMeta}>
            <span
              className={`${styles.status} ${status?.state === 'running' && !error ? styles.live : ''}`}
            >
              <i aria-hidden="true" />
              {t(`insights.state.${error ? 'offline' : (status?.state ?? 'connecting')}`)}
            </span>
            <span>CPA {serverVersion ?? '—'}</span>
            <span>{t('insights.localFirst')}</span>
          </div>
        </div>
        <div className={styles.heroActions}>
          <label className={styles.autoRefresh}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
            {t('insights.auto')}
          </label>
          <Button
            className={styles.refreshButton}
            variant="secondary"
            onClick={() => void refresh()}
            loading={busy}
          >
            {t('insights.refresh')}
          </Button>
          <Button onClick={() => void exportCsv()} disabled={!summary?.requests}>
            {t('insights.export')}
          </Button>
        </div>
      </header>

      {error && (
        <div className={styles.alert} role="alert">
          <strong>{t('insights.connectionTitle')}</strong>
          <p>{error}</p>
        </div>
      )}
      {status?.state === 'disabled' && (
        <div className={styles.alert} role="status">
          {t('insights.disabled')}
        </div>
      )}
      {notice && (
        <div className={styles.notice} role="status">
          {notice}
          <button type="button" onClick={() => setNotice('')} aria-label={t('insights.dismiss')}>
            ×
          </button>
        </div>
      )}

      <section className={styles.filters} aria-label={t('insights.filters')}>
        <div className={styles.range} role="group" aria-label={t('insights.timeRange')}>
          {['1h', '5h', '24h', '7d', '30d'].map((range) => (
            <button
              key={range}
              type="button"
              aria-pressed={query.range === range}
              onClick={() => filter('range', range)}
            >
              <span className={styles.rangeLong}>{t(`insights.range.${range}`)}</span>
              <span className={styles.rangeShort}>{t(`insights.shortRange.${range}`)}</span>
            </button>
          ))}
        </div>
        <div className={styles.filterFields}>
          {(['model', 'provider', 'source', 'client'] as const).map((field) => (
            <label key={field}>
              <span>{t(`insights.${field}`)}</span>
              <select value={query[field]} onChange={(event) => filter(field, event.target.value)}>
                <option value="">{t('insights.all')}</option>
                {summary?.options[field].map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label>
            <span>{t('insights.result')}</span>
            <select value={query.result} onChange={(event) => filter('result', event.target.value)}>
              <option value="">{t('insights.all')}</option>
              <option value="success">{t('insights.success')}</option>
              <option value="failed">{t('insights.failed')}</option>
            </select>
          </label>
        </div>
      </section>

      <section className={styles.metrics} aria-label={t('insights.metrics')}>
        <article>
          <span>{t('insights.requests')}</span>
          <strong>{summary ? number(summary.requests) : '—'}</strong>
          <small>{t('insights.failures', { count: summary?.failures ?? 0 })}</small>
          <span className={styles.metricGlyph}>
            <IconSidebarDashboard size={21} />
          </span>
        </article>
        <article>
          <span>{t('insights.tokens')}</span>
          <strong>{summary ? compact(total) : '—'}</strong>
          <small>
            {t('insights.reasoning')}: {summary ? compact(summary.reasoning_tokens) : '—'}
          </small>
          <span className={styles.metricGlyph}>↗</span>
        </article>
        <article>
          <span>{t('insights.successRate')}</span>
          <strong>
            {summary?.success_rate == null ? '—' : `${number(summary.success_rate)}%`}
          </strong>
          <small>
            {t('insights.latency')}:{' '}
            {summary?.latency_ms == null ? '—' : `${number(summary.latency_ms / 1000)}s`}
          </small>
          <span className={styles.metricGlyph}>✓</span>
        </article>
        <article>
          <span>{t('insights.cost')}</span>
          <strong>{money(summary?.estimated_cost ?? null)}</strong>
          <small>
            {t('insights.coverage', {
              priced: summary?.priced_requests ?? 0,
              total: summary?.requests ?? 0,
            })}
          </small>
          <span className={styles.metricGlyph}>$</span>
        </article>
      </section>

      <div className={styles.tabs} role="tablist" aria-label={t('insights.views')}>
        {(['overview', 'events', 'pricing'] as const).map((item, index, items) => (
          <button
            type="button"
            role="tab"
            id={`insights-tab-${item}`}
            aria-controls={`insights-panel-${item}`}
            aria-selected={tab === item}
            tabIndex={tab === item ? 0 : -1}
            key={item}
            onClick={() => setTab(item)}
            onKeyDown={(event) => {
              const nextIndex =
                event.key === 'ArrowRight'
                  ? (index + 1) % items.length
                  : event.key === 'ArrowLeft'
                    ? (index + items.length - 1) % items.length
                    : event.key === 'Home'
                      ? 0
                      : event.key === 'End'
                        ? items.length - 1
                        : -1;
              if (nextIndex < 0) return;
              event.preventDefault();
              const next = items[nextIndex];
              setTab(next);
              document.getElementById(`insights-tab-${next}`)?.focus();
            }}
          >
            {t(`insights.tab.${item}`)}
          </button>
        ))}
      </div>

      <section role="tabpanel" id={`insights-panel-${tab}`} aria-labelledby={`insights-tab-${tab}`}>
        {tab === 'overview' && (
          <div className={styles.overview}>
            <article className={`${styles.panel} ${styles.chartPanel}`}>
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.eyebrow}>ACTIVITY</span>
                  <h2>{t('insights.trend')}</h2>
                </div>
                <span className={styles.subtle}>{t('insights.hourly')}</span>
              </div>
              {trend.length ? (
                <>
                  <div
                    className={styles.chart}
                    role="img"
                    aria-label={t('insights.trendDescription', { count: summary?.requests ?? 0 })}
                  >
                    {trend.map((point) => (
                      <div
                        className={styles.barColumn}
                        key={point.timestamp}
                        title={`${clock(point.timestamp)} · ${point.requests} ${t('insights.requests')} · ${point.failures} ${t('insights.failed')}`}
                      >
                        <div
                          className={styles.bar}
                          style={{ height: `${Math.max(2, (point.requests / maxTrend) * 100)}%` }}
                        >
                          <div
                            style={{
                              height: `${point.requests ? (point.failures / point.requests) * 100 : 0}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className={styles.axis}>
                    <span>{clock(trend[0].timestamp)}</span>
                    <span>{clock(trend[trend.length - 1]?.timestamp ?? null)}</span>
                  </div>
                </>
              ) : (
                <div className={styles.chartEmpty}>
                  <IconSidebarDashboard size={36} />
                  <h3>{t('insights.noActivity')}</h3>
                  <p>{t('insights.noActivityHint')}</p>
                </div>
              )}
              <div className={styles.legend}>
                <span>
                  <i />
                  {t('insights.success')}
                </span>
                <span>
                  <i className={styles.failureDot} />
                  {t('insights.failed')}
                </span>
                <span>{t('insights.observedOnly')}</span>
              </div>
            </article>

            <article className={styles.panel}>
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.eyebrow}>TOKEN MIX</span>
                  <h2>{t('insights.tokenMix')}</h2>
                </div>
              </div>
              <div className={styles.tokenMix}>
                <div className={styles.donut}>
                  <svg viewBox="0 0 120 120" aria-hidden="true">
                    <circle
                      cx="60"
                      cy="60"
                      r="45"
                      fill="none"
                      stroke="var(--border-color)"
                      strokeWidth="12"
                    />
                    {donut.map((segment) => (
                      <circle
                        key={segment.name}
                        cx="60"
                        cy="60"
                        r="45"
                        pathLength="100"
                        fill="none"
                        stroke={segment.color}
                        strokeWidth="12"
                        strokeDasharray={`${segment.length} ${100 - segment.length}`}
                        strokeDashoffset={-segment.offset}
                        transform="rotate(-90 60 60)"
                      />
                    ))}
                  </svg>
                  <div>
                    <strong>{cacheRatio === null ? '—' : `${number(cacheRatio)}%`}</strong>
                    <span>{t('insights.cacheRate')}</span>
                  </div>
                </div>
                <div className={styles.tokenLegend}>
                  {tokenSegments.map((segment) => (
                    <div key={segment.name}>
                      <span>
                        <i style={{ background: segment.color }} />
                        {segment.name}
                      </span>
                      <strong>{compact(segment.value)}</strong>
                    </div>
                  ))}
                </div>
              </div>
              <p className={styles.subtle}>{t('insights.reasoningSubset')}</p>
            </article>

            <article className={styles.panel}>
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.eyebrow}>MODEL ACTIVITY</span>
                  <h2>{t('insights.topModels')}</h2>
                </div>
              </div>
              {summary?.models.length ? (
                <div className={styles.modelList}>
                  {summary.models.map((model) => (
                    <button
                      key={model.model}
                      type="button"
                      onClick={() => filter('model', model.model)}
                    >
                      <div>
                        <strong>{model.model}</strong>
                        <span>
                          {number(model.requests)} {t('insights.requests')} ·{' '}
                          {compact(model.total_tokens)} Tokens
                        </span>
                      </div>
                      <div className={styles.modelTrack}>
                        <i
                          style={{ width: `${(model.total_tokens / Math.max(1, total)) * 100}%` }}
                        />
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <p className={styles.emptyText}>{t('insights.noModels')}</p>
              )}
            </article>

            <article className={`${styles.panel} ${styles.quotaPanel}`}>
              <div className={styles.panelHeading}>
                <div>
                  <span className={styles.eyebrow}>ACCOUNTS & QUOTA</span>
                  <h2>{t('insights.quotaTitle')}</h2>
                </div>
                <IconSidebarQuota size={24} />
              </div>
              <p className={styles.quotaLead}>{t('insights.quotaLead')}</p>
              <div className={styles.accountNumber}>
                <strong>{accounts ?? '—'}</strong>
                <span>{t('insights.credentials')}</span>
              </div>
              <p className={styles.subtle}>{t('insights.relayNotice')}</p>
              <div className={styles.quotaLinks}>
                <Link to="/quota">
                  {t('insights.openQuota')} <span aria-hidden="true">↗</span>
                </Link>
                <Link to="/logs">
                  <IconSidebarLogs size={16} />
                  {t('insights.openLogs')}
                </Link>
              </div>
            </article>
          </div>
        )}

        {tab === 'events' && (
          <article className={styles.panel}>
            <div className={styles.panelHeading}>
              <h2>{t('insights.tab.events')}</h2>
              <span>
                {number(eventCount)} {t('insights.requests')}
              </span>
            </div>
            <div
              className={styles.tableScroll}
              role="region"
              tabIndex={0}
              aria-label={t('insights.tab.events')}
            >
              <table>
                <caption className="sr-only">{t('insights.tab.events')}</caption>
                <thead>
                  <tr>
                    {['time', 'model', 'tokens', 'latency', 'result', 'cost', 'details'].map(
                      (field) => (
                        <th key={field} scope="col">
                          {t(`insights.${field}`)}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, index) => {
                    const id = `${event.timestamp}-${index}`;
                    return (
                      <EventRow
                        key={id}
                        event={event}
                        expanded={expanded === id}
                        onToggle={() => setExpanded(expanded === id ? null : id)}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!events.length && <p className={styles.emptyText}>{t('insights.noActivity')}</p>}
            <div className={styles.pagination}>
              <Button
                variant="secondary"
                disabled={query.page <= 1 || busy}
                onClick={() => setQuery((value) => ({ ...value, page: value.page - 1 }))}
              >
                {t('insights.previous')}
              </Button>
              <span>
                {query.page} / {Math.max(1, Math.ceil(eventCount / 25))}
              </span>
              <Button
                variant="secondary"
                disabled={query.page * 25 >= eventCount || busy}
                onClick={() => setQuery((value) => ({ ...value, page: value.page + 1 }))}
              >
                {t('insights.next')}
              </Button>
            </div>
          </article>
        )}

        {tab === 'pricing' && (
          <article className={`${styles.panel} ${styles.pricing}`}>
            <div className={styles.panelHeading}>
              <div>
                <span className={styles.eyebrow}>COST ESTIMATION</span>
                <h2>{t('insights.tab.pricing')}</h2>
              </div>
            </div>
            <p className={styles.subtle}>{t('insights.priceHint')}</p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void savePrice();
              }}
            >
              <label>
                {t('insights.model')}
                <input
                  list="insights-model-options"
                  value={price.model}
                  required
                  maxLength={120}
                  onChange={(event) => {
                    const existing = prices.find((item) => item.model === event.target.value);
                    setPrice(existing ?? { ...price, model: event.target.value });
                  }}
                />
                <datalist id="insights-model-options">
                  {[
                    ...new Set([
                      ...(summary?.options.model ?? []),
                      ...prices.map((item) => item.model),
                    ]),
                  ].map((model) => (
                    <option key={model} value={model} />
                  ))}
                </datalist>
              </label>
              {(['input', 'output', 'cache'] as const).map((field) => (
                <label key={field}>
                  {t(`insights.price.${field}`)}
                  <input
                    type="number"
                    min="0"
                    max="100000"
                    step="any"
                    required
                    value={price[field]}
                    onChange={(event) =>
                      setPrice((previous) => ({ ...previous, [field]: Number(event.target.value) }))
                    }
                  />
                </label>
              ))}
              <Button type="submit" loading={busy}>
                {t('insights.savePrice')}
              </Button>
            </form>
            <div
              className={styles.tableScroll}
              role="region"
              tabIndex={0}
              aria-label={t('insights.tab.pricing')}
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t('insights.model')}</th>
                    {['input', 'output', 'cache'].map((field) => (
                      <th key={field} scope="col">
                        {t(`insights.price.${field}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {prices.map((item) => (
                    <tr key={item.model}>
                      <td>
                        <button className={styles.textButton} onClick={() => setPrice(item)}>
                          {item.model}
                        </button>
                      </td>
                      <td>${item.input}</td>
                      <td>${item.output}</td>
                      <td>${item.cache}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!prices.length && <p className={styles.emptyText}>{t('insights.noPrices')}</p>}
          </article>
        )}
      </section>

      <footer className={styles.footer}>
        <span>
          <i aria-hidden="true" />
          {t('insights.storage', {
            count: summary?.stored_records ?? 0,
            size: ((summary?.database_bytes ?? 0) / 1048576).toFixed(1),
          })}
        </span>
        <span>{t('insights.retention')}</span>
        <span>
          {t('insights.updated')}: {clock(status?.last_collected ?? null)}
        </span>
      </footer>
    </div>
  );
}

function EventRow({
  event,
  expanded,
  onToggle,
}: {
  event: UsageEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <tr>
        <td className={styles.time}>{clock(event.timestamp)}</td>
        <td>
          <strong>{event.model}</strong>
          <small className={styles.provider}>{event.provider}</small>
        </td>
        <td>{number(event.total_tokens)}</td>
        <td>{number(event.latency_ms / 1000)}s</td>
        <td>
          <span className={`${styles.result} ${event.failed ? styles.failed : ''}`}>
            {t(event.failed ? 'insights.failed' : 'insights.success')}
          </span>
        </td>
        <td>
          {event.estimated_cost === null ? t('insights.unpriced') : money(event.estimated_cost)}
        </td>
        <td>
          <button
            type="button"
            className={styles.textButton}
            aria-expanded={expanded}
            onClick={onToggle}
          >
            {t(expanded ? 'insights.collapse' : 'insights.details')}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7}>
            <dl className={styles.eventDetail}>
              {(
                [
                  'input_tokens',
                  'output_tokens',
                  'reasoning_tokens',
                  'cached_tokens',
                  'source',
                  'client',
                  'endpoint',
                  'alias',
                ] as const
              ).map((field) => (
                <div key={field}>
                  <dt>{t(`insights.field.${field}`)}</dt>
                  <dd>{event[field]}</dd>
                </div>
              ))}
            </dl>
          </td>
        </tr>
      )}
    </>
  );
}
