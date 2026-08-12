import { useCallback, useEffect, useRef, useState } from "react";

const AUTO_DISMISS_MS = 3600;

// 上限到達時の案内(「有料プランでは無制限です」等)を表示するための
// 汎用トースト。複数の上限(お気に入り・比較)から共通で使う。
export function useToast() {
  const [message, setMessage] = useState(null);
  const timeoutRef = useRef(null);

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const showToast = useCallback((text) => {
    setMessage(text);
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setMessage(null), AUTO_DISMISS_MS);
  }, []);

  const dismissToast = useCallback(() => {
    clearTimeout(timeoutRef.current);
    setMessage(null);
  }, []);

  return { message, showToast, dismissToast };
}
