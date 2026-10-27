// 面板 API 契约入口：仅重导出类型，外部导入路径保持不变。
// 字段变更请修改 types/ 中对应的业务域文件；子模块直接导入类型来源。

export type { Result, SeriesPoint, SeriesPayload } from './types/common';
export type {
  DeployStep,
  OneBotConnection,
  DeployStatus,
  FieldKind,
  FieldDescriptor,
  ConfigChangeItem,
  ConfigChanges,
  ConfigDocument,
  EnvItem,
  EnvPayload,
} from './types/config';
export type {
  ModelItem,
  ModelProbeResult,
  ModelsView,
  ModelsPayload,
  BillingScriptBinding,
  BillingScriptStatus,
  BillingPayload,
  BillingPreviewResult,
} from './types/models';
export type {
  PluginStatus,
  Plugin,
  PluginCommandRename,
  PluginConflictSide,
  PluginConflict,
  ExtensionEntry,
  ProxyInfo,
  PluginListPayload,
} from './types/plugins';
export type {
  SystemInfo,
  Overview,
  BotSummary,
  LogItem,
  LogPayload,
  ServiceItem,
  TaskItem,
  TasksPayload,
  ScheduledTaskItem,
  ScheduledTasksPayload,
  ScheduledTaskActionBody,
} from './types/runtime';
export type {
  UsageRecordItem,
  UsageRecordsPayload,
  UsageTotals,
  UsageRow,
  UsagePayload,
  RankItem,
  RankPayload,
  ActiveUser,
} from './types/usage';
export type {
  PromptPartReport,
  AgentPromptReport,
  PromptAnalysisPayload,
  PromptKeyView,
  PromptSectionView,
  PromptsPayload,
  PromptPreviewPayload,
  ChatFlowItem,
  ChatFlowsPayload,
  ChatFlowMessage,
  ChatFlowDetailPayload,
  ChatFlowPromptMeta,
  ChatFlowPromptsPayload,
  ChatFlowPromptEntry,
  ChatFlowPromptPayload,
  ChatFlowLatestPrompt,
} from './types/chat';
export type {
  ArchiveTable,
  ArchivesPayload,
  ArchiveItemSummary,
  ArchiveItemsPayload,
  ArchiveItemDetail,
  ArchiveItemQuery,
  ArchiveSummarizeBatchItem,
  ArchiveSummarizeTask,
  ArchiveSnapshot,
  ArchiveSnapshotsPayload,
  ArchiveSnapshotDetail,
  ArchiveUpdateBody,
  ArchiveDeleteBody,
} from './types/archives';
