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

export interface Agent {
  id: string;
  name: string;
  version: string;
  role: string;
  objective: string;
  task_types: string[];
  success_criteria: string;
  builtin: boolean;
  level: number;
}

export interface AgentRun {
  id: string;
  agent_id: string;
  agent_version: string;
  mode: "agent" | "director" | "council";
  goal: string;
  status: "running" | "succeeded" | "failed";
  output: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  private: boolean;
  created_at: string;
  updated_at: string;
  messages?: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  seq: number;
  role: "user" | "assistant";
  content: string;
  status: "ok" | "error";
  engine: string | null;
  task_type: string | null;
  ms: number | null;
  created_at: string;
}

export interface ChatStatus {
  online: boolean;
  engine: string | null;
  reason: string;
  web: boolean;
}

export interface DocumentFile {
  name: string;
  size: number;
  modified: number;
}

export interface LabDataset {
  ref: string;
  name: string;
  version: string;
  description: string;
  items: number;
  hash: string;
  builtin: boolean;
}

export interface LabMetrics {
  n: number;
  correct: number;
  accuracy: number;
  errors: number;
  latency_ms_mean: number | null;
  latency_ms_p95: number | null;
  engines: Record<string, number>;
}

export interface LabExperiment {
  id: string;
  name: string;
  subject: string;
  subject_version: string;
  status: "running" | "completed" | "failed" | "interrupted";
  created_at: string;
  dataset: string;
  seed: number;
  deterministic: boolean;
  reproduced_from: string | null;
  metrics: LabMetrics | null;
  evaluation: string | null;
}

export interface LabResult {
  item_idx: number;
  input: string;
  expected: unknown;
  output: string | null;
  correct: boolean;
  latency_ms: number;
  engine: string | null;
  error: string | null;
}

export interface LabDetail {
  experiment: LabExperiment & {
    objective: string;
    hypothesis: string;
    dataset_hash: string;
    resources: Record<string, number | null> | null;
    environment: Record<string, unknown>;
  };
  results: LabResult[];
}

export interface LabComparison {
  comparable: boolean;
  verdict: string;
  a_subject: string;
  b_subject: string;
  paired_items?: number;
  accuracy_a?: number;
  accuracy_b?: number;
  only_a_correct?: number;
  only_b_correct?: number;
  mcnemar_p?: number;
  diff_ci95?: [number, number];
  significant?: boolean;
}

export interface EngineComponent {
  name: string;
  kind: "algoritmo" | "strumento" | "modello esterno";
  description: string;
  available: boolean;
}

export interface EngineOperation {
  name: string;
  level: number;
  description: string;
  params: string;
}

export interface GenesisEngineManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  uses_external_model: boolean;
  components: EngineComponent[];
  operations: EngineOperation[];
}

export interface ModelEntry {
  id: string;
  family: string;
  params_b: number;
  license: string;
  context: number;
  source: string;
  notes: string;
  verification: string;
  best: { verdict: string; quant: string; where: string; need: { total_gb: number }; notes: string[] };
}

export interface ModelsResponse {
  hardware: { ram_mb: number | null; vram_mb: number; os: string; profile: string };
  models: ModelEntry[];
}

export interface ImprovableComponent {
  name: string;
  description: string;
  active: string;
  previous: string | null;
  versions: string[];
  benchmarks: string[];
}

export interface Proposal {
  id: string;
  component: string;
  stable: string;
  candidate: string;
  problem: string;
  cause: string;
  proposal: string;
  status: "proposed" | "evaluated" | "promoted" | "rejected" | "rolled_back";
  decision: string | null;
  created_at: string;
  evaluation: {
    results: { dataset: string; accuracy_stable: number; accuracy_candidate: number; verdict: string }[];
    recommendation: string;
    promotable: boolean;
    caveat: string;
  } | null;
}
