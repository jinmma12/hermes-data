import axios from 'axios';
import type {
  CollectorDefinition,
  AlgorithmDefinition,
  TransferDefinition,
  DefinitionVersion,
  CollectorInstance,
  AlgorithmInstance,
  TransferInstance,
  InstanceVersion,
  PipelineInstance,
  PipelineStage,
  PipelineActivation,
  Job,
  JobExecution,
  ExecutionEventLog,
  ReprocessPayload,
  BulkReprocessPayload,
  PaginatedResponse,
  MonitorStats,
  PluginInfo,
  Recipe,
} from '../types';

// ============================================================
// Axios Instance
// ============================================================

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// ============================================================
// Definition APIs
// ============================================================

export const definitions = {
  // Collectors
  listCollectors: () =>
    api.get<CollectorDefinition[]>('/definitions/collectors').then((r) => r.data),
  createCollector: (data: Partial<CollectorDefinition>) =>
    api.post<CollectorDefinition>('/definitions/collectors', data).then((r) => r.data),
  getCollector: (id: number) =>
    api.get<CollectorDefinition>(`/definitions/collectors/${id}`).then((r) => r.data),
  getCollectorVersions: (id: number) =>
    api.get<DefinitionVersion[]>(`/definitions/collectors/${id}/versions`).then((r) => r.data),
  createCollectorVersion: (id: number, data: Partial<DefinitionVersion>) =>
    api.post<DefinitionVersion>(`/definitions/collectors/${id}/versions`, data).then((r) => r.data),

  // Algorithms
  listAlgorithms: () =>
    api.get<AlgorithmDefinition[]>('/definitions/algorithms').then((r) => r.data),
  createAlgorithm: (data: Partial<AlgorithmDefinition>) =>
    api.post<AlgorithmDefinition>('/definitions/algorithms', data).then((r) => r.data),
  getAlgorithm: (id: number) =>
    api.get<AlgorithmDefinition>(`/definitions/algorithms/${id}`).then((r) => r.data),
  getAlgorithmVersions: (id: number) =>
    api.get<DefinitionVersion[]>(`/definitions/algorithms/${id}/versions`).then((r) => r.data),
  createAlgorithmVersion: (id: number, data: Partial<DefinitionVersion>) =>
    api.post<DefinitionVersion>(`/definitions/algorithms/${id}/versions`, data).then((r) => r.data),

  // Transfers
  listTransfers: () =>
    api.get<TransferDefinition[]>('/definitions/transfers').then((r) => r.data),
  createTransfer: (data: Partial<TransferDefinition>) =>
    api.post<TransferDefinition>('/definitions/transfers', data).then((r) => r.data),
  getTransfer: (id: number) =>
    api.get<TransferDefinition>(`/definitions/transfers/${id}`).then((r) => r.data),
  getTransferVersions: (id: number) =>
    api.get<DefinitionVersion[]>(`/definitions/transfers/${id}/versions`).then((r) => r.data),
  createTransferVersion: (id: number, data: Partial<DefinitionVersion>) =>
    api.post<DefinitionVersion>(`/definitions/transfers/${id}/versions`, data).then((r) => r.data),
};

// ============================================================
// Instance APIs
// ============================================================

export const instances = {
  // Collectors
  listCollectors: () =>
    api.get<CollectorInstance[]>('/instances/collectors').then((r) => r.data),
  createCollector: (data: Partial<CollectorInstance>) =>
    api.post<CollectorInstance>('/instances/collectors', data).then((r) => r.data),
  getCollector: (id: number) =>
    api.get<CollectorInstance>(`/instances/collectors/${id}`).then((r) => r.data),
  updateCollector: (id: number, data: Partial<CollectorInstance>) =>
    api.put<CollectorInstance>(`/instances/collectors/${id}`, data).then((r) => r.data),
  getCollectorRecipes: (id: number) =>
    api.get<Recipe[]>(`/instances/collectors/${id}/recipes`).then((r) => r.data),
  createCollectorRecipe: (id: number, data: { config_json: Record<string, unknown>; change_note: string }) =>
    api.post<InstanceVersion>(`/instances/collectors/${id}/recipes`, data).then((r) => r.data),
  getCollectorRecipeDiff: (id: number, from: number, to: number) =>
    api.get(`/instances/collectors/${id}/recipes/diff?from=${from}&to=${to}`).then((r) => r.data),
  publishCollectorRecipe: (id: number, version: number) =>
    api.post(`/instances/collectors/${id}/recipes/${version}/publish`).then((r) => r.data),

  // Algorithms
  listAlgorithms: () =>
    api.get<AlgorithmInstance[]>('/instances/algorithms').then((r) => r.data),
  createAlgorithm: (data: Partial<AlgorithmInstance>) =>
    api.post<AlgorithmInstance>('/instances/algorithms', data).then((r) => r.data),
  getAlgorithm: (id: number) =>
    api.get<AlgorithmInstance>(`/instances/algorithms/${id}`).then((r) => r.data),
  updateAlgorithm: (id: number, data: Partial<AlgorithmInstance>) =>
    api.put<AlgorithmInstance>(`/instances/algorithms/${id}`, data).then((r) => r.data),
  getAlgorithmRecipes: (id: number) =>
    api.get<Recipe[]>(`/instances/algorithms/${id}/recipes`).then((r) => r.data),
  createAlgorithmRecipe: (id: number, data: { config_json: Record<string, unknown>; change_note: string }) =>
    api.post<InstanceVersion>(`/instances/algorithms/${id}/recipes`, data).then((r) => r.data),

  // Transfers
  listTransfers: () =>
    api.get<TransferInstance[]>('/instances/transfers').then((r) => r.data),
  createTransfer: (data: Partial<TransferInstance>) =>
    api.post<TransferInstance>('/instances/transfers', data).then((r) => r.data),
  getTransfer: (id: number) =>
    api.get<TransferInstance>(`/instances/transfers/${id}`).then((r) => r.data),
  updateTransfer: (id: number, data: Partial<TransferInstance>) =>
    api.put<TransferInstance>(`/instances/transfers/${id}`, data).then((r) => r.data),
  getTransferRecipes: (id: number) =>
    api.get<Recipe[]>(`/instances/transfers/${id}/recipes`).then((r) => r.data),
  createTransferRecipe: (id: number, data: { config_json: Record<string, unknown>; change_note: string }) =>
    api.post<InstanceVersion>(`/instances/transfers/${id}/recipes`, data).then((r) => r.data),
};

// ============================================================
// Pipeline APIs
// ============================================================

export const pipelines = {
  list: () =>
    api.get<PipelineInstance[]>('/pipelines').then((r) => r.data),
  create: (data: Partial<PipelineInstance>) =>
    api.post<PipelineInstance>('/pipelines', data).then((r) => r.data),
  get: (id: number) =>
    api.get<PipelineInstance>(`/pipelines/${id}`).then((r) => r.data),
  update: (id: number, data: Partial<PipelineInstance>) =>
    api.put<PipelineInstance>(`/pipelines/${id}`, data).then((r) => r.data),

  // Stages
  getStages: (id: number) =>
    api.get<PipelineStage[]>(`/pipelines/${id}/stages`).then((r) => r.data),
  createStage: (id: number, data: Partial<PipelineStage>) =>
    api.post<PipelineStage>(`/pipelines/${id}/stages`, data).then((r) => r.data),
  updateStage: (id: number, stageId: number, data: Partial<PipelineStage>) =>
    api.put<PipelineStage>(`/pipelines/${id}/stages/${stageId}`, data).then((r) => r.data),
  deleteStage: (id: number, stageId: number) =>
    api.delete(`/pipelines/${id}/stages/${stageId}`).then((r) => r.data),
  reorderStages: (id: number, stageIds: number[]) =>
    api.put(`/pipelines/${id}/stages/reorder`, { stage_ids: stageIds }).then((r) => r.data),

  // Lifecycle
  activate: (id: number) =>
    api.post<PipelineActivation>(`/pipelines/${id}/activate`).then((r) => r.data),
  deactivate: (id: number) =>
    api.post(`/pipelines/${id}/deactivate`).then((r) => r.data),
  getActivations: (id: number) =>
    api.get<PipelineActivation[]>(`/pipelines/${id}/activations`).then((r) => r.data),
  getStatus: (id: number) =>
    api.get<PipelineActivation>(`/pipelines/${id}/status`).then((r) => r.data),
};

// ============================================================
// Job APIs
// ============================================================

export interface JobFilters {
  status?: string;
  pipeline_instance_id?: number;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const jobs = {
  list: (filters?: JobFilters) =>
    api.get<PaginatedResponse<Job>>('/jobs', { params: filters }).then((r) => r.data),
  get: (id: number) =>
    api.get<Job>(`/jobs/${id}`).then((r) => r.data),
  getExecutions: (id: number) =>
    api.get<JobExecution[]>(`/jobs/${id}/executions`).then((r) => r.data),
  getExecution: (id: number, execId: number) =>
    api.get<JobExecution>(`/jobs/${id}/executions/${execId}`).then((r) => r.data),
  getExecutionSteps: (id: number, execId: number) =>
    api.get(`/jobs/${id}/executions/${execId}/stages`).then((r) => r.data),
  getExecutionSnapshot: (id: number, execId: number) =>
    api.get(`/jobs/${id}/executions/${execId}/snapshot`).then((r) => r.data),
  getExecutionLogs: (id: number, execId: number) =>
    api.get<ExecutionEventLog[]>(`/jobs/${id}/executions/${execId}/logs`).then((r) => r.data),

  // Reprocess
  reprocess: (id: number, data: ReprocessPayload) =>
    api.post(`/jobs/${id}/reprocess`, data).then((r) => r.data),
  bulkReprocess: (data: BulkReprocessPayload) =>
    api.post('/jobs/bulk-reprocess', data).then((r) => r.data),
};

// ============================================================
// Monitor APIs
// ============================================================

export const monitor = {
  getStats: () =>
    api.get<MonitorStats>('/monitor/stats').then((r) => r.data),
  getActiveActivations: () =>
    api.get<PipelineActivation[]>('/monitor/activations').then((r) => r.data),
  getRecentJobs: (limit: number = 20) =>
    api.get<Job[]>(`/monitor/recent-jobs?limit=${limit}`).then((r) => r.data),
};

// ============================================================
// Plugin APIs
// ============================================================

export const plugins = {
  list: () =>
    api.get<PluginInfo[]>('/plugins').then((r) => r.data),
  install: (name: string) =>
    api.post(`/plugins/${name}/install`).then((r) => r.data),
  uninstall: (name: string) =>
    api.post(`/plugins/${name}/uninstall`).then((r) => r.data),
};

export default api;
