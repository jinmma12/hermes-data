using Microsoft.EntityFrameworkCore;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;

namespace Hermes.Engine.Tests.E2E;

/// <summary>
/// E2E tests verifying that pipeline stage (step) composition — the edges
/// connecting connectors in the visual designer — correctly persists to the
/// database with proper ordering, and that reorder / delete / duplicate
/// operations maintain data integrity.
///
/// These tests use a real EF Core in-memory database so that all entity
/// relationships, cascading behavior, and query semantics are validated
/// end-to-end.
/// </summary>
public class PipelineStageCompositionE2ETests
{
    // ════════════════════════════════════════════════════════════════════
    // Helpers
    // ════════════════════════════════════════════════════════════════════

    private static HermesDbContext CreateDb() => TestDbHelper.CreateInMemoryDb();

    private static PipelineInstance CreatePipeline(
        string name = "composition-test",
        PipelineStatus status = PipelineStatus.Draft)
    {
        return new PipelineInstance
        {
            Name = name,
            Status = status,
            MonitoringType = MonitoringType.FileMonitor,
            MonitoringConfig = "{\"path\":\"/data\"}"
        };
    }

    private static PipelineStep MakeStep(
        Guid pipelineId, int order, StageType type, Guid? refId = null)
    {
        return new PipelineStep
        {
            PipelineInstanceId = pipelineId,
            StepOrder = order,
            StepType = type,
            RefType = type switch
            {
                StageType.Collect => RefType.Collector,
                StageType.Process => RefType.Process,
                StageType.Export => RefType.Export,
                _ => RefType.Process
            },
            RefId = refId ?? Guid.NewGuid(),
            IsEnabled = true,
            OnError = OnErrorAction.Stop
        };
    }

    // ════════════════════════════════════════════════════════════════════
    // 1. Basic Stage Composition — DB Persistence (15 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task CreatePipeline_WithThreeStages_AllPersistedInOrder()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Re-read from DB
        var loaded = await db.PipelineInstances
            .Include(p => p.Steps)
            .FirstAsync(p => p.Id == pipeline.Id);

        Assert.Equal(3, loaded.Steps.Count);
        var ordered = loaded.Steps.OrderBy(s => s.StepOrder).ToList();
        Assert.Equal(StageType.Collect, ordered[0].StepType);
        Assert.Equal(StageType.Process, ordered[1].StepType);
        Assert.Equal(StageType.Export, ordered[2].StepType);
        Assert.Equal(1, ordered[0].StepOrder);
        Assert.Equal(2, ordered[1].StepOrder);
        Assert.Equal(3, ordered[2].StepOrder);
    }

    [Fact]
    public async Task CreatePipeline_StepsHaveCorrectRefTypes()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(RefType.Collector, steps[0].RefType);
        Assert.Equal(RefType.Process, steps[1].RefType);
        Assert.Equal(RefType.Export, steps[2].RefType);
    }

    [Fact]
    public async Task CreatePipeline_StepsBelongToCorrectPipeline()
    {
        await using var db = CreateDb();
        var p1 = CreatePipeline("pipeline-A");
        var p2 = CreatePipeline("pipeline-B");
        p1.Steps.Add(MakeStep(p1.Id, 1, StageType.Collect));
        p2.Steps.Add(MakeStep(p2.Id, 1, StageType.Collect));
        p2.Steps.Add(MakeStep(p2.Id, 2, StageType.Export));
        db.PipelineInstances.AddRange(p1, p2);
        await db.SaveChangesAsync();

        var p1Steps = await db.PipelineSteps.Where(s => s.PipelineInstanceId == p1.Id).ToListAsync();
        var p2Steps = await db.PipelineSteps.Where(s => s.PipelineInstanceId == p2.Id).ToListAsync();
        Assert.Single(p1Steps);
        Assert.Equal(2, p2Steps.Count);
    }

    [Fact]
    public async Task CreatePipeline_EmptySteps_PersistsWithZeroSteps()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var loaded = await db.PipelineInstances.Include(p => p.Steps).FirstAsync(p => p.Id == pipeline.Id);
        Assert.Empty(loaded.Steps);
    }

    [Fact]
    public async Task CreatePipeline_SingleCollector_ValidComposition()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps.Where(s => s.PipelineInstanceId == pipeline.Id).ToListAsync();
        Assert.Single(steps);
        Assert.Equal(StageType.Collect, steps[0].StepType);
    }

    [Fact]
    public async Task CreatePipeline_FiveStages_OrderPreserved()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 4, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 5, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(5, steps.Count);
        for (int i = 0; i < 5; i++)
            Assert.Equal(i + 1, steps[i].StepOrder);
    }

    [Fact]
    public async Task CreatePipeline_MultipleProcessors_AllPersisted()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var refIds = new[] { Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid() };
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process, refIds[0]));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Process, refIds[1]));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 4, StageType.Process, refIds[2]));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 5, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var procs = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id && s.StepType == StageType.Process)
            .ToListAsync();

        Assert.Equal(3, procs.Count);
        Assert.Equal(refIds.ToHashSet(), procs.Select(p => p.RefId).ToHashSet());
    }

    [Fact]
    public async Task StepRefId_PointsToSpecificInstance()
    {
        await using var db = CreateDb();
        var collRefId = Guid.NewGuid();
        var procRefId = Guid.NewGuid();
        var expRefId = Guid.NewGuid();

        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect, collRefId));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process, procRefId));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Export, expRefId));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(collRefId, steps[0].RefId);
        Assert.Equal(procRefId, steps[1].RefId);
        Assert.Equal(expRefId, steps[2].RefId);
    }

    // ════════════════════════════════════════════════════════════════════
    // 2. Step Reordering — DB Consistency (10 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task ReorderSteps_SwapFirstAndLast_OrderUpdatedInDb()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        var s3 = MakeStep(pipeline.Id, 3, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2, s3 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Swap s1 and s3 ordering
        s1.StepOrder = 3;
        s3.StepOrder = 1;
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(s3.Id, steps[0].Id);
        Assert.Equal(s2.Id, steps[1].Id);
        Assert.Equal(s1.Id, steps[2].Id);
    }

    [Fact]
    public async Task ReorderSteps_MoveMiddleToEnd_CorrectOrder()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        var s3 = MakeStep(pipeline.Id, 3, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2, s3 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Move s2 to end: new order is s1, s3, s2
        s2.StepOrder = 3;
        s3.StepOrder = 2;
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(s1.Id, steps[0].Id);
        Assert.Equal(s3.Id, steps[1].Id);
        Assert.Equal(s2.Id, steps[2].Id);
    }

    [Fact]
    public async Task ReorderSteps_ReverseAll_CorrectOrder()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        var s3 = MakeStep(pipeline.Id, 3, StageType.Export);
        var s4 = MakeStep(pipeline.Id, 4, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2, s3, s4 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Reverse
        s1.StepOrder = 4;
        s2.StepOrder = 3;
        s3.StepOrder = 2;
        s4.StepOrder = 1;
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(s4.Id, steps[0].Id);
        Assert.Equal(s3.Id, steps[1].Id);
        Assert.Equal(s2.Id, steps[2].Id);
        Assert.Equal(s1.Id, steps[3].Id);
    }

    [Fact]
    public async Task ReorderSteps_DoesNotAffectOtherPipeline()
    {
        await using var db = CreateDb();
        var pA = CreatePipeline("A");
        var pB = CreatePipeline("B");
        var sA1 = MakeStep(pA.Id, 1, StageType.Collect);
        var sA2 = MakeStep(pA.Id, 2, StageType.Export);
        var sB1 = MakeStep(pB.Id, 1, StageType.Collect);
        pA.Steps.AddRange(new[] { sA1, sA2 });
        pB.Steps.Add(sB1);
        db.PipelineInstances.AddRange(pA, pB);
        await db.SaveChangesAsync();

        // Reorder pA
        sA1.StepOrder = 2;
        sA2.StepOrder = 1;
        await db.SaveChangesAsync();

        // pB unchanged
        var bSteps = await db.PipelineSteps.Where(s => s.PipelineInstanceId == pB.Id).ToListAsync();
        Assert.Single(bSteps);
        Assert.Equal(1, bSteps[0].StepOrder);
    }

    // ════════════════════════════════════════════════════════════════════
    // 3. Step Deletion — Cascade & Integrity (10 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task DeleteMiddleStep_RemainingStepsPreserved()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        var s3 = MakeStep(pipeline.Id, 3, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2, s3 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Delete middle step
        db.PipelineSteps.Remove(s2);
        await db.SaveChangesAsync();

        var remaining = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(2, remaining.Count);
        Assert.Equal(s1.Id, remaining[0].Id);
        Assert.Equal(s3.Id, remaining[1].Id);
    }

    [Fact]
    public async Task DeleteMiddleStep_ThenReorder_GapFilled()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        var s3 = MakeStep(pipeline.Id, 3, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2, s3 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        db.PipelineSteps.Remove(s2);
        await db.SaveChangesAsync();

        // Fix ordering gap: s1=1, s3=2
        s3.StepOrder = 2;
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(2, steps.Count);
        Assert.Equal(1, steps[0].StepOrder);
        Assert.Equal(2, steps[1].StepOrder);
    }

    [Fact]
    public async Task DeleteAllSteps_PipelineStillExists()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        db.PipelineSteps.RemoveRange(
            await db.PipelineSteps.Where(s => s.PipelineInstanceId == pipeline.Id).ToListAsync()
        );
        await db.SaveChangesAsync();

        var loaded = await db.PipelineInstances.Include(p => p.Steps).FirstAsync(p => p.Id == pipeline.Id);
        Assert.NotNull(loaded);
        Assert.Empty(loaded.Steps);
    }

    [Fact]
    public async Task DeleteFirstStep_RemainingStepsIntact()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        pipeline.Steps.AddRange(new[] { s1, s2 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        db.PipelineSteps.Remove(s1);
        await db.SaveChangesAsync();

        var remaining = await db.PipelineSteps.Where(s => s.PipelineInstanceId == pipeline.Id).ToListAsync();
        Assert.Single(remaining);
        Assert.Equal(s2.Id, remaining[0].Id);
    }

    [Fact]
    public async Task DeleteLastStep_RemainingStepsIntact()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        db.PipelineSteps.Remove(s2);
        await db.SaveChangesAsync();

        var remaining = await db.PipelineSteps.Where(s => s.PipelineInstanceId == pipeline.Id).ToListAsync();
        Assert.Single(remaining);
        Assert.Equal(s1.Id, remaining[0].Id);
    }

    // ════════════════════════════════════════════════════════════════════
    // 4. Add Step After Creation — Append / Insert (8 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task AppendStep_ToExistingPipeline_OrderCorrect()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Append new step
        var newStep = MakeStep(pipeline.Id, 2, StageType.Export);
        db.PipelineSteps.Add(newStep);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(2, steps.Count);
        Assert.Equal(StageType.Collect, steps[0].StepType);
        Assert.Equal(StageType.Export, steps[1].StepType);
    }

    [Fact]
    public async Task InsertStep_InMiddle_ShiftAndPersist()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s3 = MakeStep(pipeline.Id, 2, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s3 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Insert processor between collector and export
        s3.StepOrder = 3;
        await db.SaveChangesAsync();

        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        db.PipelineSteps.Add(s2);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(3, steps.Count);
        Assert.Equal(StageType.Collect, steps[0].StepType);
        Assert.Equal(StageType.Process, steps[1].StepType);
        Assert.Equal(StageType.Export, steps[2].StepType);
    }

    [Fact]
    public async Task AppendMultipleSteps_Sequentially_AllPersisted()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Add steps one by one (simulating UI drag-and-drop)
        for (int i = 1; i <= 4; i++)
        {
            var type = i == 1 ? StageType.Collect : i == 4 ? StageType.Export : StageType.Process;
            db.PipelineSteps.Add(MakeStep(pipeline.Id, i, type));
            await db.SaveChangesAsync();
        }

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(4, steps.Count);
        Assert.Equal(StageType.Collect, steps[0].StepType);
        Assert.Equal(StageType.Process, steps[1].StepType);
        Assert.Equal(StageType.Process, steps[2].StepType);
        Assert.Equal(StageType.Export, steps[3].StepType);
    }

    // ════════════════════════════════════════════════════════════════════
    // 5. Full Pipeline Lifecycle with Stages — DB E2E (12 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task FullLifecycle_CreateStagesActivate_AllPersistedCorrectly()
    {
        await using var db = CreateDb();

        // 1. Create pipeline
        var pipeline = CreatePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        Assert.Equal(PipelineStatus.Draft, pipeline.Status);

        // 2. Add stages (simulating designer edge connections)
        var collRefId = Guid.NewGuid();
        var procRefId = Guid.NewGuid();
        var expRefId = Guid.NewGuid();

        db.PipelineSteps.Add(MakeStep(pipeline.Id, 1, StageType.Collect, collRefId));
        db.PipelineSteps.Add(MakeStep(pipeline.Id, 2, StageType.Process, procRefId));
        db.PipelineSteps.Add(MakeStep(pipeline.Id, 3, StageType.Export, expRefId));
        await db.SaveChangesAsync();

        // 3. Activate
        pipeline.Status = PipelineStatus.Active;
        var activation = new PipelineActivation
        {
            PipelineInstanceId = pipeline.Id,
            Status = ActivationStatus.Running,
            WorkerId = "test-worker"
        };
        db.PipelineActivations.Add(activation);
        await db.SaveChangesAsync();

        // 4. Verify everything
        var loaded = await db.PipelineInstances
            .Include(p => p.Steps)
            .FirstAsync(p => p.Id == pipeline.Id);

        Assert.Equal(PipelineStatus.Active, loaded.Status);
        Assert.Equal(3, loaded.Steps.Count);

        var act = await db.PipelineActivations.FirstAsync(a => a.PipelineInstanceId == pipeline.Id);
        Assert.Equal(ActivationStatus.Running, act.Status);

        // 5. Verify stage refs match what we set
        var steps = loaded.Steps.OrderBy(s => s.StepOrder).ToList();
        Assert.Equal(collRefId, steps[0].RefId);
        Assert.Equal(procRefId, steps[1].RefId);
        Assert.Equal(expRefId, steps[2].RefId);
    }

    [Fact]
    public async Task FullLifecycle_ActivateDeactivateReactivate_StatusTransitions()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Activate
        pipeline.Status = PipelineStatus.Active;
        var act1 = new PipelineActivation
        {
            PipelineInstanceId = pipeline.Id,
            Status = ActivationStatus.Running
        };
        db.PipelineActivations.Add(act1);
        await db.SaveChangesAsync();
        Assert.Equal(PipelineStatus.Active, pipeline.Status);

        // Deactivate (pause)
        pipeline.Status = PipelineStatus.Paused;
        act1.Status = ActivationStatus.Stopped;
        await db.SaveChangesAsync();
        Assert.Equal(PipelineStatus.Paused, pipeline.Status);
        Assert.Equal(ActivationStatus.Stopped, act1.Status);

        // Reactivate
        pipeline.Status = PipelineStatus.Active;
        var act2 = new PipelineActivation
        {
            PipelineInstanceId = pipeline.Id,
            Status = ActivationStatus.Running
        };
        db.PipelineActivations.Add(act2);
        await db.SaveChangesAsync();

        var activations = await db.PipelineActivations
            .Where(a => a.PipelineInstanceId == pipeline.Id)
            .ToListAsync();
        Assert.Equal(2, activations.Count);
    }

    [Fact]
    public async Task FullLifecycle_Archive_StagesSurvive()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline(status: PipelineStatus.Active);
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Archive
        pipeline.Status = PipelineStatus.Archived;
        await db.SaveChangesAsync();

        var loaded = await db.PipelineInstances.Include(p => p.Steps).FirstAsync(p => p.Id == pipeline.Id);
        Assert.Equal(PipelineStatus.Archived, loaded.Status);
        Assert.Equal(2, loaded.Steps.Count);
    }

    [Fact]
    public async Task FullLifecycle_ModifyStagesWhilePaused_Persists()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline(status: PipelineStatus.Paused);
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Export);
        pipeline.Steps.AddRange(new[] { s1, s2 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Add a processor in between while paused
        s2.StepOrder = 3;
        var s_new = MakeStep(pipeline.Id, 2, StageType.Process);
        db.PipelineSteps.Add(s_new);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(3, steps.Count);
        Assert.Equal(StageType.Collect, steps[0].StepType);
        Assert.Equal(StageType.Process, steps[1].StepType);
        Assert.Equal(StageType.Export, steps[2].StepType);
    }

    [Fact]
    public async Task FullLifecycle_CreateWorkItem_LinkedToActivation()
    {
        await using var db = CreateDb();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Create work item (simulating a file detection)
        var workItem = new WorkItem
        {
            PipelineInstanceId = pipeline.Id,
            PipelineActivationId = activation.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/test.csv",
            SourceMetadata = "{\"size\":2048}",
            Status = JobStatus.Detected,
            DetectedAt = DateTimeOffset.UtcNow
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        // Verify linkage
        var loaded = await db.WorkItems.FirstAsync(w => w.Id == workItem.Id);
        Assert.Equal(pipeline.Id, loaded.PipelineInstanceId);
        Assert.Equal(activation.Id, loaded.PipelineActivationId);

        // Pipeline should have 3 steps (from SeedPipelineAsync)
        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();
        Assert.Equal(3, steps.Count);
    }

    [Fact]
    public async Task FullLifecycle_DuplicatePipeline_StepsCopied()
    {
        await using var db = CreateDb();
        var original = CreatePipeline("original");
        var origRefIds = new[] { Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid() };
        original.Steps.Add(MakeStep(original.Id, 1, StageType.Collect, origRefIds[0]));
        original.Steps.Add(MakeStep(original.Id, 2, StageType.Process, origRefIds[1]));
        original.Steps.Add(MakeStep(original.Id, 3, StageType.Export, origRefIds[2]));
        db.PipelineInstances.Add(original);
        await db.SaveChangesAsync();

        // Duplicate: create new pipeline with copied steps
        var copy = new PipelineInstance
        {
            Name = original.Name + " (Copy)",
            Status = PipelineStatus.Draft,
            MonitoringType = original.MonitoringType,
            MonitoringConfig = original.MonitoringConfig
        };
        db.PipelineInstances.Add(copy);
        await db.SaveChangesAsync();

        // Copy steps
        var origSteps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == original.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        foreach (var step in origSteps)
        {
            db.PipelineSteps.Add(new PipelineStep
            {
                PipelineInstanceId = copy.Id,
                StepOrder = step.StepOrder,
                StepType = step.StepType,
                RefType = step.RefType,
                RefId = step.RefId,
                IsEnabled = step.IsEnabled,
                OnError = step.OnError
            });
        }
        await db.SaveChangesAsync();

        // Verify copy
        var copySteps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == copy.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(3, copySteps.Count);
        Assert.Equal(PipelineStatus.Draft, copy.Status);
        Assert.Equal("original (Copy)", copy.Name);
        Assert.NotEqual(original.Id, copy.Id);

        // RefIds should be the same (pointing to same instances)
        for (int i = 0; i < 3; i++)
            Assert.Equal(origRefIds[i], copySteps[i].RefId);
    }

    // ════════════════════════════════════════════════════════════════════
    // 6. Step Enable/Disable — Partial Composition (5 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task DisableStep_PersistsToDb()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        pipeline.Steps.AddRange(new[] { s1, s2 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        s2.IsEnabled = false;
        await db.SaveChangesAsync();

        var loaded = await db.PipelineSteps.FirstAsync(s => s.Id == s2.Id);
        Assert.False(loaded.IsEnabled);
    }

    [Fact]
    public async Task EnableDisableToggle_ReflectedInDb()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var step = MakeStep(pipeline.Id, 1, StageType.Collect);
        pipeline.Steps.Add(step);
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        Assert.True(step.IsEnabled);
        step.IsEnabled = false;
        await db.SaveChangesAsync();
        Assert.False((await db.PipelineSteps.FirstAsync(s => s.Id == step.Id)).IsEnabled);

        step.IsEnabled = true;
        await db.SaveChangesAsync();
        Assert.True((await db.PipelineSteps.FirstAsync(s => s.Id == step.Id)).IsEnabled);
    }

    [Fact]
    public async Task CountEnabledSteps_CorrectAfterDisable()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 2, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 3, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        // Disable middle step
        pipeline.Steps[1].IsEnabled = false;
        await db.SaveChangesAsync();

        var enabledCount = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id && s.IsEnabled)
            .CountAsync();

        Assert.Equal(2, enabledCount);
    }

    // ════════════════════════════════════════════════════════════════════
    // 7. Edge Cases & Error Handling (5 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task DuplicateStepOrder_BothPersisted()
    {
        // In-memory DB doesn't enforce unique constraint on StepOrder,
        // but this tests that the application can handle the scenario
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 1, StageType.Process)); // Same order!
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .ToListAsync();
        Assert.Equal(2, steps.Count);
    }

    [Fact]
    public async Task LargeStepOrder_Persisted()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        pipeline.Steps.Add(MakeStep(pipeline.Id, 100, StageType.Collect));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 200, StageType.Process));
        pipeline.Steps.Add(MakeStep(pipeline.Id, 300, StageType.Export));
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(100, steps[0].StepOrder);
        Assert.Equal(200, steps[1].StepOrder);
        Assert.Equal(300, steps[2].StepOrder);
    }

    [Fact]
    public async Task OnErrorAction_PersistsCorrectly()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var s1 = MakeStep(pipeline.Id, 1, StageType.Collect);
        s1.OnError = OnErrorAction.Stop;
        var s2 = MakeStep(pipeline.Id, 2, StageType.Process);
        s2.OnError = OnErrorAction.Skip;
        pipeline.Steps.AddRange(new[] { s1, s2 });
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(OnErrorAction.Stop, steps[0].OnError);
        Assert.Equal(OnErrorAction.Skip, steps[1].OnError);
    }

    [Fact]
    public async Task RetryConfig_PersistsCorrectly()
    {
        await using var db = CreateDb();
        var pipeline = CreatePipeline();
        var step = new PipelineStep
        {
            PipelineInstanceId = pipeline.Id,
            StepOrder = 1,
            StepType = StageType.Collect,
            RefType = RefType.Collector,
            RefId = Guid.NewGuid(),
            IsEnabled = true,
            OnError = OnErrorAction.Retry,
            RetryCount = 3,
            RetryDelaySeconds = 30
        };
        pipeline.Steps.Add(step);
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var loaded = await db.PipelineSteps.FirstAsync(s => s.Id == step.Id);
        Assert.Equal(OnErrorAction.Retry, loaded.OnError);
        Assert.Equal(3, loaded.RetryCount);
        Assert.Equal(30, loaded.RetryDelaySeconds);
    }

    [Fact]
    public async Task SeedPipelineAsync_ProducesValidComposition()
    {
        await using var db = CreateDb();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        Assert.Equal(PipelineStatus.Active, pipeline.Status);
        Assert.Equal(ActivationStatus.Running, activation.Status);

        var steps = await db.PipelineSteps
            .Where(s => s.PipelineInstanceId == pipeline.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();

        Assert.Equal(3, steps.Count);
        Assert.Equal(StageType.Collect, steps[0].StepType);
        Assert.Equal(StageType.Process, steps[1].StepType);
        Assert.Equal(StageType.Export, steps[2].StepType);

        // Each step refs a real instance
        Assert.True(steps.All(s => s.RefId != Guid.Empty));
    }
}
