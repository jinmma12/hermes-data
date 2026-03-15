namespace Hermes.Engine.Domain;

public enum DefinitionStatus { Draft, Active, Deprecated, Archived }
public enum ExecutionType { Plugin, Script, Http, Docker, NifiFlow, Internal }
public enum InstanceStatus { Draft, Active, Disabled, Archived }
public enum PipelineStatus { Draft, Active, Paused, Archived }
public enum MonitoringType { FileMonitor, ApiPoll, DbPoll, EventStream }
public enum StageType { Collect, Algorithm, Transfer }
public enum RefType { Collector, Algorithm, Transfer }
public enum OnErrorAction { Stop, Skip, Retry }
public enum ActivationStatus { Starting, Running, Stopping, Stopped, Error }
public enum SourceType { File, ApiResponse, DbChange, Event }
public enum JobStatus { Detected, Queued, Processing, Completed, Failed }
public enum TriggerType { Initial, Retry, Reprocess }
public enum ExecutionStatus { Running, Completed, Failed, Cancelled }
public enum StepExecutionStatus { Pending, Running, Completed, Failed, Skipped }
public enum ReprocessStatus { Pending, Approved, Executing, Done, Rejected }
public enum EventLevel { Debug, Info, Warn, Error }
public enum PluginStatus { Installed, Active, Disabled, Uninstalled }
public enum MessageType { Configure, Execute, Log, Output, Error, Status, Done }
public enum PluginType { Collector, Algorithm, Transfer }
public enum DeadLetterStatus { Quarantined, Retrying, Resolved, Discarded }
