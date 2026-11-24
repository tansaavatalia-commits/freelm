// Shapes returned by the local API (genesis/api/server.py).

export type TaskStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";
export const TASK_STATUSES: TaskStatus[] = ["pending", "running", "succeeded", "failed", "cancelled"];

export interface Gpu {
  name: string;
  vram_mb: number | null;
}

export interface Hardware {
  os_name: string;
  os_release: string;
  os_version: string;
  machine: string;
  python: string;
  cpu_model: string | null;
  cpu_logical: number | null;
  ram_total_mb: number | null;
  ram_available_mb: number | null;
  disk_path: string;
  disk_total_gb: number | null;
  disk_free_gb: number | null;
  gpus: Gpu[] | null;
  notes: string[];
}

export interface Status {
  version: string;
  home: string;
  database: string;
  schema_version: number;
  profile: string;
  profile_reason: string;
  projects: number;
  tasks: Record<TaskStatus, number>;
  pending_approvals: number;
  audit_entries: number;
  audit_chain_ok: boolean;
  audit_first_bad_seq: number | null;
  backups: number;
  engines: Engine[];
  profile_details: { max_workers: number; max_parallel_online: number; local_models: boolean; description: string };
  hardware: Hardware;
  memory: { ram_total_mb: number | null; ram_available_mb: number | null; process_rss_mb: number | null };
  worker_running: boolean;
  recovered_at_start: number;
}

export interface Engine {
  id: string;
  name: string;
  kind: "local" | "remote";
  cost: string;
  method: string;
  capabilities: string[];
  usable: boolean;
  reason: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  project_id: string | null;
  kind: string;
  payload: Record<string, unknown>;
  principal: string;
  level: number;
  status: TaskStatus;
  priority: number;
  attempts: number;
  max_attempts: number;
  approval_id: string | null;
  result: unknown;
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface TaskKind {
  kind: string;
  level: number;
  description: string;
}

export interface Approval {
  id: string;
  principal: string;
  action: string;
  level: number;
  details: Record<string, unknown>;
  status: "pending" | "approved" | "denied" | "used";
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  principal: string;
  action: string;
  level: number | null;
  outcome: string;
  details: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
  chain_ok: boolean;
  first_bad_seq: number | null;
  total: number;
}

export interface Check {
  check: string;
  status: "ok" | "warn" | "fail";
  detail: string;
}

export interface Doctor {
  version: string;
  checks: Check[];
  hardware: Hardware;
  profile: string;
  profile_reason: string;
}

export interface Backup {
  name: string;
  size_kb: number;
}
