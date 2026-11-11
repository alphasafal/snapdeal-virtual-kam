// The web app's connection to Postgres.
// The voice agent (Python) writes calls, transcripts and actions to this same database;
// the pages here read them. That shared database is the only link between the two.
import { Pool } from "pg";

// One pool per server instance. Reads the same Postgres the voice agent writes to.
const globalForPg = globalThis as unknown as { kamPool?: Pool };

export function pool(): Pool {
  if (!globalForPg.kamPool) {
    const url = process.env.DATABASE_URL;
    if (!url) throw new Error("DATABASE_URL is not set");
    const local = /localhost|127\.0\.0\.1/.test(url);
    globalForPg.kamPool = new Pool({
      connectionString: url,
      ssl: local ? undefined : { rejectUnauthorized: false },
      max: 5,
    });
  }
  return globalForPg.kamPool;
}

// Run one SQL query and return its rows. Values always go in `params` ($1, $2, ...),
// never into the SQL text, so user input cannot change the query.
export async function q<T = Record<string, any>>(text: string, params: unknown[] = []): Promise<T[]> {
  const res = await pool().query(text, params as any[]);
  return res.rows as T[];
}

// A short unique id such as "call_3f9a1c22b7". Same format the Python side uses.
export function newId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, "").slice(0, 10)}`;
}

// The review table is small and owned by the web app, so make sure it exists before using it.
let reviewsReady: Promise<unknown> | null = null;
export function ensureReviews(): Promise<unknown> {
  reviewsReady ??= pool().query(`create table if not exists call_reviews (
    call_id varchar primary key, verdict varchar not null, reviewer varchar, note text,
    reviewed_at timestamptz)`);
  return reviewsReady;
}
