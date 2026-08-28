/** 主机名工具 —— 账户入口识别。 */

/**
 * 当前是否通过账户入口子域名访问(固定的 ``user.`` 前缀,如 user.localhost)。
 *
 * - ``localhost`` / IP 地址 / 非 ``user`` 前缀 → 面板入口,返回 false
 * - ``user.localhost``、``user.mismiss.example.com`` → 账户入口,返回 true
 *
 * 身份不绑定子域名:登录时输入的用户名/密码决定属于哪个账户。
 */
export function isAccountPortalHost(): boolean {
  const host = window.location.hostname.toLowerCase();
  if (
    host === 'localhost' ||
    host === '127.0.0.1' ||
    /^\d+\.\d+\.\d+\.\d+$/.test(host)
  ) {
    return false;
  }
  return host.split('.')[0] === 'user';
}
