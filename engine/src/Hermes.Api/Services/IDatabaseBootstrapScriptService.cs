using Hermes.Api.Contracts;

namespace Hermes.Api.Services;

public interface IDatabaseBootstrapScriptService
{
    DatabaseInfoDto GetDatabaseInfo();

    BootstrapScriptDto GetBootstrapScript(string provider, string schema);
}
