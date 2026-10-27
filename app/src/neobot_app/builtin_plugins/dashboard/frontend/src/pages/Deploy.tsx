import { useRef, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Save } from 'lucide-react';
import Button from '../components/ui/Button';
import PageHeader from '../components/ui/PageHeader';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import InlineAlert from '../components/ui/InlineAlert';
import { useAuthGate } from '../auth/AuthContext';
import { STEPS } from './deploy/deployModel';
import { useDeployEditor } from './deploy/useDeployEditor';
import DeployStepPanel from './deploy/DeployStepPanel';

export default function Deploy() {
  const { canManage } = useAuthGate();
  const readOnly = canManage === false;
  const [activeIndex, setActiveIndex] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectStep = (index: number, focus = false) => {
    setActiveIndex(index);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    if (focus) stepRefs.current[index]?.focus();
  };

  const editor = useDeployEditor(readOnly, () => selectStep(3));
  const {
    doc,
    loading,
    busy,
    loadError,
    disabled,
    dirty,
    dirtySteps,
    read,
    saveAll,
    restored,
    discardDraft,
  } = editor;
  const configuredCount = STEPS.filter(
    (step) => doc?.steps?.find((item) => item.key === step.key)?.done,
  ).length;
  const saveLabel = busy === 'config' || busy === 'key' ? '保存中…' : '保存并应用';

  return (
    <div className="page page--viewport deploy-page deploy-wizard-page">
      <PageHeader title="快捷部署" />
      {readOnly && (
        <InlineAlert tone="info" title="当前会话只读">
          可以查看部署状态和复制连接信息，修改配置需要管理权限。
        </InlineAlert>
      )}
      <div className="deploy-wizard">
        <div className="deploy-stepnav" role="tablist" aria-label="部署步骤">
          {STEPS.map((step, index) => {
            const done = doc?.steps?.find((item) => item.key === step.key)?.done;
            const stepDirty = dirtySteps[step.key];
            return (
              <button
                key={step.key}
                ref={(node) => {
                  stepRefs.current[index] = node;
                }}
                id={'deploy-tab-' + step.key}
                type="button"
                role="tab"
                aria-selected={index === activeIndex}
                aria-controls={'deploy-panel-' + step.key}
                tabIndex={index === activeIndex ? 0 : -1}
                className={
                  'deploy-step' +
                  (index === activeIndex ? ' is-current' : '') +
                  (done && !stepDirty ? ' is-complete' : '')
                }
                onClick={() => selectStep(index)}
                onKeyDown={(event) => {
                  let next = index;
                  if (event.key === 'ArrowRight') next = (index + 1) % STEPS.length;
                  else if (event.key === 'ArrowLeft') next = (index + STEPS.length - 1) % STEPS.length;
                  else if (event.key === 'Home') next = 0;
                  else if (event.key === 'End') next = STEPS.length - 1;
                  else return;
                  event.preventDefault();
                  selectStep(next, true);
                }}
              >
                <span className="deploy-step-number" aria-hidden="true">
                  {done && !stepDirty ? <Check size={14} /> : index + 1}
                </span>
                <span className="deploy-step-label">{step.label}</span>
                <span className="deploy-step-state">
                  {stepDirty ? '未保存' : done ? '已配置' : step.required ? '待配置' : '选填'}
                </span>
              </button>
            );
          })}
        </div>
        <div className="deploy-step-scroll" ref={scrollRef}>
          {loadError && (
            <InlineAlert
              tone="error"
              title="部署状态读取失败"
              actions={
                !dirty &&
                !busy && (
                  <Button size="sm" disabled={loading} onClick={() => void read('retry')}>
                    重新读取
                  </Button>
                )
              }
            >
              {loadError}
            </InlineAlert>
          )}
          {!doc ? (
            loading && <PanelSkeleton label="正在读取部署配置…" rows={4} />
          ) : (
            <DeployStepPanel activeIndex={activeIndex} editor={editor} />
          )}
        </div>
        <footer className="deploy-wizard-footer">
          <div className="deploy-save-state" aria-live="polite">
            <strong>
              {busy === 'config' || busy === 'key'
                ? '正在应用更改…'
                : dirty
                  ? '有未保存的更改'
                  : doc?.ready
                    ? '必填项已配置'
                    : `${configuredCount} / ${STEPS.length} 项已配置`}
            </strong>
            <span>
              {restored
                ? '已恢复上次未保存的输入，密钥不会保存到浏览器。'
                : dirty
                  ? '切换步骤会保留输入，保存时一并应用。'
                  : '可直接点击步骤查看或修改。'}
            </span>
          </div>
          <div className="deploy-footer-actions">
            {restored && (
              <Button disabled={disabled} onClick={() => void discardDraft()}>
                放弃草稿
              </Button>
            )}
            <Button disabled={activeIndex === 0} onClick={() => selectStep(activeIndex - 1)}>
              <ChevronLeft size={15} />
              上一步
            </Button>
            {activeIndex < STEPS.length - 1 && (
              <Button onClick={() => selectStep(activeIndex + 1)}>
                下一步
                <ChevronRight size={15} />
              </Button>
            )}
            <Button variant="primary" disabled={disabled || !dirty} onClick={() => void saveAll()}>
              <Save size={15} />
              {saveLabel}
            </Button>
          </div>
        </footer>
      </div>
    </div>
  );
}
