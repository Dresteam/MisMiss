/**
 * 自助获取猫耳 Cookie。
 *
 * 嵌在 Bot 页的「自定义 Cookie」区块里，两个书签小工具：
 *
 * - **一键回传**：用户在猫耳页面点一下书签，把 `document.cookie` 推回面板。
 * - **显示 Cookie**：书签只把 Cookie 弹出来，由用户自己复制粘贴。
 *
 * 为什么非得用书签，而不是面板代登录
 * ----------------------------------
 * 猫耳的登录接口有三道服务端伪造不了的门槛（2026-09-29 逐项核对抓包）：
 * ① `Content-Type: application/x-www-form-urlencoded`（body 却是 JSON 文本）；
 * ② 每个请求带 `X-M-DeviceSign` —— 指纹库算出 visitorId 再对 URL 签名；
 * ③ 一整套登录页访客会话 Cookie（`FM_SESS` / `FM_SESS.sig` / `MSESSID` …），
 *    `FM_SESS.sig` 还是签过名的，验证码多半就绑在它上面。
 * 后端代发实测一律回 `100010007 滑动验证失败`。书签之所以可行，是因为它**运行在
 * 用户自己的浏览器、猫耳自己的页面上**，用的是这个人真实的指纹与会话，没有冒充谁。
 *
 * 按钮必须**拖到书签栏**（手机端只能在浏览器里手动新建书签）—— 在面板页面上直接点
 * 是无效的，那既读不到猫耳的 Cookie，也没有猫耳的同源上下文。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bookmark, RefreshCw, AlertTriangle, CircleCheck, Loader2, Copy } from 'lucide-react';
import { issueHelperToken, fetchHelperStatus } from '../api/client';
import { Button } from './Button';
import { showToast } from '../hooks/useToast';

// ------------------------------------------------------------------ //
// 书签小工具
// ------------------------------------------------------------------ //

/**
 * 书签里用的轻提示：往页面注入一个浮层，几秒后自己消失。
 *
 * 刻意不用 `alert()` —— 书签第一次点击多半发生在**面板页**上（见下方守卫），
 * 在那里弹一个阻塞对话框既突兀又要手动关。注入失败（比如页面还没有 body）
 * 才退回 alert 兜底。
 */
const NOTIFY_FN = 'const notify=m=>{try{'
  + 'const d=document.createElement("div");d.textContent=m;'
  + 'd.style.cssText="position:fixed;z-index:2147483647;left:50%;top:24px;'
  + 'transform:translateX(-50%);max-width:80vw;padding:10px 16px;border-radius:10px;'
  + 'background:#18181b;color:#fff;font:14px/1.5 system-ui,sans-serif;'
  + 'box-shadow:0 8px 30px rgba(0,0,0,.3);text-align:center";'
  + 'document.body.appendChild(d);setTimeout(()=>d.remove(),6000);'
  + '}catch(e){alert(m);}};';

/**
 * 两个书签共用的前置判断：当前不在猫耳页面上就先把用户送过去。
 *
 * 用户十有八九是在**面板页**上点的书签 —— 在那里读 `document.cookie` 只会拿到
 * 面板自己的 Cookie，传上去也没有意义。所以先看 hostname，不是猫耳就开一个
 * 猫耳标签页并让用户在那上面再点一次。
 *
 * 用 `window.open` 而不是直接 `location.href` 跳转：面板页要留在原地继续轮询
 * `/helper/status`，跳走了就再也看不到「已写入」的回执。
 */
const MISSEVAN_GUARD = 'if(!/(^|\\.)missevan\\.com$/i.test(location.hostname)){'
  + 'const w=window.open("https://fm.missevan.com/","_blank");'
  + 'notify(w?"已在新标签页打开猫耳FM，请在那个页面再点一次这个书签。"'
  + ':"没能打开新标签页，请手动访问 www.missevan.com 登录后再点这个书签。");'
  + 'return;}';

/** 「一键回传」：读取猫耳页面的 document.cookie 回传面板。 */
function buildSendBookmarklet(origin: string, token: string): string {
  return 'javascript:(()=>{'
    + NOTIFY_FN
    + MISSEVAN_GUARD
    + 'const c=document.cookie;'
    + 'if(!c){notify("读取不到 Cookie，请确认已登录猫耳FM。");return;}'
    + `fetch('${origin}/api/helper/cookie',{method:'POST',mode:'no-cors',`
    + "headers:{'Content-Type':'text/plain'},"
    + `body:JSON.stringify({token:'${token}',cookie:c})});`
    + 'notify("已发送到 MisMiss，请回到面板页面查看结果。");'
    + '})()';
}

/**
 * 「显示 Cookie」：只把 Cookie 弹出来，不发送。
 *
 * 用于面板没有 HTTPS（HTTPS 的猫耳页面无法向 http 地址发请求），
 * 或用户不愿意让浏览器自动回传的场景。用 prompt 而非 alert ——
 * alert 里的文字无法复制。
 */
function buildShowBookmarklet(): string {
  return 'javascript:(()=>{'
    + NOTIFY_FN
    + MISSEVAN_GUARD
    + 'const c=document.cookie;'
    + 'if(!c){notify("读取不到 Cookie，请确认已登录猫耳FM。");return;}'
    + 'prompt("复制下面的 Cookie，回到 MisMiss 面板粘贴：",c);'
    + '})()';
}

// ------------------------------------------------------------------ //
// 平台识别与文案
// ------------------------------------------------------------------ //

type Platform = 'desktop' | 'ios' | 'android' | 'other';

function detectPlatform(): Platform {
  if (typeof navigator === 'undefined') return 'desktop';
  const ua = navigator.userAgent;
  // iPadOS 13+ 的 UA 伪装成 Mac，靠触点数区分
  const iOS = /iPad|iPhone|iPod/.test(ua)
    || (/Macintosh/.test(ua) && typeof navigator.maxTouchPoints === 'number'
        && navigator.maxTouchPoints > 1);
  if (iOS) return 'ios';
  if (/Android/.test(ua)) {
    // Chrome / Edge / 三星浏览器的书签菜单是同一套，按它们写步骤；
    // 其余国产浏览器入口各不相同，交给「其他」那套通用说法
    const other = /UCBrowser|Quark|MQQBrowser|HuaweiBrowser|HeyTapBrowser|MiuiBrowser|VivoBrowser|Firefox|OPR\//i;
    return other.test(ua) ? 'other' : 'android';
  }
  // 其它能在手机上跑的浏览器（鸿蒙、Windows Phone …）
  if (/Mobile|HarmonyOS|Windows Phone/i.test(ua)) return 'other';
  return 'desktop';
}

/**
 * 是否在**内置浏览器**里（微信 / QQ / 微博 / 支付宝 / 钉钉 的 WebView）。
 *
 * 这些 WebView 没有书签管理器，书签根本装不上 —— 不是步骤写得不对，是
 * 这条路在它们里面不存在。所以要把用户先请到系统浏览器里去。
 */
function isInAppBrowser(): boolean {
  if (typeof navigator === 'undefined') return false;
  // 注意 QQBrowser（带 MQQBrowser 的独立浏览器）**有**书签管理器，不在其列；
  // QQ 内置浏览器才有 `QQ/8.x` 这一段
  return /MicroMessenger|QQ\/\d|Weibo|AlipayClient|DingTalk/i.test(navigator.userAgent);
}

const PLATFORM_LABEL: Record<Platform, string> = {
  desktop: '电脑',
  ios: 'iPhone / iPad',
  android: 'Android',
  other: '其他手机浏览器',
};

/** 让用户把书签地址复制走去手动建书签（手机上没有拖拽）。 */
function CopyBookmarklet({ href }: { href: string }) {
  const [fallback, setFallback] = useState(false);
  const box = useRef<HTMLTextAreaElement | null>(null);

  const copy = async () => {
    try {
      // clipboard API 只在 HTTPS / localhost 可用；面板线上是 HTTPS
      await navigator.clipboard.writeText(href);
      showToast('success', '书签地址已复制', '按下方步骤粘贴到书签里');
    } catch {
      setFallback(true);   // 降级：摊开原文让用户手动选中复制
      showToast('info', '请手动复制', '在下面的文本框里全选复制');
    }
  };

  return (
    <div className="space-y-2">
      <Button variant="secondary" size="sm" icon={<Copy className="w-4 h-4" />} onClick={copy}>
        复制书签地址
      </Button>
      {fallback && (
        <textarea
          ref={box}
          readOnly
          value={href}
          rows={3}
          onFocus={() => box.current?.select()}
          className="input w-full font-mono text-[10px] break-all"
        />
      )}
    </div>
  );
}

/** 拖拽用；在面板页面上直接点会被拦下 —— 见 onWrongClick。 */
function BookmarkChip({ href, label, onWrongClick }: {
  href: string; label: string; onWrongClick: () => void;
}) {
  return (
    <a
      href={href}
      draggable
      onClick={(e) => { e.preventDefault(); onWrongClick(); }}
      className="inline-flex items-center gap-2 px-3 h-9 rounded-lg border border-dashed
                 border-primary-400 dark:border-primary-600 bg-primary-50 dark:bg-primary-900/30
                 text-primary-700 dark:text-primary-300 text-sm font-medium cursor-grab
                 active:cursor-grabbing select-none"
    >
      <Bookmark className="w-4 h-4" />
      {label}
    </a>
  );
}

function Steps({ children }: { children: React.ReactNode }) {
  return (
    <ol className="text-sm text-gray-600 dark:text-gray-300 space-y-1.5 list-decimal list-inside">
      {children}
    </ol>
  );
}

/**
 * 分平台的「怎么把书签装上 + 怎么用」——电脑是拖拽，手机只能手动新建。
 *
 * 最后一步三个平台一致：点它即可。不需要预先在猫耳页面 —— 书签自己会判断
 * 当前是不是猫耳，不是就帮你开一个（见 MISSEVAN_GUARD）。
 */
function InstallSteps({ platform, children }: {
  platform: Platform; children?: React.ReactNode;
}) {
  const last = (
    <li>
      点它即可。当前不在猫耳页面也没关系 —— 它会帮你打开猫耳，
      <b>在猫耳页面上再点一次</b>就行
    </li>
  );
  if (platform === 'desktop') {
    return (
      <>
        <Steps>
          <li>把上面的按钮<b>拖到浏览器的书签栏</b>（拖不动就右键复制链接，手动新建书签）</li>
          {last}
        </Steps>
        {children}
      </>
    );
  }
  if (platform === 'ios') {
    return (
      <>
        <Steps>
          <li>先点「复制书签地址」把地址存进剪贴板</li>
          <li>在任意页面点底部的<b>分享</b>图标 → 「<b>添加书签</b>」，名字随便起（如 MisMiss），保存</li>
          <li>点底部的<b>书签</b>图标 → 找到刚加的那条 → 点右下角「<b>编辑</b>」</li>
          <li>点地址那一行，全选删掉，<b>粘贴</b>刚复制的地址 → 点空白处保存</li>
          {last}
        </Steps>
        {children}
      </>
    );
  }
  if (platform === 'android') {
    return (
      <>
        <Steps>
          <li>先点「复制书签地址」把地址存进剪贴板</li>
          <li>在任意页面点右上角 <b>⋮</b> → <b>星标</b>图标，添加书签（名字随便起）</li>
          <li>再点 <b>⋮</b> → 「<b>书签</b>」→ 长按刚加的那条 → 「<b>修改</b>」</li>
          <li>把网址整段删掉，<b>粘贴</b>刚复制的地址 → 保存</li>
          {last}
        </Steps>
        {children}
      </>
    );
  }
  // 其他手机浏览器（UC / 夸克 / 三星 / QQ浏览器 / Firefox …）：
  // 菜单位置各家不同，但要做的事是同一件 —— 添加书签、编辑、把地址换成这一串
  return (
    <>
      <Steps>
        <li>先点「复制书签地址」把地址存进剪贴板</li>
        <li>在任意页面找到浏览器的<b>书签 / 收藏</b>菜单（通常在底部工具栏或右上角菜单里），
          把当前页面添加为书签（名字随便起）</li>
        <li>进入书签列表，长按或点「编辑」那条书签</li>
        <li>把网址整段删掉，<b>粘贴</b>刚复制的地址 → 保存</li>
        {last}
      </Steps>
      {children}
    </>
  );
}

/**
 * 手机端装不上书签时的退路。
 *
 * 没有书签就**真的没有别的办法** —— Cookie 只有站在猫耳自己的页面上才读得到，
 * 而要在别人的页面里执行代码，手机浏览器上只有书签这一条路（扩展在移动端基本
 * 不可用）。所以这里的退路都是「绕开手机」，而不是「换个姿势注入」。
 */
function NoBookmarkFallback() {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 space-y-1">
      <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
        装不上书签 / 书签点了没反应？
      </p>
      <ul className="text-xs text-gray-500 dark:text-gray-400 space-y-1 list-disc list-inside">
        <li>先确认不在微信、QQ 这类内置浏览器里（见上方提示）</li>
        <li>换个系统浏览器再试一次 —— Safari、Chrome、手机自带浏览器都可以</li>
        <li>
          还是不行就<b>别在手机上折腾了</b>：让别人在电脑上打开面板，
          用同一个「一键回传」书签帮你取一次。Cookie 通常能维持很久，不用反复弄。
        </li>
      </ul>
    </div>
  );
}

/** 内置浏览器装不了书签，得先把用户请到系统浏览器里。 */
function InAppWarning() {
  return (
    <div className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-400
                    bg-amber-50 dark:bg-amber-900/20 border border-amber-200
                    dark:border-amber-800 rounded-lg px-3 py-2">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <span>
        你正在<b>微信 / QQ 等内置浏览器</b>里，这些浏览器没有书签管理器，书签装不上。
        请点右上角「<b>⋯</b>」→「<b>在浏览器打开</b>」，换到系统浏览器再按下面的步骤操作。
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ //

type HelperTab = 'send' | 'show';

export function CookieHelper({ accountId, onDone }: {
  accountId: number;
  /** 成功写入 Cookie 后回调（父级刷新账户摘要，模式会变成私有） */
  onDone?: () => void;
}) {
  const [tab, setTab] = useState<HelperTab>('send');
  const [platform, setPlatform] = useState<Platform>(detectPlatform);
  const [inApp] = useState<boolean>(isInAppBrowser);
  const [token, setToken] = useState('');
  const [expiresAt, setExpiresAt] = useState(0);
  const [status, setStatus] = useState<{ state: string; message: string } | null>(null);
  const [minting, setMinting] = useState(false);

  // 自动签发只做一次。用「已触发过」的闩而不是「正在飞」的闸：StrictMode 会
  // 把 effect 跑两遍甚至重挂组件，只看在飞状态拦不住，会白多出几个待过期的
  // token 文件。「重新生成」走的是直接调用 mint()，不经过这个 effect。
  const autoMinted = useRef(false);

  const origin = typeof window === 'undefined' ? '' : window.location.origin;

  const mint = useCallback(async () => {
    if (!accountId) return;
    setMinting(true);
    try {
      const r = await issueHelperToken(accountId);
      setToken(r.token);
      setExpiresAt(r.expires_at);
      setStatus({ state: 'waiting', message: '' });
    } catch (e: any) {
      showToast('error', '生成失败', e.message);
    } finally {
      setMinting(false);
    }
  }, [accountId]);

  useEffect(() => {
    if (token || autoMinted.current) return;
    autoMinted.current = true;
    void mint();
  }, [token, mint]);

  // 轮询消费状态 —— 书签端是 no-cors，拿不到响应，成败只能靠这里得知
  const waiting = status?.state === 'waiting';
  useEffect(() => {
    if (!token || !waiting) return;
    const t = setInterval(async () => {
      try {
        const s = await fetchHelperStatus(accountId, token);
        setStatus(s);
        if (s.state === 'done') {
          showToast('success', s.message || 'Cookie 已更新', '');
          onDone?.();
        } else if (s.state === 'failed') {
          showToast('error', 'Cookie 未能写入', s.message);
        }
      } catch { /* 下一轮再试 */ }
    }, 2500);
    return () => clearInterval(t);
  }, [token, waiting, accountId, onDone]);

  if (!accountId) {
    return <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-primary-500" /></div>;
  }

  const expired = expiresAt > 0 && Date.now() / 1000 > expiresAt;
  const ready = !!token && !expired;
  const sendHref = ready ? buildSendBookmarklet(origin, token) : '';
  const showHref = buildShowBookmarklet();

  const regen = (
    <Button variant="ghost" size="sm" icon={<RefreshCw className="w-4 h-4" />}
      loading={minting} onClick={() => { setToken(''); setStatus(null); mint(); }}>
      重新生成
    </Button>
  );

  return (
    <div className="space-y-3">
      {/* 内置浏览器装不了书签，先请用户换到系统浏览器 */}
      {inApp && <InAppWarning />}

      {/* 平台切换 —— 默认按当前 UA 选，但允许手动切（可能在电脑上替手机设置） */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-400">装书签的方式：</span>
        {(['desktop', 'ios', 'android', 'other'] as const).map((p) => (
          <button key={p} type="button" onClick={() => setPlatform(p)}
            className={`inline-flex items-center min-h-8 px-2.5 py-1 text-xs rounded-lg border transition-colors
              ${platform === p
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
            {PLATFORM_LABEL[p]}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-1">
        {([['send', '一键回传'], ['show', '显示 Cookie']] as const).map(([k, label]) => (
          <button key={k} type="button" onClick={() => setTab(k)}
            className={`inline-flex items-center min-h-8 px-2.5 py-1 text-xs rounded-lg border transition-colors
              ${tab === k
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                : 'border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'send' ? (
        <div className="space-y-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            用你平时的方式登录猫耳（密码、短信验证码、第三方账号都行），再用下面的书签把
            Cookie 传回来。取到后会直接替换当前 Bot 的 Cookie，账户也会切换为「自定义 Cookie」。
          </p>
          {minting && <span className="text-sm text-gray-400">正在生成书签…</span>}
          {!minting && expired && (
            <p className="text-sm text-amber-600 dark:text-amber-400">书签已过期，请点「重新生成」</p>
          )}
          {ready && (
            <div className="flex flex-wrap items-center gap-2">
              {platform === 'desktop'
                ? (
                  <BookmarkChip
                    href={sendHref}
                    label="一键回传 Cookie"
                    onWrongClick={() => showToast('info', '请拖到书签栏',
                      '这个书签要在猫耳页面上点击才有效,在面板里点只会读到面板自己的 Cookie')}
                  />
                )
                : <CopyBookmarklet href={sendHref} />}
              {regen}
            </div>
          )}
          {!ready && !minting && regen}

          <InstallSteps platform={platform} />
          {platform !== 'desktop' && <NoBookmarkFallback />}

          {status?.state === 'done' && (
            <p className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
              <CircleCheck className="w-4 h-4" />{status.message}
            </p>
          )}
          {status?.state === 'failed' && (
            <p className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertTriangle className="w-4 h-4" />{status.message}
            </p>
          )}
          {waiting && !expired && (
            <p className="text-xs text-gray-400">
              等待书签回传…（书签 5 分钟内有效，过期请点「重新生成」）
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            用你平时的方式登录猫耳，再用下面的书签把 Cookie 显示出来 —— 它只弹给你看，
            不会向面板发任何请求。适合面板没有 HTTPS、或你不想让浏览器自动回传的情况。
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {platform === 'desktop'
              ? (
                <BookmarkChip
                  href={showHref}
                  label="显示 Cookie"
                  onWrongClick={() => showToast('info', '请拖到书签栏',
                    '这个书签要在猫耳页面上点击才有效')}
                />
              )
              : <CopyBookmarklet href={showHref} />}
          </div>
          <InstallSteps platform={platform} />
          {platform !== 'desktop' && <NoBookmarkFallback />}
          <p className="text-xs text-gray-400">
            点它之后会弹出 Cookie，把它整段粘贴到下方「更换 Cookie」的输入框，再点保存。
          </p>
        </div>
      )}
    </div>
  );
}
