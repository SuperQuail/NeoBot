import type { DeployDraft } from './deployModel';

// 兼容此前快捷部署草稿；只存非敏感配置，API Key 不得落入浏览器存储。
export const DEPLOY_DRAFT_KEY = 'neobot.deploy.draft.v1';

export function loadDeployDraft(): DeployDraft | null {
  try {
    const raw = sessionStorage.getItem(DEPLOY_DRAFT_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const value = parsed as Partial<DeployDraft>;
    return {
      account: String(value.account ?? ''),
      nickName: String(value.nickName ?? ''),
      aliases: String(value.aliases ?? ''),
      persona: String(value.persona ?? ''),
      adminQq: String(value.adminQq ?? ''),
      chance: String(value.chance ?? '0.3'),
    };
  } catch {
    return null;
  }
}

export function saveDeployDraft(draft: DeployDraft): void {
  try {
    sessionStorage.setItem(DEPLOY_DRAFT_KEY, JSON.stringify(draft));
  } catch {
    // 隐私模式或容量不足不阻断当前编辑会话。
  }
}

export function clearDeployDraft(): void {
  try {
    sessionStorage.removeItem(DEPLOY_DRAFT_KEY);
  } catch {
    // 存储不可用时仍可继续保存服务端配置。
  }
}
