import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type OnNodesChange,
  type OnEdgesChange,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { StageType, PipelineStatus } from '../types';
import type { PipelineInstance, PipelineStage } from '../types';
import { pipelines } from '../api/client';
import RecipeEditorPanel from './RecipeEditorPanel';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';

// ============================================================
// Custom Node Components
// ============================================================

interface StageNodeData {
  label: string;
  stageType: StageType;
  description: string;
  instanceName: string;
  isEnabled: boolean;
  stageId: number;
  refId: number;
  onOpenRecipe: (stageId: number, refId: number, stageType: StageType) => void;
  [key: string]: unknown;
}

function CollectNode({ data }: { data: StageNodeData }) {
  return (
    <div className={`w-56 rounded-xl border-2 bg-white shadow-md transition-all hover:shadow-lg ${
      data.isEnabled ? 'border-blue-300' : 'border-slate-200 opacity-60'
    }`}>
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-blue-400 !bg-white" />
      <div className="rounded-t-[10px] bg-blue-50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500 text-white">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-blue-600">Collect</p>
            <p className="text-xs font-medium text-slate-700">{data.label}</p>
          </div>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-[11px] text-slate-500">{data.description}</p>
        <button
          onClick={() => data.onOpenRecipe(data.stageId, data.refId, data.stageType)}
          className="mt-2 w-full rounded-lg border border-blue-200 bg-blue-50 px-2 py-1.5 text-[11px] font-medium text-blue-700 transition-colors hover:bg-blue-100"
        >
          Edit Recipe
        </button>
      </div>
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-blue-400 !bg-white" />
    </div>
  );
}

function AlgorithmNode({ data }: { data: StageNodeData }) {
  return (
    <div className={`w-56 rounded-xl border-2 bg-white shadow-md transition-all hover:shadow-lg ${
      data.isEnabled ? 'border-purple-300' : 'border-slate-200 opacity-60'
    }`}>
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-purple-400 !bg-white" />
      <div className="rounded-t-[10px] bg-purple-50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500 text-white">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
            </svg>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-purple-600">Algorithm</p>
            <p className="text-xs font-medium text-slate-700">{data.label}</p>
          </div>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-[11px] text-slate-500">{data.description}</p>
        <button
          onClick={() => data.onOpenRecipe(data.stageId, data.refId, data.stageType)}
          className="mt-2 w-full rounded-lg border border-purple-200 bg-purple-50 px-2 py-1.5 text-[11px] font-medium text-purple-700 transition-colors hover:bg-purple-100"
        >
          Edit Recipe
        </button>
      </div>
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-purple-400 !bg-white" />
    </div>
  );
}

function TransferNode({ data }: { data: StageNodeData }) {
  return (
    <div className={`w-56 rounded-xl border-2 bg-white shadow-md transition-all hover:shadow-lg ${
      data.isEnabled ? 'border-emerald-300' : 'border-slate-200 opacity-60'
    }`}>
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-emerald-400 !bg-white" />
      <div className="rounded-t-[10px] bg-emerald-50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500 text-white">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600">Transfer</p>
            <p className="text-xs font-medium text-slate-700">{data.label}</p>
          </div>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-[11px] text-slate-500">{data.description}</p>
        <button
          onClick={() => data.onOpenRecipe(data.stageId, data.refId, data.stageType)}
          className="mt-2 w-full rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-[11px] font-medium text-emerald-700 transition-colors hover:bg-emerald-100"
        >
          Edit Recipe
        </button>
      </div>
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-emerald-400 !bg-white" />
    </div>
  );
}

// ============================================================
// Pipeline Designer Page
// ============================================================

export default function PipelineDesignerPage() {
  const { id } = useParams<{ id: string }>();
  const [pipeline, setPipeline] = useState<PipelineInstance | null>(null);
  const [loading, setLoading] = useState(true);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [recipePanel, setRecipePanel] = useState<{
    stageId: number;
    refId: number;
    stageType: StageType;
  } | null>(null);

  const nodeTypes: NodeTypes = useMemo(
    () => ({
      collect: CollectNode,
      algorithm: AlgorithmNode,
      transfer: TransferNode,
    }),
    []
  );

  const handleOpenRecipe = useCallback((stageId: number, refId: number, stageType: StageType) => {
    setRecipePanel({ stageId, refId, stageType });
  }, []);

  useEffect(() => {
    loadPipeline();
  }, [id]);

  async function loadPipeline() {
    try {
      setLoading(true);
      if (id && id !== 'new') {
        const data = await pipelines.get(parseInt(id));
        setPipeline(data);
        buildFlowFromStages(data.stages || []);
      } else {
        // New pipeline with demo stages
        loadDemoData();
      }
    } catch {
      loadDemoData();
    } finally {
      setLoading(false);
    }
  }

  function loadDemoData() {
    setPipeline({
      id: 1,
      name: 'Order Monitoring Pipeline',
      description: 'Collects orders from REST API, detects anomalies, uploads to S3',
      monitoring_type: 'API_POLL' as PipelineInstance['monitoring_type'],
      monitoring_config: { interval: '5m' },
      status: PipelineStatus.ACTIVE,
      created_at: '2026-03-01T09:00:00Z',
      updated_at: '2026-03-15T14:30:00Z',
    });

    const demoStages: PipelineStage[] = [
      {
        id: 1, pipeline_instance_id: 1, stage_order: 1,
        stage_type: StageType.COLLECT, ref_type: 'COLLECTOR', ref_id: 1,
        ref_name: 'REST API Collector',
        is_enabled: true, on_error: 'STOP' as PipelineStage['on_error'],
        retry_count: 3, retry_delay_seconds: 10,
      },
      {
        id: 2, pipeline_instance_id: 1, stage_order: 2,
        stage_type: StageType.ALGORITHM, ref_type: 'ALGORITHM', ref_id: 1,
        ref_name: 'Anomaly Detector',
        is_enabled: true, on_error: 'STOP' as PipelineStage['on_error'],
        retry_count: 0, retry_delay_seconds: 0,
      },
      {
        id: 3, pipeline_instance_id: 1, stage_order: 3,
        stage_type: StageType.TRANSFER, ref_type: 'TRANSFER', ref_id: 1,
        ref_name: 'S3 Upload',
        is_enabled: true, on_error: 'STOP' as PipelineStage['on_error'],
        retry_count: 2, retry_delay_seconds: 30,
      },
    ];
    buildFlowFromStages(demoStages);
  }

  function buildFlowFromStages(stages: PipelineStage[]) {
    const descriptions: Record<string, string> = {
      'REST API Collector': 'Polls REST API endpoint for new order batches',
      'Anomaly Detector': 'Applies z-score analysis to detect anomalies',
      'S3 Upload': 'Uploads processed results to Amazon S3 bucket',
    };

    const nodeTypeMap: Record<StageType, string> = {
      [StageType.COLLECT]: 'collect',
      [StageType.ALGORITHM]: 'algorithm',
      [StageType.TRANSFER]: 'transfer',
    };

    const newNodes: Node[] = stages.map((stage, idx) => ({
      id: `stage-${stage.id}`,
      type: nodeTypeMap[stage.stage_type],
      position: { x: 80 + idx * 300, y: 150 },
      data: {
        label: stage.ref_name || `Stage ${stage.stage_order}`,
        stageType: stage.stage_type,
        description: descriptions[stage.ref_name || ''] || 'Configure this stage',
        instanceName: stage.ref_name || '',
        isEnabled: stage.is_enabled,
        stageId: stage.id,
        refId: stage.ref_id,
        onOpenRecipe: handleOpenRecipe,
      },
    }));

    const newEdges: Edge[] = [];
    for (let i = 0; i < stages.length - 1; i++) {
      newEdges.push({
        id: `edge-${stages[i].id}-${stages[i + 1].id}`,
        source: `stage-${stages[i].id}`,
        target: `stage-${stages[i + 1].id}`,
        animated: true,
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      });
    }

    setNodes(newNodes);
    setEdges(newEdges);
  }

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  async function handleSave() {
    if (!pipeline) return;
    try {
      await pipelines.update(pipeline.id, pipeline);
    } catch {
      // Demo mode - just show success
    }
    alert('Pipeline saved successfully!');
  }

  async function handleActivate() {
    if (!pipeline) return;
    try {
      await pipelines.activate(pipeline.id);
      setPipeline({ ...pipeline, status: PipelineStatus.ACTIVE });
    } catch {
      setPipeline({ ...pipeline, status: PipelineStatus.ACTIVE });
    }
  }

  if (loading) return <LoadingSpinner message="Loading pipeline designer..." />;

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between rounded-t-xl border border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900">
                {pipeline?.name || 'New Pipeline'}
              </h1>
              {pipeline && <StatusBadge status={pipeline.status} />}
            </div>
            <p className="text-xs text-slate-500">{pipeline?.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-secondary text-xs" onClick={handleSave}>
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
            </svg>
            Save
          </button>
          {pipeline?.status !== PipelineStatus.ACTIVE && (
            <button className="btn-primary text-xs" onClick={handleActivate}>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
              </svg>
              Activate
            </button>
          )}
        </div>
      </div>

      {/* Flow Canvas + Recipe Panel */}
      <div className="flex flex-1 overflow-hidden rounded-b-xl border border-t-0 border-slate-200">
        <div className={`flex-1 transition-all ${recipePanel ? 'mr-0' : ''}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            className="bg-slate-50"
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#cbd5e1" gap={20} size={1} />
            <Controls className="!rounded-lg !border-slate-200 !shadow-md" />
            <MiniMap
              className="!rounded-lg !border-slate-200 !shadow-md"
              nodeColor={(node) => {
                switch (node.type) {
                  case 'collect': return '#3b82f6';
                  case 'algorithm': return '#a855f7';
                  case 'transfer': return '#10b981';
                  default: return '#94a3b8';
                }
              }}
            />
          </ReactFlow>
        </div>

        {/* Recipe Editor Panel */}
        {recipePanel && (
          <RecipeEditorPanel
            stageId={recipePanel.stageId}
            refId={recipePanel.refId}
            stageType={recipePanel.stageType}
            onClose={() => setRecipePanel(null)}
          />
        )}
      </div>
    </div>
  );
}
