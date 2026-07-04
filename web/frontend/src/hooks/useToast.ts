import { useState, useCallback, useRef, useEffect } from 'react';

export interface Toast {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  exiting?: boolean;
}

let _nextId = 0;

const _globalListeners: Set<(toast: Toast) => void> = new Set();

export function showToast(
  type: Toast['type'],
  title: string,
  message?: string,
) {
  const toast: Toast = { id: ++_nextId, type, title, message };
  _globalListeners.forEach((fn) => fn(toast));
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const addToast = useCallback((toast: Toast) => {
    setToasts((prev) => [...prev.slice(-4), toast]);
    const timer = setTimeout(() => {
      setToasts((prev) => prev.map((t) => (t.id === toast.id ? { ...t, exiting: true } : t)));
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, 200);
    }, 4000);
    timers.current.set(toast.id, timer);
  }, []);

  // Subscribe to global toast events
  useEffect(() => {
    _globalListeners.add(addToast);
    return () => {
      _globalListeners.delete(addToast);
      timers.current.forEach((t) => clearTimeout(t));
    };
  }, [addToast]);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 200);
  }, []);

  const toast = useCallback(
    (type: Toast['type'], title: string, message?: string) => {
      showToast(type, title, message);
    },
    [],
  );

  return { toasts, removeToast, toast };
}
