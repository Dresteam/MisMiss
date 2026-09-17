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
  /** 服务器更新后首次登录时非空,关闭弹窗并 ack 后清空 */
  pendingChangelog: PendingChangelog | null;
}

const EMPTY_STATE = {
  token: null, username: null, firstLogin: false,
  role: 'admin' as const, accountId: null, pendingChangelog: null,
};

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  changePassword: (current: string, newPwd: string) => Promise<void>;
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
              pendingChangelog: d.pending_changelog ?? null,
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
      pendingChangelog: data.pending_changelog ?? null,
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

  return { ...state, login, logout, changePassword, loading };
}
