import { useEffect, useRef, useState } from 'react';

interface Props {
  text: string;
  className?: string;
}

const SCROLL_SPEED = 20; // px/s 恒定滚动速度
const PAUSE = 1;         // 左右两端各停留 1s（固定）

let _styleInjected = false;

/** 注入动态 keyframes —— 两端各停留 1s，百分比随文字长度变化。 */
function injectKeyframes(animationName: string, distance: number, total: number) {
  const scrollStart = (PAUSE / total) * 100;
  const scrollEnd = ((PAUSE + distance / SCROLL_SPEED) / total) * 100;

  let styleEl = document.getElementById('marquee-dynamic') as HTMLStyleElement | null;
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'marquee-dynamic';
    document.head.appendChild(styleEl);
  }

  styleEl.textContent = `
    @keyframes ${animationName} {
      0% { transform: translateX(0); }
      ${scrollStart}% { transform: translateX(0); }
      ${scrollEnd}% { transform: translateX(-${distance}px); }
      100% { transform: translateX(-${distance}px); }
    }
  `;
}

let _animId = 0;

/** 文字溢出时自动滚动：恒定速度 + 固定两端停留，无空白。 */
export function MarqueeText({ text, className = '' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const [distance, setDistance] = useState(0);
  const [animName, setAnimName] = useState('');

  useEffect(() => {
    const container = containerRef.current;
    const textEl = textRef.current;
    if (!container || !textEl) return;
    const overflow = textEl.getBoundingClientRect().width - container.getBoundingClientRect().width;
    setDistance(overflow > 1 ? overflow : 0);
  }, [text]);

  // 窗口尺寸变化时重新测量
  useEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      const textEl = textRef.current;
      if (!container || !textEl) return;
      const overflow = textEl.getBoundingClientRect().width - container.getBoundingClientRect().width;
      setDistance(overflow > 1 ? overflow : 0);
    };
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  // 根据距离生成动态动画
  useEffect(() => {
    if (distance <= 0) { setAnimName(''); return; }
    const total = PAUSE * 2 + distance / SCROLL_SPEED;
    const name = `marquee-${++_animId}`;
    injectKeyframes(name, distance, total);
    setAnimName(name);
  }, [distance]);

  return (
    <div ref={containerRef} className={`overflow-hidden ${className}`}>
      <span
        ref={textRef}
        className="inline-block whitespace-nowrap w-max"
        style={animName ? { animation: `${animName} ${PAUSE * 2 + distance / SCROLL_SPEED}s linear infinite` } : undefined}
      >
        {text}
      </span>
    </div>
  );
}
