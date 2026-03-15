import { useEffect, useState } from 'react';
import type { PluginInfo } from '../types';
import { StageType } from '../types';
import { plugins } from '../api/client';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function PluginMarketplacePage() {
  const [pluginList, setPluginList] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | StageType>('all');

  useEffect(() => {
    loadPlugins();
  }, []);

  async function loadPlugins() {
    try {
      setLoading(true);
      const data = await plugins.list();
      setPluginList(data);
    } catch {
      // Demo data
      setPluginList([
        { name: 'rest-api-collector', version: '1.2.0', type: StageType.COLLECT, description: 'Collect data from REST APIs with support for authentication, pagination, and rate limiting.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'file-watcher', version: '1.0.0', type: StageType.COLLECT, description: 'Monitor directories for new files using inotify (Linux) or polling (cross-platform).', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'database-poller', version: '1.1.0', type: StageType.COLLECT, description: 'Poll database tables for changes using timestamp tracking or sequence IDs.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'mqtt-collector', version: '0.9.0', type: StageType.COLLECT, description: 'Subscribe to MQTT topics for real-time IoT data ingestion.', author: 'vessel-community', license: 'MIT', runtime: 'python', installed: false, icon_url: null },
        { name: 'kafka-consumer', version: '0.8.0', type: StageType.COLLECT, description: 'Consume messages from Apache Kafka topics with consumer group management.', author: 'vessel-community', license: 'Apache-2.0', runtime: 'python', installed: false, icon_url: null },
        { name: 'anomaly-detector', version: '1.0.0', type: StageType.ALGORITHM, description: 'Statistical anomaly detection with z-score, IQR, and modified z-score methods.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'data-transformer', version: '1.0.0', type: StageType.ALGORITHM, description: 'Transform data between JSON, CSV, XML formats with configurable mapping rules.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'dedup-filter', version: '1.0.0', type: StageType.ALGORITHM, description: 'Remove duplicate records based on configurable keys and time windows.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'ml-classifier', version: '0.5.0', type: StageType.ALGORITHM, description: 'Machine learning classification using scikit-learn models. Supports custom model loading.', author: 'vessel-community', license: 'MIT', runtime: 'python', installed: false, icon_url: null },
        { name: 's3-uploader', version: '1.0.0', type: StageType.TRANSFER, description: 'Upload data to Amazon S3 with support for multipart upload, encryption, and compression.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'database-writer', version: '1.0.0', type: StageType.TRANSFER, description: 'Write data to PostgreSQL, MySQL, or MSSQL with upsert and batch insert support.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: true, icon_url: null },
        { name: 'webhook-sender', version: '1.0.0', type: StageType.TRANSFER, description: 'Send results to external HTTP webhook endpoints with retry and backoff.', author: 'vessel-core', license: 'Apache-2.0', runtime: 'python', installed: false, icon_url: null },
        { name: 'elasticsearch-writer', version: '0.7.0', type: StageType.TRANSFER, description: 'Index documents into Elasticsearch with configurable mappings and bulk operations.', author: 'vessel-community', license: 'Apache-2.0', runtime: 'python', installed: false, icon_url: null },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleInstall(name: string) {
    try {
      await plugins.install(name);
    } catch {
      // Demo mode
    }
    setPluginList((prev) =>
      prev.map((p) => (p.name === name ? { ...p, installed: true } : p))
    );
  }

  async function handleUninstall(name: string) {
    try {
      await plugins.uninstall(name);
    } catch {
      // Demo mode
    }
    setPluginList((prev) =>
      prev.map((p) => (p.name === name ? { ...p, installed: false } : p))
    );
  }

  const typeColor: Record<StageType, { bg: string; text: string; iconBg: string }> = {
    [StageType.COLLECT]: { bg: 'bg-blue-50', text: 'text-blue-700', iconBg: 'bg-blue-500' },
    [StageType.ALGORITHM]: { bg: 'bg-purple-50', text: 'text-purple-700', iconBg: 'bg-purple-500' },
    [StageType.TRANSFER]: { bg: 'bg-emerald-50', text: 'text-emerald-700', iconBg: 'bg-emerald-500' },
  };

  const filteredPlugins = filter === 'all'
    ? pluginList
    : pluginList.filter((p) => p.type === filter);

  if (loading) return <LoadingSpinner message="Loading plugins..." />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Plugin Marketplace</h1>
        <p className="mt-1 text-sm text-slate-500">
          Browse and install plugins to extend Vessel capabilities
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2">
        {(['all', StageType.COLLECT, StageType.ALGORITHM, StageType.TRANSFER] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${
              filter === f
                ? 'bg-vessel-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {f === 'all' ? 'All' : f}
          </button>
        ))}
      </div>

      {/* Plugin Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filteredPlugins.map((plugin) => {
          const colors = typeColor[plugin.type];
          return (
            <div key={plugin.name} className="card p-5">
              <div className="flex items-start justify-between">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${colors.iconBg}`}>
                  <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 01-.657.643 48.39 48.39 0 01-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 01-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 00-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 01-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 00.657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 01-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 005.427-.63 48.05 48.05 0 00.582-4.717.532.532 0 00-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.959.401v0a.656.656 0 00.658-.663 48.422 48.422 0 00-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 01-.61-.58v0z" />
                  </svg>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${colors.bg} ${colors.text}`}>
                  {plugin.type}
                </span>
              </div>

              <h3 className="mt-3 text-sm font-semibold text-slate-900">{plugin.name}</h3>
              <p className="mt-1 line-clamp-2 text-xs text-slate-500">{plugin.description}</p>

              <div className="mt-3 flex items-center gap-2 text-[10px] text-slate-400">
                <span>v{plugin.version}</span>
                <span>&middot;</span>
                <span>{plugin.author}</span>
                <span>&middot;</span>
                <span>{plugin.runtime}</span>
                <span>&middot;</span>
                <span>{plugin.license}</span>
              </div>

              <div className="mt-4 border-t border-slate-100 pt-3">
                {plugin.installed ? (
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1 text-xs font-medium text-emerald-600">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Installed
                    </span>
                    <button
                      onClick={() => handleUninstall(plugin.name)}
                      className="text-xs text-slate-400 hover:text-red-600"
                    >
                      Uninstall
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleInstall(plugin.name)}
                    className="btn-primary w-full justify-center text-xs"
                  >
                    Install
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
