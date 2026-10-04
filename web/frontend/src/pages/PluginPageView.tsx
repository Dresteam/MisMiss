import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Loader2 } from 'lucide-react';
import { fetchAccountPluginDetail } from '../api/client';
import type { PluginDetail } from '../api/types';
import { PluginUI } from '../components/PluginUI';
import { Button } from '../components/Button';
import { MarqueeText } from '../components/MarqueeText';
import { useAuth } from '../hooks/useAuth';
import { useGuideActive } from '../components/GuideOverlay';
import { makeDemoPluginDetail } from './AccountDetailPage';

export function PluginPageView() {
  const { id, name } = useParams<{ id: string; name: string }>();
  const auth = useAuth();
  // 账户自己的路由无 :id 参数,回退到登录账户自身
  const accountId = id ? Number(id) : (auth.accountId ?? 0);
  // 返回插件界面:账户 → 插件页;管理端 → 账户详情的插件 Tab(?tab=plugins)
  const backPath = auth.role === 'account'
    ? '/account/plugins'
    : `/account/${accountId}?tab=plugins`;
  // 指引期间能走到这一页，只可能是从演示卡片点进来的 —— 那会儿插件名是假的。
  // 取**挂载那一刻**的值就定死：指引一点「完成」，guideActive 会立刻翻成 false，
  // 但用户人还站在这张假插件页上，这时候去拉真详情只会 404、页面变成「插件未找到」
  const guideActive = useGuideActive();
  const [demo] = useState(guideActive);
  const [detail, setDetail] = useState<PluginDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!name || !accountId) return;
    // 演示态：不拉详情 —— 演示插件名在账户里不存在，拉就是 404
    if (demo) { setDetail(makeDemoPluginDetail(name)); setLoading(false); return; }
    fetchAccountPluginDetail(accountId, name).then(setDetail).finally(() => setLoading(false));
  }, [name, accountId, demo]);

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  if (!detail) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">插件未找到</p>
        <Link to={backPath} className="text-primary-500 text-sm mt-2 inline-block">返回账户</Link>
      </div>
    );
  }

  const displayName = detail.display_name || detail.name;

  /** 页头。下面几个分支共用同一份，别抄第二遍 */
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
      <div className="flex items-center gap-2 lg:gap-3 min-w-0">
        <Link to={backPath} className="btn-ghost btn-sm shrink-0">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        {/* data-guide：操作指引「插件主页」那一步指的这里 */}
        <div className="min-w-0 flex-1" data-guide="pv-title">
          <h1 className="text-lg lg:text-xl font-bold text-gray-900 dark:text-white">
            <MarqueeText text={displayName} />
          </h1>
          <p className="text-[10px] lg:text-xs text-gray-500 truncate">{detail.plugin_id} · v{detail.version}</p>
        </div>
      </div>
      <Link to={backPath} className="shrink-0">
        <Button variant="ghost" size="sm" icon={<ExternalLink />}>返回账户</Button>
      </Link>
    </div>
  );

  // 演示态：页头是真的，正文换成说明。真实主页的界面与数据都来自插件自己
  // （`_ui_schema.json` + 插件自己的接口），演示插件两样都没有 —— 硬渲染只会
  // 得到一片报错，不如把「这里原本是什么」讲清楚
  if (demo) {
    return (
      <div className="animate-fade-in max-w-5xl">
        {header}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 lg:p-6">
          <div className="text-center py-12">
            <p className="text-sm text-gray-500 dark:text-gray-400">演示期间不加载真实插件界面</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
              真实使用中，这里会是「{displayName}」自己的界面 —— 由插件自己声明，不是面板写死的
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!detail.ui_schema) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-500">此插件没有 Web 前端页面</p>
        <Link to={backPath} className="text-primary-500 text-sm mt-2 inline-block">返回账户</Link>
      </div>
    );
  }

  return (
    <div className="animate-fade-in max-w-5xl">
      {header}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 lg:p-6">
        <PluginUI
          schema={detail.ui_schema as any}
          pluginName={detail.name}
          apiBase={`/api/accounts/${accountId}/plugin/${detail.name}/ui`}
        />
      </div>
    </div>
  );
}
