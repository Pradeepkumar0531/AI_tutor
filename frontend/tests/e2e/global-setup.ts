import { execFileSync, execSync, spawn } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";

export const E2E_DB = "/tmp/alc-e2e.db";
export const E2E_DATABASE_URL = `sqlite:///${E2E_DB}`;
export const E2E_STORAGE_DIR = "/tmp/alc-e2e-storage";
export const E2E_BROKER_ROOT = "/tmp/alc-e2e-broker";
export const E2E_RESULTS_DIR = "/tmp/alc-e2e-results";
export const E2E_FIXTURE_PDF = "/tmp/alc-e2e-fixture.pdf";
export const E2E_WORKER_PID = "/tmp/alc-e2e-worker.pid";
export const E2E_WORKER_LOG = "/tmp/alc-e2e-worker.log";

export const E2E_BACKEND_ENV: Record<string, string> = {
  DATABASE_URL: process.env.DATABASE_URL ?? E2E_DATABASE_URL,
  CELERY_BROKER_URL: "filesystem://",
  CELERY_FILESYSTEM_ROOT: E2E_BROKER_ROOT,
  CELERY_RESULT_BACKEND: `file://${E2E_RESULTS_DIR}`,
  STORAGE_BACKEND: "local",
  LOCAL_STORAGE_DIR: E2E_STORAGE_DIR,
  // Deterministic fake AI (content-derived embeddings + keyword concepts).
  // No credentials, no network — the only honest way to exercise the real
  // knowledge pipeline end to end here. Never set in production.
  TEST_FAKE_AI: "true",
  // Admin bootstrap for the admin journey spec: registering this email
  // promotes it to admin (the only privilege path; no public endpoint).
  ADMIN_EMAILS: "e2e-admin@example.com",
};

/** Fresh SQLite database with the full schema for the e2e backend. */
export default function globalSetup() {
  for (const f of [E2E_DB, E2E_WORKER_PID, E2E_WORKER_LOG]) {
    try {
      unlinkSync(f);
    } catch {
      // First run: nothing to delete.
    }
  }
  for (const dir of [E2E_STORAGE_DIR, E2E_BROKER_ROOT, E2E_RESULTS_DIR]) {
    rmSync(dir, { recursive: true, force: true });
    mkdirSync(dir, { recursive: true });
  }
  const createAll = [
    "from sqlalchemy import create_engine;",
    "import app.models;",
    "from app.db.base import Base;",
    `Base.metadata.create_all(create_engine(${JSON.stringify(E2E_DATABASE_URL)}))`,
  ].join(" ");
  execFileSync("../backend/.venv/bin/python", ["-c", createAll], { cwd: "../backend" });

  // Deterministic 2-page PDF fixture (generated, never committed): same text
  // as before plus one embedded 300x200 raster on page 1 (noisy pixels so it
  // passes the minimum-bytes filter; text, chunking, and concepts unchanged).
  const makePdf = [
    "import fitz, random;",
    "doc = fitz.open();",
    "p1 = doc.new_page();",
    'p1.insert_textbox(fitz.Rect(72, 72, 500, 700), "Photosynthesis converts sunlight into chemical energy. Page one.");',
    "rng = random.Random(7);",
    "pix = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 300, 200));",
    "[(pix.set_rect(fitz.Rect(x, y, x+4, y+4), (rng.randrange(256), rng.randrange(256), rng.randrange(256))), None) for y in range(0, 200, 4) for x in range(0, 300, 4)];",
    "p1.insert_image(fitz.Rect(72, 200, 372, 400), pixmap=pix);",
    "p2 = doc.new_page();",
    'p2.insert_textbox(fitz.Rect(72, 72, 500, 700), "Mitochondria release that energy as ATP. Page two.");',
    `doc.save(${JSON.stringify(E2E_FIXTURE_PDF)});`,
  ].join(" ");
  execFileSync("../backend/.venv/bin/python", ["-c", makePdf], { cwd: "../backend" });
  if (!existsSync(E2E_FIXTURE_PDF)) throw new Error("e2e fixture PDF missing");

  // Real Celery worker subprocess (solo pool): same task code as production,
  // filesystem broker as the Redis stand-in, shared SQLite + storage paths.
  const logFd = openSync(E2E_WORKER_LOG, "w");
  const child = spawn(
    "../backend/.venv/bin/celery",
    ["-A", "app.jobs.worker.celery", "worker", "--pool=solo", "--concurrency=1", "-l", "INFO"],
    {
      cwd: "../backend",
      env: { ...process.env, ...E2E_BACKEND_ENV },
      detached: true,
      stdio: ["ignore", logFd, logFd],
    },
  );
  child.unref();
  if (child.pid) writeFileSync(E2E_WORKER_PID, String(child.pid), "utf-8");

  // Readiness: the solo worker logs "ready." once it consumes.
  const deadline = Date.now() + 90_000;
  for (;;) {
    try {
      const log = readFileSync(E2E_WORKER_LOG, "utf-8");
      if (/ready\./.test(log)) break;
      if (/Traceback|CRITICAL|Error:/.test(log)) {
        throw new Error(`e2e worker failed to boot, see ${E2E_WORKER_LOG}`);
      }
    } catch (e) {
      if ((e as Error).message.startsWith("e2e worker failed")) throw e;
    }
    if (Date.now() > deadline) {
      throw new Error(`e2e celery worker did not start, see ${E2E_WORKER_LOG}`);
    }
    execSync("sleep 1");
  }
}

export function stopE2EWorker() {
  try {
    const pid = Number(readFileSync(E2E_WORKER_PID, "utf-8"));
    if (pid) process.kill(pid, "SIGTERM");
  } catch {
    // Already gone.
  }
}
