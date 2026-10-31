import { useEffect, useRef, useState } from "react";

export interface RouteInfo {
  path: string;
  params: URLSearchParams;
}

function parseHash(): RouteInfo {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const questionMark = raw.indexOf("?");
  const path = questionMark >= 0 ? raw.slice(0, questionMark) : raw;
  const search = questionMark >= 0 ? raw.slice(questionMark + 1) : "";
  return { path: path || "/", params: new URLSearchParams(search) };
}

export function useRoute(): RouteInfo {
  const [route, setRoute] = useState<RouteInfo>(() => parseHash());
  useEffect(() => {
    const listener = () => {
      setRoute(parseHash());
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    };
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  return route;
}

export function navigate(to: string): void {
  const target = to.startsWith("#") ? to : `#${to}`;
  if (window.location.hash === target) {
    return;
  }
  window.location.hash = target;
}

export function navigateWithParams(path: string, params: Record<string, string | undefined>): void {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      search.set(key, value);
    }
  }
  const suffix = search.toString();
  navigate(`${path}${suffix ? `?${suffix}` : ""}`);
}

export function useDebouncedValue<T>(value: T, delayMilliseconds = 250): T {
  const [debounced, setDebounced] = useState(value);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setDebounced(value), delayMilliseconds);
    return () => window.clearTimeout(timer.current);
  }, [value, delayMilliseconds]);
  return debounced;
}
