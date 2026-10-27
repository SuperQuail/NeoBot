import type { DeployStatus } from '../../api/types';

export const STEPS = [
  {
    key: 'bot_identity',
    label: '身份',
    title: '机器人身份',
    required: true,
    description: '填写机器人使用的 QQ 账号，以及你希望大家如何称呼它。',
    helpTitle: '填写机器人账号',
    tips: ['QQ 号应与 NapCat 登录的机器人账号一致。', '昵称用于自我介绍；别名帮助机器人识别大家对它的称呼。'],
  },
  {
    key: 'persona',
    label: '人设',
    title: '设定说话方式',
    required: true,
    description: '写清身份、语气和回复边界，这段设定会用于日常对话。',
    helpTitle: '从三句话开始',
    tips: [
      '它是谁，在群里是什么角色。',
      '它怎么说话，回答多长，使用什么语气。',
      '它有哪些习惯，以及需要遵守的边界。',
    ],
  },
  {
    key: 'platform_key',
    label: '供应商',
    title: '连接模型供应商',
    required: true,
    description: '默认模型使用 DeepSeek，填写调用凭据后即可开始对话。',
    helpTitle: '密钥只写不读',
    tips: [
      '已保存的密钥不会回显。留空保留原值，填写新值会替换。',
      '其他模型与供应商可在「配置管理」中调整。',
    ],
  },
  {
    key: 'admin',
    label: '管理员',
    title: '通知与回复偏好',
    required: false,
    description: '设置系统通知接收人，以及机器人在群聊中的参与意愿。',
    helpTitle: '按需要调整',
    tips: [
      '管理员用于接收余额不足等系统通知，留空也可以正常运行。',
      '回复意愿会结合聊天场景变化，被提及时通常更积极。',
    ],
  },
  {
    key: 'onebot',
    label: '连接',
    title: '连接 NapCat',
    required: true,
    description: '将生效地址与 Access Token 填入 NapCat 的反向 WebSocket 连接。',
    helpTitle: '在 NapCat 中操作',
    tips: [
      '新建反向 WebSocket 客户端。',
      '根据部署位置，复制同机或局域网连接地址。',
      '填写 Access Token 并启用连接。',
    ],
  },
] as const;

export interface DeployDraft {
  account: string;
  nickName: string;
  aliases: string;
  persona: string;
  adminQq: string;
  chance: string;
}

export const EMPTY_DRAFT: DeployDraft = {
  account: '',
  nickName: '',
  aliases: '',
  persona: '',
  adminQq: '',
  chance: '0.3',
};

export function draftFromDocument(doc: DeployStatus): DeployDraft {
  const values = doc.values || {};
  return {
    account: values.bot_account || '',
    nickName: values.bot_nick_name || '',
    aliases: (values.alias_name || []).join('、'),
    persona: values.bot_data || '',
    adminQq: (values.admin_accounts || [])[0] || '',
    chance: String(values.group_chat_chance ?? 0.3),
  };
}

/** 仅把快捷部署中编辑过的字段合并到刚读取的服务端文档。 */
export function mergeDeployConfig(
  config: Record<string, unknown>,
  draft: DeployDraft,
  savedDraft: DeployDraft,
  parsedChance: number,
): Record<string, unknown> {
  const changed = (field: keyof DeployDraft) => draft[field] !== savedDraft[field];
  return {
    ...config,
    bot: {
      ...((config.bot || {}) as Record<string, unknown>),
      ...(changed('account') ? { account: draft.account.trim() } : {}),
      ...(changed('nickName') ? { nick_name: draft.nickName.trim() } : {}),
      ...(changed('aliases')
        ? {
            alias_name: draft.aliases
              .split(/[、,，\s]+/)
              .map((value) => value.trim())
              .filter(Boolean),
          }
        : {}),
      ...(changed('persona') ? { bot_data: draft.persona } : {}),
    },
    chat: {
      ...((config.chat || {}) as Record<string, unknown>),
      ...(changed('adminQq') ? { admin_accounts: draft.adminQq.trim() ? [draft.adminQq.trim()] : [] } : {}),
      ...(changed('chance') ? { group_chat_chance: parsedChance } : {}),
    },
  };
}
