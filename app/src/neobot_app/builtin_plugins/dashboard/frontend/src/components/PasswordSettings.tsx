import { useId, useRef, useState, type FormEvent } from 'react';
import { KeyRound } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthGate } from '../auth/AuthContext';
import { clearToken } from '../api/client';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import Modal, { ModalActions } from './Modal';
import { infoBar } from '../notifications/infoBar';
import Button from './ui/Button';

export interface PasswordSettingsProps {
  /** 由页面的草稿保护确认是否允许进入改密流程。 */
  beforeOpen?: () => Promise<boolean>;
  /** 由设置页持有弹窗状态，切换设置面板时保留改密流程。 */
  onOpen: () => void;
}

export default function PasswordSettings({ beforeOpen, onOpen }: PasswordSettingsProps) {
  const { canManage } = useAuthGate();
  const [opening, setOpening] = useState(false);
  const openingRef = useRef(false);
  const open = async () => {
    if (canManage !== true || openingRef.current) return;
    openingRef.current = true;
    setOpening(true);
    try {
      if (!beforeOpen || (await beforeOpen())) onOpen();
    } catch {
      infoBar({ title: '未能打开密码设置', tone: 'err', message: '请稍后重试。' });
    } finally {
      openingRef.current = false;
      setOpening(false);
    }
  };
  return (
    <Button
      type="button"
      disabled={canManage !== true || opening}
      title={canManage === false ? '修改密码需要管理权限' : '修改密码'}
      aria-label={opening ? '请稍候…' : '修改密码'}
      onClick={() => void open()}
    >
      <KeyRound size={18} aria-hidden="true" />
      {opening ? '请稍候…' : '修改密码'}
    </Button>
  );
}

export interface ChangePasswordDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ChangePasswordDialog({ open, onClose }: ChangePasswordDialogProps) {
  // 关闭即卸载表单，密码只在本次弹窗的内存状态中保留。
  return open ? <ChangePasswordForm onClose={onClose} /> : null;
}

type FieldErrors = Partial<Record<'current' | 'next' | 'confirm', string>>;

function ChangePasswordForm({ onClose }: { onClose: () => void }) {
  const { canManage } = useAuthGate();
  const navigate = useNavigate();
  const id = useId();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const locked = canManage !== true;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busyRef.current || locked) return;
    const invalid: FieldErrors = {};
    if (!current) invalid.current = '请输入当前密码';
    const length = Array.from(next).length;
    if (length < 8 || length > 128) invalid.next = '新密码须为 8–128 个字符';
    else if (next !== next.trim()) invalid.next = '密码首尾不能包含空白字符';
    else if (!/[\p{L}\p{N}]/u.test(next)) invalid.next = '密码至少包含一个字母或数字';
    if (confirm !== next || !confirm) invalid.confirm = '两次输入的新密码不一致';
    setErrors(invalid);
    if (Object.keys(invalid).length) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const result = await api.changePassword({ current_password: current, new_password: next, confirm });
      if (!result.ok) {
        infoBar({
          title: result.status === 0 ? '未能确认改密结果' : '密码未修改',
          tone: 'err',
          message: result.status === 0 ? '连接失败，请稍后重试。' : result.error || '请稍后重试。',
        });
        return;
      }
      if (result.data?.reauthenticate !== true) {
        infoBar({ title: '未能确认改密结果', tone: 'warn', message: '请重新登录以确认当前密码。' });
        return;
      }
      clearToken();
      clearQueries();
      onClose();
      navigate('/login?reason=password-changed', { replace: true });
    } catch {
      infoBar({ title: '未能确认改密结果', tone: 'err', message: '连接失败，请稍后重试。' });
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const close = () => {
    if (!busyRef.current) onClose();
  };

  return (
    <Modal
      open
      title="修改面板密码"
      onClose={close}
      closeDisabled={busy}
      className="password-settings-dialog"
      footer={
        <ModalActions>
          <Button onClick={close} disabled={busy}>
            取消
          </Button>
          <Button type="submit" form={`${id}-form`} variant="primary" disabled={locked || busy}>
            {busy ? '修改中…' : '修改并重新登录'}
          </Button>
        </ModalActions>
      }
    >
      <form
        id={`${id}-form`}
        className="password-settings-form"
        noValidate
        onSubmit={(event) => void submit(event)}
      >
        <p className="password-settings-summary">修改后所有登录会话将失效，需要使用新密码重新登录。</p>
        <div className="password-settings-field">
          <label htmlFor={`${id}-current`}>当前密码</label>
          <input
            id={`${id}-current`}
            className="input"
            data-autofocus
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => {
              setCurrent(event.target.value);
              setErrors((previous) => ({ ...previous, current: undefined }));
            }}
            disabled={locked || busy}
            aria-invalid={!!errors.current}
            aria-describedby={errors.current ? `${id}-current-error` : undefined}
            required
          />
          {errors.current && (
            <p className="password-settings-error" id={`${id}-current-error`}>
              {errors.current}
            </p>
          )}
        </div>
        <div className="password-settings-field">
          <label htmlFor={`${id}-next`}>新密码</label>
          <input
            id={`${id}-next`}
            className="input"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => {
              setNext(event.target.value);
              setErrors((previous) => ({ ...previous, next: undefined }));
            }}
            disabled={locked || busy}
            aria-invalid={!!errors.next}
            aria-describedby={`${id}-hint${errors.next ? ` ${id}-next-error` : ''}`}
            required
          />
          <p className="password-settings-hint" id={`${id}-hint`}>
            8–128 个字符，至少包含一个字母或数字，首尾不能有空格。
          </p>
          {errors.next && (
            <p className="password-settings-error" id={`${id}-next-error`}>
              {errors.next}
            </p>
          )}
        </div>
        <div className="password-settings-field">
          <label htmlFor={`${id}-confirm`}>确认新密码</label>
          <input
            id={`${id}-confirm`}
            className="input"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => {
              setConfirm(event.target.value);
              setErrors((previous) => ({ ...previous, confirm: undefined }));
            }}
            disabled={locked || busy}
            aria-invalid={!!errors.confirm}
            aria-describedby={errors.confirm ? `${id}-confirm-error` : undefined}
            required
          />
          {errors.confirm && (
            <p className="password-settings-error" id={`${id}-confirm-error`}>
              {errors.confirm}
            </p>
          )}
        </div>
        {locked && <p className="password-settings-hint">修改密码需要管理权限。</p>}
      </form>
    </Modal>
  );
}
