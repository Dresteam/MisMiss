import zhCN from './zh-CN';
import type { ZhCN } from './zh-CN';

type NestedKeyOf<T> = T extends string ? never : {
  [K in keyof T & string]: T[K] extends string
    ? K
    : T[K] extends Record<string, any>
      ? `${K}.${NestedKeyOf<T[K]>}`
      : never;
}[keyof T & string];

export type I18nKey = NestedKeyOf<ZhCN>;

/** 获取翻译文本，支持 {key} 变量替换 */
export function t(key: I18nKey, vars?: Record<string, string | number>): string {
  const keys = key.split('.');
  let val: any = zhCN;
  for (const k of keys) {
    if (val && typeof val === 'object' && k in val) {
      val = val[k];
    } else {
      return key; // fallback: 返回 key 本身
    }
  }
  if (typeof val !== 'string') return key;

  // 变量替换 {key}
  if (vars) {
    return val.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
  }
  return val;
}

/** React Hook 版本 */
export function useT() {
  return { t };
}

export { zhCN };
