import { createContext, useContext, useEffect, useRef, useState } from "react";

export const LiveVersionContext = createContext(0);

export function useLiveVersion(): number {
  return useContext(LiveVersionContext);
}

/**
 * 订阅后端 SSE 更新通知。事件只携带版本号与变更的运行列表；
 * 这里合并 600ms 内的多条通知，避免训练高频写日志时反复重绘。
 */
export function useServerEvents(): { connected: boolean; version: number } {
  const [version, setVersion] = useState(0);
  const [connected, setConnected] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const source = new EventSource("/api/v1/stream");
    const scheduleUpdate = () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => {
        setVersion((value) => value + 1);
      }, 600);
    };
    source.addEventListener("ready", () => {
      setConnected(true);
    });
    source.addEventListener("update", scheduleUpdate);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    return () => {
      window.clearTimeout(timer.current);
      source.close();
    };
  }, []);

  return { connected, version };
}
