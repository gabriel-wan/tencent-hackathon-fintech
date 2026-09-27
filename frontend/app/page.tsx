import { connection } from "next/server";

async function getHealth() {
  try {
    const res = await fetch(`${process.env.BACKEND_URL}/health`, { cache: "no-store" });
    return await res.json();
  } catch {
    return { backend: "unreachable" };
  }
}

export default async function Home() {
  await connection(); // render per request: backend is unreachable during `next build`
  const health = await getHealth();
  return (
    <main>
      <h1>Internal Brain</h1>
      <pre>{JSON.stringify(health, null, 2)}</pre>
    </main>
  );
}
