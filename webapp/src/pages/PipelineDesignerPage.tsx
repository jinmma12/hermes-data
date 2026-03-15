import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  type OnConnect,
  type Connection,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  MarkerType,
  Handle,
  Position,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { StageType, PipelineStatus } from '../types';
import type { PipelineInstance, PipelineStage } from '../types';
import { pipelines } from '../api/client';
import RecipeEditorPanel from './RecipeEditorPanel';
import ConnectorCatalog from '../components/designer/ConnectorCatalog';
import type { ConnectorItem } from '../components/designer/ConnectorCatalog';
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
  connectorCode?: string;
  onOpenRecipe: (stageId: number, refId: number, stageType: StageType) => void;
  onDeleteNode: (nodeId: string) => void;
  nodeId: string;
  [key: string]: unknown;
}

function CollectNode({ data }: { data: StageNodeData }) {
  return (
    <div className={`w-56 rounded-xl border-2 bg-white shadow-md transition-all hover:shadow-lg ${
      data.isEnabled ? 'border-blue-300' : 'border-slate-200 opacity-60'
    }`}>
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-blue-400 !bg-white" />
      <div className="rounded-t-[10px] bg-blue-50 px-4 py-2.5">
        <div className="flex items-center justify-between">
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
          <button
            onClick={(e) => { e.stopPropagation(); data.onDeleteNode(data.nodeId); }}
            className="rounded p-0.5 text-slate-300 hover:bg-red-50 hover:text-red-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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
        <div className="flex items-center justify-between">
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
          <button
            onClick={(e) => { e.stopPropagation(); data.onDeleteNode(data.nodeId); }}
            className="rounded p-0.5 text-slate-300 hover:bg-red-50 hover:text-red-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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
        <div className="flex items-center justify-between">
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
          <button
            onClick={(e) => { e.stopPropagation(); data.onDeleteNode(data.nodeId); }}
            className="rounded p-0.5 text-slate-300 hover:bg-red-50 hover:text-red-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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
// Pipeline Designer (inner component, needs ReactFlowProvider)
// ============================================================

let nextNodeId = 100;

function PipelineDesignerInner() {
  const { id } = useParams<{ id: string }>();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();

  const [pipeline, setPipeline] = useState<PipelineInstance | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
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

  const handleDeleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    setDirty(true);
  }, []);

  // ---- Load pipeline ----

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
        loadNewPipeline();
      }
    } catch {
      loadNewPipeline();
    } finally {
      setLoading(false);
    }
  }

  function loadNewPipeline() {
    setPipeline({
      id: 0,
      name: 'New Pipeline',
      description: 'Drag connectors from the left panel to build your pipeline',
      monitoring_type: 'API_POLL' as PipelineInstance['monitoring_type'],
      monitoring_config: {},
      status: PipelineStatus.DRAFT,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    setNodes([]);
    setEdges([]);
  }

  function buildFlowFromStages(stages: PipelineStage[]) {
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
        description: 'Configure this stage',
        instanceName: stage.ref_name || '',
        isEnabled: stage.is_enabled,
        stageId: stage.id,
        refId: stage.ref_id,
        onOpenRecipe: handleOpenRecipe,
        onDeleteNode: handleDeleteNode,
        nodeId: `stage-${stage.id}`,
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

    // Track highest ID for new nodes
    const maxId = stages.reduce((max, s) => Math.max(max, s.id), 0);
    nextNodeId = maxId + 1;
  }

  // ---- Node/Edge change handlers ----

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => {
      setNodes((nds) => applyNodeChanges(changes, nds));
      const isPositionOnly = changes.every((c) => c.type === 'position' || c.type === 'dimensions');
      if (!isPositionOnly) setDirty(true);
    },
    []
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      setEdges((eds) => applyEdgeChanges(changes, eds));
      setDirty(true);
    },
    []
  );

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            animated: true,
            style: { stroke: '#94a3b8', strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
          },
          eds
        )
      );
      setDirty(true);
    },
    []
  );

  // ---- Add node (from catalog click or drag-and-drop) ----

  function getNextNodePosition(): { x: number; y: number } {
    if (nodes.length === 0) return { x: 80, y: 150 };
    const rightmost = nodes.reduce((max, n) => (n.position.x > max.position.x ? n : max), nodes[0]);
    return { x: rightmost.position.x + 300, y: rightmost.position.y };
  }

  const addNode = useCallback(
    (connector: ConnectorItem, position?: { x: number; y: number }) => {
      const id = nextNodeId++;
      const nodeTypeMap: Record<StageType, string> = {
        [StageType.COLLECT]: 'collect',
        [StageType.ALGORITHM]: 'algorithm',
        [StageType.TRANSFER]: 'transfer',
      };

      const pos = position || getNextNodePosition();

      const newNode: Node = {
        id: `stage-${id}`,
        type: nodeTypeMap[connector.type],
        position: pos,
        data: {
          label: connector.name,
          stageType: connector.type,
          description: connector.description,
          instanceName: connector.name,
          isEnabled: true,
          stageId: id,
          refId: 0,
          connectorCode: connector.code,
          onOpenRecipe: handleOpenRecipe,
          onDeleteNode: handleDeleteNode,
          nodeId: `stage-${id}`,
        },
      };

      setNodes((nds) => {
        const updated = [...nds, newNode];

        // Auto-connect: if there is exactly one node that has no outgoing edge
        // and its position is to the left, connect it to the new node
        if (nds.length > 0) {
          const rightmost = nds.reduce((max, n) => (n.position.x > max.position.x ? n : max), nds[0]);
          if (!position) {
            // Only auto-connect when added via click (not drop)
            setEdges((eds) => {
              const hasOutgoing = eds.some((e) => e.source === rightmost.id);
              if (!hasOutgoing) {
                return addEdge(
                  {
                    id: `edge-${rightmost.id}-${newNode.id}`,
                    source: rightmost.id,
                    target: newNode.id,
                    animated: true,
                    style: { stroke: '#94a3b8', strokeWidth: 2 },
                    markerEnd: { type: MarkerType.ArrowClosed, color: '#94a3b8' },
                  },
                  eds
                );
              }
              return eds;
            });
          }
        }

        return updated;
      });

      setDirty(true);
    },
    [nodes, handleOpenRecipe, handleDeleteNode]
  );

  // ---- Drag and Drop ----

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const connectorData = event.dataTransfer.getData('application/hermes-connector');
      if (!connectorData) return;

      const connector: ConnectorItem = JSON.parse(connectorData);
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      addNode(connector, position);
    },
    [screenToFlowPosition, addNode]
  );

  // ---- Save pipeline ----

  async function handleSave() {
    if (!pipeline) return;
    setSaving(true);
    try {
      // Build stages from nodes using edge topology to determine order
      const stageOrder = computeStageOrder();
      const stages: Partial<PipelineStage>[] = stageOrder.map((nodeId, idx) => {
        const node = nodes.find((n) => n.id === nodeId);
        if (!node) return null;
        const d = node.data as StageNodeData;
        return {
          id: d.stageId > 0 && d.stageId < 100 ? d.stageId : undefined,
          pipeline_instance_id: pipeline.id,
          stage_order: idx + 1,
          stage_type: d.stageType,
          ref_type: d.stageType === StageType.COLLECT ? 'COLLECTOR' : d.stageType === StageType.ALGORITHM ? 'ALGORITHM' : 'TRANSFER',
          ref_id: d.refId,
          ref_name: d.label,
          is_enabled: d.isEnabled,
          on_error: 'STOP' as PipelineStage['on_error'],
          retry_count: 0,
          retry_delay_seconds: 0,
        };
      }).filter(Boolean) as Partial<PipelineStage>[];

      if (pipeline.id && pipeline.id > 0) {
        await pipelines.update(pipeline.id, { ...pipeline, stages } as Partial<PipelineInstance>);
      } else {
        const created = await pipelines.create({ ...pipeline, stages } as Partial<PipelineInstance>);
        setPipeline(created);
      }
      setDirty(false);
    } catch {
      // Graceful fallback for demo mode
    }
    setSaving(false);
  }

  function computeStageOrder(): string[] {
    // Topological sort using edges
    const inDegree = new Map<string, number>();
    const adjacency = new Map<string, string[]>();
    const nodeIds = new Set(nodes.map((n) => n.id));

    for (const nid of nodeIds) {
      inDegree.set(nid, 0);
      adjacency.set(nid, []);
    }
    for (const edge of edges) {
      if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
        adjacency.get(edge.source)!.push(edge.target);
        inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
      }
    }

    const queue: string[] = [];
    for (const [nid, deg] of inDegree) {
      if (deg === 0) queue.push(nid);
    }

    // Sort roots by x position
    queue.sort((a, b) => {
      const na = nodes.find((n) => n.id === a);
      const nb = nodes.find((n) => n.id === b);
      return (na?.position.x || 0) - (nb?.position.x || 0);
    });

    const result: string[] = [];
    while (queue.length > 0) {
      const curr = queue.shift()!;
      result.push(curr);
      for (const next of adjacency.get(curr) || []) {
        inDegree.set(next, (inDegree.get(next) || 0) - 1);
        if (inDegree.get(next) === 0) queue.push(next);
      }
    }

    // Add any disconnected nodes not yet in result (sorted by x)
    const remaining = nodes
      .filter((n) => !result.includes(n.id))
      .sort((a, b) => a.position.x - b.position.x)
      .map((n) => n.id);

    return [...result, ...remaining];
  }

  // ---- Activate / Deactivate ----

  async function handleActivate() {
    if (!pipeline) return;
    try {
      await pipelines.activate(pipeline.id);
      setPipeline({ ...pipeline, status: PipelineStatus.ACTIVE });
    } catch {
      setPipeline({ ...pipeline, status: PipelineStatus.ACTIVE });
    }
  }

  async function handleDeactivate() {
    if (!pipeline) return;
    try {
      await pipelines.deactivate(pipeline.id);
      setPipeline({ ...pipeline, status: PipelineStatus.PAUSED });
    } catch {
      setPipeline({ ...pipeline, status: PipelineStatus.PAUSED });
    }
  }

  // ---- Pipeline name editing ----

  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState('');

  function startEditName() {
    setNameValue(pipeline?.name || '');
    setEditingName(true);
  }

  function commitName() {
    if (pipeline && nameValue.trim()) {
      setPipeline({ ...pipeline, name: nameValue.trim() });
      setDirty(true);
    }
    setEditingName(false);
  }

  // ---- Render ----

  if (loading) return <LoadingSpinner message="Loading pipeline designer..." />;

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between rounded-t-xl border border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              {editingName ? (
                <input
                  autoFocus
                  value={nameValue}
                  onChange={(e) => setNameValue(e.target.value)}
                  onBlur={commitName}
                  onKeyDown={(e) => { if (e.key === 'Enter') commitName(); if (e.key === 'Escape') setEditingName(false); }}
                  className="rounded border border-vessel-300 px-2 py-0.5 text-lg font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-vessel-400"
                />
              ) : (
                <h1
                  className="cursor-pointer text-lg font-bold text-slate-900 hover:text-vessel-700"
                  onClick={startEditName}
                  title="Click to rename"
                >
                  {pipeline?.name || 'New Pipeline'}
                </h1>
              )}
              {pipeline && <StatusBadge status={pipeline.status} />}
              {dirty && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                  Unsaved changes
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">
              {nodes.length} stage{nodes.length !== 1 ? 's' : ''} &middot; {edges.length} connection{edges.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="btn-secondary text-xs"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? (
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
              </svg>
            )}
            Save
          </button>

          {pipeline?.status === PipelineStatus.ACTIVE ? (
            <button className="btn-secondary text-xs !border-red-200 !text-red-600 hover:!bg-red-50" onClick={handleDeactivate}>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z" />
              </svg>
              Deactivate
            </button>
          ) : (
            <button
              className="btn-primary text-xs"
              onClick={handleActivate}
              disabled={nodes.length === 0}
              title={nodes.length === 0 ? 'Add at least one stage' : 'Activate pipeline'}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
              </svg>
              Activate
            </button>
          )}
        </div>
      </div>

      {/* Main content: Catalog + Canvas + Recipe Panel */}
      <div className="flex flex-1 overflow-hidden rounded-b-xl border border-t-0 border-slate-200">
        {/* Left sidebar: Connector Catalog */}
        <ConnectorCatalog onAddNode={addNode} />

        {/* React Flow Canvas */}
        <div
          className="flex-1"
          ref={reactFlowWrapper}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            className="bg-slate-50"
            proOptions={{ hideAttribution: true }}
            deleteKeyCode={['Backspace', 'Delete']}
            snapToGrid
            snapGrid={[20, 20]}
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

            {/* Empty state overlay */}
            {nodes.length === 0 && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="rounded-2xl border-2 border-dashed border-slate-300 bg-white/80 px-12 py-10 text-center shadow-sm backdrop-blur-sm">
                  <svg className="mx-auto h-12 w-12 text-slate-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                  </svg>
                  <p className="mt-3 text-sm font-medium text-slate-500">Drop connectors here to build your pipeline</p>
                  <p className="mt-1 text-xs text-slate-400">Or click a connector in the left panel</p>
                </div>
              </div>
            )}
          </ReactFlow>
        </div>

        {/* Right panel: Recipe Editor */}
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

// ============================================================
// Wrapper with ReactFlowProvider
// ============================================================

export default function PipelineDesignerPage() {
  return (
    <ReactFlowProvider>
      <PipelineDesignerInner />
    </ReactFlowProvider>
  );
}
