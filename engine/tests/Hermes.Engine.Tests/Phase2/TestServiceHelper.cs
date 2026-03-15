using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Hermes.Engine.Infrastructure.Data;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Creates a proper DI container where IServiceScopeFactory resolves
/// the same in-memory DB instance. This is needed for services that
/// create their own scope (BackPressureManager, DeadLetterQueue, etc.)
/// </summary>
public static class TestServiceHelper
{
    public static (IServiceProvider Provider, HermesDbContext Db) CreateServices(string? dbName = null)
    {
        var name = dbName ?? Guid.NewGuid().ToString();
        var services = new ServiceCollection();

        services.AddDbContext<HermesDbContext>(options =>
            options.UseInMemoryDatabase(name));

        var provider = services.BuildServiceProvider();

        // Get a long-lived context for seeding/assertions
        var db = provider.GetRequiredService<HermesDbContext>();
        db.Database.EnsureCreated();

        return (provider, db);
    }
}
