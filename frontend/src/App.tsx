import { AppShell } from "./components/AppShell";
import { LiveVersionContext, useServerEvents } from "./live/LiveUpdates";

export function App() {
  const { connected, version } = useServerEvents();
  return (
    <LiveVersionContext.Provider value={version}>
      <AppShell connected={connected} />
    </LiveVersionContext.Provider>
  );
}
