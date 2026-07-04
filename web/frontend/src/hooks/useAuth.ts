import { useState, useEffect, createContext, useContext } from 'react';

interface AuthState {
  token: string | null;
  username: string | null;
  firstLogin: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  changePassword: (current: string, newPwd: string) => Promise<void>;
  loading: boolean;
}

export const AuthContext = createContext<AuthContextType>(null!);
export const useAuth = () => useContext(AuthContext);

export function useAuthState(): AuthContextType {
  const [state, setState] = useState<AuthState>(() => {
    const token = localStorage.getItem('auth_token');
    return { token, username: null, firstLogin: false };
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (state.token) {
      fetch('/api/auth/check', { headers: { Authorization: `Bearer ${state.token}` } })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d) setState(s => ({ ...s, username: d.username, firstLogin: d.first_login }));
          else { localStorage.removeItem('auth_token'); setState({ token: null, username: null, firstLogin: false }); }
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
    setState({ token: data.token, username: data.username, firstLogin: data.first_login });
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setState({ token: null, username: null, firstLogin: false });
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
