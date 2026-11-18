import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

/** 面板筛选条件的本地持久化前缀 —— 与业务数据无关，只存 UI 偏好。 */
const PREFIX = 'mismiss.filters.';

function _localStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function _sessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * 与 ``useState`` 用法一致的持久化状态。
 *
 * 默认写 **localStorage**：同一浏览器的新标签页、关闭面板后重新打开、甚至
 * 重启浏览器都能恢复筛选条件。这与「进详情再返回」的 sessionStorage 方案
 * 不同——后者换一个标签页就丢，用户会以为功能没生效。
 *
 * 兼容旧版本：若 localStorage 里还没有值、而 sessionStorage 有同 key 的旧值，
 * 自动迁移过来；localStorage 不可用时回退 sessionStorage，再不行退化为普通 state。
 * 值必须能 JSON 序列化（字符串/数组/对象/布尔/数字）。
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
): [T, Dispatch<SetStateAction<T>>] {
  const storageKey = PREFIX + key;
  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initial;
    const local = _localStorage();
    const session = _sessionStorage();
    try {
      const raw = local?.getItem(storageKey);
      if (raw !== null && raw !== undefined) {
        return JSON.parse(raw) as T;
      }
      // 旧版本写在 sessionStorage：迁移到 localStorage，避免升级后首次打开丢失
      const legacy = session?.getItem(storageKey);
      if (legacy !== null && legacy !== undefined) {
        try {
          local?.setItem(storageKey, legacy);
        } catch {
          /* localStorage 写入失败时仍使用读到的旧值 */
        }
        return JSON.parse(legacy) as T;
      }
      return initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    const serialized = JSON.stringify(value);
    try {
      const local = _localStorage();
      if (local) {
        local.setItem(storageKey, serialized);
        return;
      }
    } catch {
      /* 隐私模式或配额满，回退 sessionStorage */
    }
    try {
      _sessionStorage()?.setItem(storageKey, serialized);
    } catch {
      /* 存储完全不可用：保持内存态 */
    }
  }, [storageKey, value]);

  return [value, setValue];
}
