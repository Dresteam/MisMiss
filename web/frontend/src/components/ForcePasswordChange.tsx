import { ShieldAlert } from 'lucide-react';
import { AccountPasswordForm } from './AccountPasswordForm';

interface Props {
  accountId: number;
  /** 改密成功后的收尾：清 token 并要求重新登录 */
  onDone: () => void;
}

/**
 * 「必须修改默认密码」的强制界面。
 *
 * 新建账户的密码是预填的默认值，人人都知道，留着等于没设防 —— 这类账户登录后
 * 不给跳过，改完为止。**没有关闭按钮、点遮罩也不关**，否则等于没要求。
 * （用户仍可直接关掉页面或退出登录，登录凭据并没有被锁死。）
 */
export function ForcePasswordChange({ accountId, onDone }: Props) {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl
                      p-6 max-w-sm w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/40
                          flex items-center justify-center shrink-0">
            <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">请先修改密码</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">这一步不能跳过</p>
          </div>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          当前账户仍在使用创建时预填的默认密码，任何人试一次就能登进来。
          修改后才能继续使用面板。
        </p>
        <AccountPasswordForm accountId={accountId} onDone={onDone} submitLabel="修改并重新登录" />
      </div>
    </div>
  );
}
