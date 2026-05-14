import { useEffect, useState } from "react";

type Greeting = { id: number; message: string };
type Status =
  | { kind: "loading" }
  | { kind: "ok"; greeting: Greeting }
  | { kind: "error"; error: string };

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/greeting")
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return (await res.json()) as Greeting;
      })
      .then((greeting) => setStatus({ kind: "ok", greeting }))
      .catch((err: unknown) =>
        setStatus({
          kind: "error",
          error: err instanceof Error ? err.message : String(err),
        }),
      );
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Allocio</h1>
      {status.kind === "loading" && <p>Loading…</p>}
      {status.kind === "ok" && (
        <p>
          From the database: <strong>{status.greeting.message}</strong> (id{" "}
          {status.greeting.id})
        </p>
      )}
      {status.kind === "error" && (
        <p style={{ color: "crimson" }}>Error: {status.error}</p>
      )}
    </main>
  );
}
