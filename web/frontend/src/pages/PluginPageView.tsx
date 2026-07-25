import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Loader2 } from 'lucide-react';
import { fetchPluginDetail } from '../api/client';
import type { PluginDetail } from '../api/types';
import { PluginUI } from '../components/PluginUI';
import { Button } from '../components/Button';

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

  return (
    <div className="animate-fade-in max-w-5xl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Link to="/plugin" className="btn-ghost btn-sm">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
              {detail.display_name || detail.name}
            </h1>
            <p className="text-xs text-gray-500">{detail.plugin_id} · v{detail.version}</p>
          </div>
        </div>
        <Link to={`/plugin`}>
          <Button variant="ghost" size="sm" icon={<ExternalLink />}>插件中心</Button>
        </Link>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
        <PluginUI schema={detail.ui_schema as any} pluginName={detail.name} />
      </div>
    </div>
  );
}
