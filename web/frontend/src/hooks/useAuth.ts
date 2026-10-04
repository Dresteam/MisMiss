import { useState, useEffect, createContext, useContext } from 'react';

/** 待确认的更新日志(仅账户角色,同一版本只下发一次) */
export interface PendingChangelog {
  version: string;
  title: string;
  body: string;
}

interface AuthState {
  token: string | null;
  username: string | null;
  firstLogin: boolean;
  /** 角色:admin(面板管理员) | account(账户持有者) */
  role: 'admin' | 'account';
  accountId: number | null;
  /** 账户仍用着新建时预填的默认密码 —— 必须先改密才能用面板 */
  mustChangePassword: boolean;
  /** 服务器更新后首次登录时非空,关闭弹窗并 ack 后清空 */
  pendingChangelog: PendingChangelog | null;
  /** 账户角色还没看过「操作指引」—— 登录后自动跳过去，看过一次就不再跳 */
  showGuide: boolean;
}

const EMPTY_STATE = {
  token: null, username: null, firstLogin: false,
  role: 'admin' as const, accountId: null, mustChangePassword: false,
  pendingChangelog: null, showGuide: false,
};

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  changePassword: (current: string, newPwd: string) => Promise<void>;
  /** 看过指引后清掉标记，避免再点「/」时被重复跳转 */
  clearShowGuide: () => void;
  loading: boolean;
}

export const AuthContext = createContext<AuthContextType>(null!);
export const useAuth = () => useContext(AuthContext);

export function useAuthState(): AuthContextType {
  const [state, setState] = useState<AuthState>(() => ({
    ...EMPTY_STATE,
    token: localStorage.getItem('auth_token'),
  }));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (state.token) {
      fetch('/api/auth/check', { headers: { Authorization: `Bearer ${state.token}` } })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d && d.valid !== false) {
            setState(s => ({
              ...s,
              username: d.username,
              firstLogin: d.first_login,
              role: d.role === 'account' ? 'account' : 'admin',
              accountId: d.account_id ?? null,
              mustChangePassword: !!d.must_change_password,
              pendingChangelog: d.pending_changelog ?? null,
              showGuide: !!d.show_guide,
            }));
          } else {
            localStorage.removeItem('auth_token');
            setState(EMPTY_STATE);
          }
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (username: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
    const data = await res.json();
    localStorage.setItem('auth_token', data.token);
    setState({
      token: data.token,
      username: data.username,
      firstLogin: data.first_login,
      role: data.role === 'account' ? 'account' : 'admin',
      accountId: data.account_id ?? null,
      mustChangePassword: !!data.must_change_password,
      pendingChangelog: data.pending_changelog ?? null,
      showGuide: !!data.show_guide,
    });
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setState(EMPTY_STATE);
  };

  const changePassword = async (current: string, newPwd: string) => {
    if (!state.token) throw new Error('未登录');
    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: state.token, current_password: current, new_password: newPwd }),
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
    setState(s => ({ ...s, firstLogin: false }));
  };

  const clearShowGuide = () => setState((s) => ({ ...s, showGuide: false }));

  return { ...state, login, logout, changePassword, clearShowGuide, loading };
}
