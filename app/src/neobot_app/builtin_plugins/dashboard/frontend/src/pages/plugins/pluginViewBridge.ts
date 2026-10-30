import type {
  ConfigDocument,
  FieldDescriptor,
  PluginAction,
  PluginActionPayload,
  PluginGuideDemo,
  PluginPermission,
  PluginSurfaceContract,
  PluginSurfacePayload,
  Result,
} from '../../api/types';

export type RunPluginAction = (
  action: PluginAction,
  values: unknown,
  quiet?: boolean,
) => Promise<PluginActionPayload | null>;

export interface PluginViewContext {
  pluginId: string;
  viewId: string;
  mode: 'live' | 'demo';
  permissions: PluginPermission[];
  available: boolean;
  suspended?: boolean;
  theme: Record<string, string>;
  reducedMotion: boolean;
  language: string;
  layout?: 'inline' | 'stage';
  colorScheme?: string;
}

export interface PluginAnchorRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface PluginViewConfigAccess {
  get: () => Promise<Result<ConfigDocument>>;
  save: (values: Record<string, unknown>, revision: string) => Promise<Result<ConfigDocument>>;
}

export type PluginViewSurface = PluginSurfacePayload & {
  contract: PluginSurfaceContract;
  configFields?: FieldDescriptor[];
};

type PluginViewConfiguration =
  { mode: 'live'; access: PluginViewConfigAccess } | { mode: 'demo'; values: Record<string, unknown> };

interface BridgeOptions {
  source: () => Window | null;
  post: (message: unknown) => void;
  contract: () => PluginSurfaceContract;
  context: () => PluginViewContext;
  demo: () => PluginGuideDemo | undefined;
  run: RunPluginAction;
  notify: (notice: { title: string; message?: string; tone: 'ok' | 'warn' | 'err' | 'info' }) => void;
  navigate: (target: string) => void;
  anchors: (rectangles: Record<string, PluginAnchorRect>) => void;
  resize?: (height: number) => void;
  reveal?: (rectangle: PluginAnchorRect) => void;
  ready?: () => void;
  configuration: () => PluginViewConfiguration;
  session: string;
}

const CHANNEL = 'neobot-plugin-view';
const plain = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const clone = (value: unknown) => (value === undefined ? null : JSON.parse(JSON.stringify(value)));

interface BridgeError {
  code: string;
  message: string;
  status?: number;
  fields?: ConfigDocument['errors'];
}

interface BridgeResponse {
  result: unknown;
  error?: BridgeError;
}

function failure(code: string, message: string): BridgeResponse {
  return { result: null, error: { code, message } };
}

function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function anchorRectangle(value: unknown): PluginAnchorRect | null {
  if (!plain(value)) return null;
  const { left, top, width, height } = value;
  if (!finiteNumber(left) || !finiteNumber(top) || !finiteNumber(width) || !finiteNumber(height)) return null;
  return { left, top, width, height };
}

function noticeTone(value: unknown): 'ok' | 'warn' | 'err' | 'info' {
  if (value === 'ok' || value === 'warn' || value === 'err') return value;
  return 'info';
}

export function createPluginViewBridge(options: BridgeOptions) {
  let active = true;
  const pending = new Set<string>();
  const envelope = { channel: CHANNEL, version: 1, session: options.session };
  const reply = (requestId: string, result: unknown, error?: BridgeError) => {
    if (active) options.post({ ...envelope, kind: 'response', requestId, result: clone(result), error });
  };
  const event = (name: string, payload: unknown) => {
    if (active) options.post({ ...envelope, kind: 'event', name, payload: clone(payload) });
  };

  async function executeAction(
    params: Record<string, unknown>,
    context: PluginViewContext,
    contract: PluginSurfaceContract,
  ): Promise<BridgeResponse> {
    const action = contract.actions.find((item) => item.id === params.id);
    if (!action) return failure('action_not_found', '插件没有声明此操作');
    if (context.mode === 'demo') {
      const examples = options.demo()?.actions ?? {};
      if (!Object.hasOwn(examples, action.id))
        return failure('demo_result_missing', '当前演示没有提供此操作的样例');
      return { result: examples[action.id] };
    }
    if (context.suspended) return failure('view_suspended', '页面正在演示，真实操作已暂停');
    if (!context.available || !context.permissions.includes(action.permission))
      return failure('permission_denied', '当前无执行权限或插件未运行');
    const values = Object.hasOwn(params, 'values') ? params.values : {};
    const response = await options.run(action, values, true);
    if (!response) return failure('action_busy', '另一项操作正在执行，请稍后重试');
    // 页面关闭后无法再自行通知，由仍存活的入口补发本次结果；旧插件的空结果继续静默。
    if (!active)
      options.notify({
        title: response.ok ? `${action.title}执行完成` : `${action.title}失败`,
        message: response.ok ? undefined : response.error || '操作执行失败',
        tone: response.ok ? 'ok' : 'err',
      });
    if (!response.ok) return failure(response.code || 'action_failed', response.error || '操作执行失败');
    return { result: response.result };
  }

  async function accessConfiguration(
    writing: boolean,
    params: Record<string, unknown>,
    context: PluginViewContext,
    contract: PluginSurfaceContract,
  ): Promise<BridgeResponse> {
    const configuration = options.configuration();
    if (configuration.mode === 'demo') {
      if (writing) return failure('demo_read_only', '说明书只展示样例配置，不能保存真实配置');
      return {
        result: { config: configuration.values, revision: '', form_supported: true, schema: [] },
      };
    }
    if (context.suspended) return failure('view_suspended', '页面正在演示，真实操作已暂停');
    if (!context.permissions.includes(writing ? 'manage' : 'read'))
      return failure('permission_denied', '当前无配置访问权限');
    if (contract.config === null) return failure('config_not_declared', '插件尚未声明配置模型');

    let response: Result<ConfigDocument>;
    if (writing) {
      const { values, revision } = params;
      if (!plain(values) || typeof revision !== 'string')
        return failure('invalid_config', '保存配置需要对象与读取时的 revision');
      response = await configuration.access.save(values, revision);
    } else {
      response = await configuration.access.get();
    }
    // 设置页收起或卸载后不能自行反馈保存结果，只补发本次写入的通知。
    if (writing && !active) {
      const saved = response.ok && !!response.data;
      const pending = saved && response.data?.applied === false;
      options.notify({
        title: !saved ? '插件配置保存失败' : pending ? '配置已保存，尚未生效' : '插件配置已保存',
        message: saved ? response.data?.message : response.error || '配置操作未完成',
        tone: !saved ? 'err' : pending ? 'warn' : 'ok',
      });
    }
    if (!response.ok || !response.data) {
      return {
        result: null,
        error: {
          code: response.status === 409 ? 'config_conflict' : 'config_failed',
          message: response.error || '配置操作未完成',
          status: response.status,
          fields: response.data?.errors,
        },
      };
    }
    const { config, revision, form_supported, schema, message, applied, changes } = response.data;
    return { result: { config, revision, form_supported, schema, message, applied, changes } };
  }

  function publishNotice(params: Record<string, unknown>): BridgeResponse {
    if (typeof params.title !== 'string' || !params.title.trim())
      return failure('invalid_notice', '通知标题不能为空');
    options.notify({
      title: params.title,
      message: typeof params.message === 'string' ? params.message : undefined,
      tone: noticeTone(params.tone),
    });
    return { result: null };
  }

  function navigate(params: Record<string, unknown>): BridgeResponse {
    if (
      typeof params.target !== 'string' ||
      !/^(config|action|resource|view)\.[a-z0-9_.-]+$/.test(params.target)
    )
      return failure('invalid_target', '导航目标无效');
    options.navigate(params.target);
    return { result: null };
  }

  function updateAnchors(
    params: Record<string, unknown>,
    context: PluginViewContext,
    contract: PluginSurfaceContract,
  ): BridgeResponse {
    const rectangles: Record<string, PluginAnchorRect> = {};
    const declared = contract.views?.find((item) => item.id === context.viewId)?.anchors ?? [];
    const submitted = plain(params.rectangles) ? params.rectangles : {};
    for (const id of declared) {
      const rectangle = anchorRectangle(submitted[id]);
      if (!rectangle) continue;
      rectangles[id] = rectangle;
    }
    options.anchors(rectangles);
    return { result: null };
  }

  function dispatch(
    method: unknown,
    params: Record<string, unknown>,
    context: PluginViewContext,
    contract: PluginSurfaceContract,
  ): BridgeResponse | Promise<BridgeResponse> {
    switch (method) {
      case 'ready':
        return { result: context };
      case 'action':
        return executeAction(params, context, contract);
      case 'getConfig':
        return accessConfiguration(false, params, context, contract);
      case 'saveConfig':
        return accessConfiguration(true, params, context, contract);
      case 'notify':
        return publishNotice(params);
      case 'navigate':
        return navigate(params);
      case 'anchors':
        return updateAnchors(params, context, contract);
      case 'reveal': {
        const rectangle = anchorRectangle(params.rectangle);
        if (
          !rectangle ||
          rectangle.left < 0 ||
          rectangle.top < 0 ||
          rectangle.width <= 0 ||
          rectangle.height <= 0
        )
          return failure('invalid_rectangle', '焦点范围必须为有效的可见区域');
        if (context.layout === 'inline' && context.mode === 'live' && !context.suspended)
          options.reveal?.(rectangle);
        return { result: null };
      }
      case 'resize':
        if (!finiteNumber(params.height) || params.height <= 0)
          return failure('invalid_height', '页面高度必须为正数');
        // 布局消息仍受窗口与会话校验约束，限制异常页面占用的高度。
        if (context.layout === 'inline') options.resize?.(Math.min(20000, Math.ceil(params.height)));
        return { result: null };
      default:
        return failure('method_not_found', '页面桥接不支持此请求');
    }
  }

  async function receive(incoming: MessageEvent) {
    const request = incoming.data;
    if (
      !active ||
      incoming.source !== options.source() ||
      !plain(request) ||
      request.channel !== CHANNEL ||
      request.version !== 1 ||
      request.kind !== 'request' ||
      typeof request.requestId !== 'string'
    )
      return;
    if (request.method !== 'ready' && request.session !== options.session) return;
    if (pending.has(request.requestId)) return;
    pending.add(request.requestId);
    try {
      const params = plain(request.params) ? request.params : {};
      const context = options.context();
      const contract = options.contract();
      const response = await dispatch(request.method, params, context, contract);
      reply(request.requestId, response.result, response.error);
      if (active && request.method === 'ready') options.ready?.();
    } catch {
      reply(request.requestId, null, { code: 'bridge_failed', message: '页面操作暂时无法完成' });
    } finally {
      pending.delete(request.requestId);
    }
  }

  return {
    receive,
    event,
    dispose: () => {
      active = false;
      pending.clear();
    },
  };
}
