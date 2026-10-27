// 主机、机器人、日志、宿主服务与任务状态。

/** 系统信息快照 /api/system */
export interface SystemInfo {
  hostname?: string;
  os?: string;
  python_version?: string;
  pid?: number;
  cpu_percent?: number;
  cpu_count?: number;
  mem_percent?: number;
  mem_used_mb?: number;
  mem_total_mb?: number;
  process_memory_mb?: number;
  process_threads?: number;
  disk_percent?: number;
  disk_used_gb?: number;
  disk_total_gb?: number;
  load_average?: number[];
}

/** 概览 /api/overview */
export interface Overview {
  online?: boolean;
  /** 是否处于待机状态（原 frozen 字段） */
  standby?: boolean;
  app_name?: string;
  app_version?: string;
  uptime_seconds?: number;
  today_messages?: number;
  total_messages?: number;
  plugins_loaded?: number;
  plugins_total?: number;
  bot_nickname?: string;
  bot_user_id?: string | number;
  /** 首页要提示的配置缺口（如未配置超级管理员账号）；后端只读运行中的配置生成 */
  notices?: Array<{ level?: string; text?: string; hint?: string }>;
}

/** 机器人 /api/bots 与 /api/bot/detail */
export interface BotSummary {
  user_id?: string | number;
  name?: string;
  nickname?: string;
  platform?: string;
  avatar_initial?: string;
  avatar_url?: string;
  status?: string;
  online?: boolean;
  latency_ms?: number;
  today_messages?: number;
  total_messages?: number;
  uptime_seconds?: number;
  app_name?: string;
  app_version?: string;
}

/** 日志 /api/logs */
export interface LogItem {
  id?: number;
  time?: string;
  datetime?: string;
  level?: string;
  module?: string;
  message?: string;
}

export interface LogPayload {
  items?: LogItem[];
  last_id?: number;
  total?: number;
}

/** 服务 / 任务 */
export interface ServiceItem {
  name: string;
  description?: string;
  available?: boolean;
}

export interface TaskItem {
  task_id?: string;
  id?: string;
  name?: string;
  description?: string;
  kind?: string;
  status?: string;
  pipeline_key?: string;
  next_run?: string;
  trigger_time?: string;
  cron?: string;
}

export interface TasksPayload {
  scheduled?: TaskItem[];
  background?: TaskItem[];
  scheduled_error?: string;
  background_error?: string;
}

/** 定时任务 /api/scheduled-tasks */
export interface ScheduledTaskItem {
  task_id: string;
  title: string;
  detail?: string;
  recurrence: string;
  state: string;
  enabled: boolean;
  start_at?: string;
  end_at?: string;
  /** datetime-local 输入框需要的本地时间串 */
  start_at_local?: string;
  end_at_local?: string;
  next_run?: string;
  bindings?: Array<{ kind: string; id: string }>;
  metadata?: Record<string, unknown>;
  one_shot_notification?: boolean;
  completed_windows?: number;
  created_at?: string;
  updated_at?: string;
  version?: number;
}

export interface ScheduledTasksPayload {
  ok?: boolean;
  available?: boolean;
  tasks?: ScheduledTaskItem[];
  editable?: boolean;
  error?: string | null;
}

/** 定时任务写操作 /api/scheduled-tasks/action（action 必填，其余按动作透传） */
export interface ScheduledTaskActionBody {
  action: 'create' | 'update' | 'set_state' | 'set_notification_policy' | 'delete';
  task_uuid?: string;
  title?: string;
  detail?: string;
  recurrence?: string;
  start_at?: string;
  end_at?: string;
  bindings?: Array<{ kind: string; id: string }>;
  metadata?: Record<string, unknown>;
  one_shot_notification?: boolean;
  state?: 'active' | 'disabled';
}
