/** 直播间 ID 与网页地址的相互转换。
 *
 * 与后端 ``core.network.urls`` 保持同一套规则：既接受裸数字，也接受直播间链接
 * （带协议头、www、结尾斜杠、查询串、锚点都可以）。前端这一份用于即时校验与
 * 预填，后端那份是最终裁决 —— 两边都做，是因为前端要能立刻提示格式错误，
 * 而不能只靠一次往返才发现。
 */

/** 直播间网页地址 */
export function livePageUrl(liveId: number): string {
  return `https://fm.missevan.com/live/${liveId}`;
}

/**
 * 把用户输入解析成直播间 id；解析不出来返回 ``null``。
 *
 * @param raw 用户输入（裸数字或直播间链接）
 */
export function parseLiveId(raw: string | number | null | undefined): number | null {
  if (typeof raw === 'number') {
    return Number.isInteger(raw) && raw > 0 ? raw : null;
  }
  const text = (raw ?? '').trim();
  if (!text) return null;
  if (/^\d+$/.test(text)) {
    const n = Number(text);
    return n > 0 ? n : null;
  }
  const m = text.match(/(?:^|\/live\/)(\d+)(?:\D|$)/);
  if (!m) return null;
  const n = Number(m[1]);
  return n > 0 ? n : null;
}
