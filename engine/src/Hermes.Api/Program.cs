using Hermes.Api.Endpoints;
using Hermes.Api.Options;
using Hermes.Api.Services;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.Configure<DatabaseOptions>(builder.Configuration.GetSection(DatabaseOptions.SectionName));
builder.Services.AddSingleton<IHermesReadStore, InMemoryHermesReadStore>();
builder.Services.AddSingleton<IDatabaseBootstrapScriptService, DatabaseBootstrapScriptService>();
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
});

var app = builder.Build();

app.MapHermesSystemEndpoints();
app.MapHermesReadEndpoints();
app.MapHermesMutationEndpoints();
app.MapHermesInstanceEndpoints();

app.Run();

public partial class Program
{
}
