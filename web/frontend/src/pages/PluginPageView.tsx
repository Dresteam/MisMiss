import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Loader2 } from 'lucide-react';
import { fetchPluginDetail } from '../api/client';
import type { PluginDetail } from '../api/types';
import { PluginUI } from '../components/PluginUI';
import { Button } from '../components/Button';
import { MarqueeText } from '../components/MarqueeText';

export function PluginPageView() {
  const { name } = useParams<{ name: string }>();
  const [detail, setDetail] = useState<PluginDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!name) return;
    fetchPluginDetail(name).then(setDetail).finally(() => setLoading(false));
  }, [name]);

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  if (!detail) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">插件未找到</p>
        <Link to="/plugin" className="text-primary-500 text-sm mt-2 inline-block">返回插件中心</Link>
      </div>
    );
  }

  if (!detail.ui_schema) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">此插件没有 Web 前端页面</p>
        <Link to="/plugin" className="text-primary-500 text-sm mt-2 inline-block">返回插件中心</Link>
      </div>
    );
  }

  const displayName = detail.display_name || detail.name;

  return (
    <div className="animate-fade-in max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 lg:gap-3 min-w-0">
          <Link to="/plugin" className="btn-ghost btn-sm shrink-0">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg lg:text-xl font-bold text-gray-900 dark:text-white">
              <MarqueeText text={displayName} />
            </h1>
            <p className="text-[10px] lg:text-xs text-gray-500 truncate">{detail.plugin_id} · v{detail.version}</p>
          </div>
        </div>
        <Link to={`/plugin`} className="shrink-0">
          <Button variant="ghost" size="sm" icon={<ExternalLink />}>插件中心</Button>
        </Link>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 lg:p-6">
        <PluginUI schema={detail.ui_schema as any} pluginName={detail.name} />
      </div>
    </div>
  );
}
