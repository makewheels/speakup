import { useCallback, useRef } from "react";

/**
 * 录音按钮「长按 vs 单击」去重：按住 320ms 才触发 action（长按路径），
 * 松手后的 onClick 若长按已触发则跳过，避免一次按住触发两下。
 */
export default function usePressGuard() {
  const timerRef = useRef(null);
  const handledRef = useRef(false);

  const pressStart = useCallback((action) => {
    handledRef.current = false;
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      handledRef.current = true;
      action();
    }, 320);
  }, []);

  const pressEnd = useCallback(() => clearTimeout(timerRef.current), []);

  const pressClick = useCallback((action) => {
    if (handledRef.current) {
      handledRef.current = false;
      return;
    }
    action();
  }, []);

  const pressCancel = useCallback(() => clearTimeout(timerRef.current), []);

  return { pressStart, pressEnd, pressClick, pressCancel };
}
