// pages/ChatFlows.tsx —— 聊天流：内存快速预览 + 纯内存的完整提示词历史
// （features/spec(3) 建立，spec(10) 改为纯内存 + 逐份 diff + 图片只留哈希）
//
// 两个数据来源，职责不同：
// 1) /api/chat-flows(+detail)：回复管线写入 ChatFlowRegistry 的**内存快照**（有界、只保留
//    最近 80 条消息、单条 4000 字符）—— 保留原有「快速预览」能力；
// 2) /api/chat-flows/prompts(+prompt)：每次模型调用的完整提示词，**只存在内存里**
//    （全局保留最近 N 份，重启即清空），逐份只存相对上一份的 diff，图片只留 sha256
//    哈希不留 base64。列表只给元数据，正文按需读取、**完整渲染不做任何截断**。
//    这一份**按 5s 轮询**并默认跟随最新：一轮对话（回复发出 / 被取消）跑完后，
//    面板上立刻是那一轮最后的一份提示词，而不是上一次调用留下的旧那份。
//
// 名称：列表与详情标题都用后端解析好的 display_name（群名 / 昵称），
// pipeline_key 作为副标题常驻，便于在日志 / 配置里定位。
import { useEffect, useMemo, useRef, useState } from 'react';
import { Info } from 'lucide-react';
import Icon from '../components/Icon';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import { PanelSkeleton } from '../components/ui/PageSkeleton';
import InlineAlert from '../components/ui/InlineAlert';
import { notify } from '../notifications/infoBar';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import type { ChatFlowLatestPrompt } from '../api/types';
import PageHeader from '../components/ui/PageHeader';
import { useAuthGate } from '../auth/AuthContext';
import { samePromptPayload } from './chat-flows/chatFlowUtils';
import { ChatFlowList } from './chat-flows/ChatFlowList';
import { QuickPreview } from './chat-flows/QuickPreview';
import { PromptHistory, PromptReader } from './chat-flows/PromptHistory';
import {
  ChatFlowHelpDialog,
  ChatFlowContextDialog,
  ClearPromptHistoryDialog,
  type ChatContextPanel,
} from './chat-flows/ChatFlowDialogs';

export default function ChatFlows() {
  const { canManage } = useAuthGate();
  const readOnly = canManage === false;
  const list = useQuery(QK.chatFlows, () => api.chatFlows(), { interval: POLL.chatFlows });
  const flows = useMemo(() => list.data?.items || [], [list.data]);
  const [selected, setSelected] = useState('');
  const [showDetail, setShowDetail] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [tab, setTab] = useState<'full' | 'quick'>('quick');
  const [helpOpen, setHelpOpen] = useState(false);
  const [contextPanel, setContextPanel] = useState<ChatContextPanel>(null);
  const flowListRef = useRef<HTMLUListElement>(null);
  const flowDetailRef = useRef<HTMLElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const promptEntryRef = useRef<HTMLDivElement>(null);
  const previousDetailMode = useRef(showDetail);
  const previousHistoryMode = useRef(showHistory);

  useEffect(() => {
    if (previousDetailMode.current === showDetail) return;
    previousDetailMode.current = showDetail;
    if (!window.matchMedia?.('(max-width: 760px)').matches) return;
    (showDetail ? flowDetailRef.current : flowListRef.current)?.focus({ preventScroll: true });
  }, [showDetail]);

  useEffect(() => {
    if (previousHistoryMode.current === showHistory) return;
    previousHistoryMode.current = showHistory;
    if (tab !== 'full' || !window.matchMedia?.('(max-width: 1100px)').matches) return;
    (showHistory ? historyRef.current : promptEntryRef.current)?.focus({ preventScroll: true });
  }, [showHistory, tab]);
  /** 历史列表是否只看当前聊天流 */
  const [onlyCurrent, setOnlyCurrent] = useState(true);
  /** 历史里被手动切换到的 seq；null = 跟随最新一份 */
  const [pickedSeq, setPickedSeq] = useState<number | null>(null);
  const [clearOpen, setClearOpen] = useState(false);
  const [clearChecked, setClearChecked] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (selected || flows.length === 0) return;
    setSelected(flows[0].pipeline_key);
  }, [flows, selected]);

  // 选中的聊天流被淘汰后回落到第一条
  useEffect(() => {
    if (selected && flows.length > 0 && !flows.some((flow) => flow.pipeline_key === selected)) {
      setSelected(flows[0].pipeline_key);
    }
  }, [flows, selected]);

  const detail = useQuery(
    QK.chatFlowDetail(selected || 'none'),
    () => (selected ? api.chatFlowDetail(selected) : Promise.resolve(null)),
    { interval: POLL.chatFlows, deps: [selected] },
  );
  const snapshot = detail.data || null;

  // 完整提示词历史：「元数据列表 + 最新一份全文」，**每 5s 轮询一次**
  // —— 一轮对话（回复发出 / 被取消）跑完后，面板上立刻就是那一轮最后一份提示词，
  //    而不是上一次调用留下的旧那份；命中内存快照，不做逐份重建，轮询成本可忽略。
  const promptKey = onlyCurrent ? selected : '';
  const prompts = useQuery(QK.chatFlowPrompts(promptKey), () => api.chatFlowPromptLatest(promptKey), {
    interval: POLL.chatFlowPrompts,
    deps: [promptKey],
  });
  const promptCacheRef = useRef<ChatFlowLatestPrompt | null>(null);
  const promptData = useMemo(() => {
    const incoming = prompts.data;
    const previous = promptCacheRef.current;
    if (incoming && previous && samePromptPayload(previous, incoming)) return previous;
    promptCacheRef.current = incoming;
    return incoming;
  }, [prompts.data]);
  const promptItems = useMemo(() => promptData?.items || [], [promptData]);
  const limit = promptData?.limit || 0;
  const storageBytes = promptData?.storage_bytes || 0;
  const imageRefs = promptData?.image_refs || 0;
  const latestSeq = promptData?.seq ?? null;
  // 手动选中的份仍存在就用它，否则回落到最新一份（切换聊天流后自然重置）
  const activeSeq =
    pickedSeq !== null && promptItems.some((item) => item.seq === pickedSeq) ? pickedSeq : latestSeq;
  const showingLatest = activeSeq !== null && activeSeq === latestSeq;

  // **切换历史时才请求全量接口**；最新那一份已由 chatFlowPromptLatest 读回，不再重复请求
  const entry = useQuery(
    QK.chatFlowPrompt(activeSeq ?? 0),
    () => (activeSeq === null || showingLatest ? Promise.resolve(null) : api.chatFlowPrompt(activeSeq)),
    { deps: [activeSeq, showingLatest] },
  );
  const activeEntry = showingLatest ? (promptData?.entry ?? null) : (entry.data?.entry ?? null);
  const entryLoading = showingLatest ? prompts.loading : entry.loading;

  async function clearHistory() {
    if (readOnly) return;
    setClearing(true);
    const result = await api.chatFlowPromptClear();
    setClearing(false);
    if (!result.ok) {
      notify(result.error || '清空提示词历史失败', 'err');
      return;
    }
    notify(result.data?.message || '已清空完整提示词历史', 'ok');
    setClearOpen(false);
    setClearChecked(false);
    setPickedSeq(null);
    await prompts.refetch();
  }

  return (
    <div className="page page--viewport chat-flows-page">
      <PageHeader
        title="聊天流"
        actions={
          <>
            <Button
              variant="ghost"
              className="chat-help-button"
              aria-label="隐私与记录说明"
              onClick={() => setHelpOpen(true)}
            >
              <Icon name="eye" size={15} />
              <span className="chat-help-long">隐私与记录</span>
              <span className="chat-help-short">隐私</span>
            </Button>
            <Button
              variant="danger"
              type="button"
              className="chat-clear-history"
              aria-label="清空提示词历史"
              title="清空提示词历史"
              disabled={readOnly || clearing}
              onClick={() => {
                setClearChecked(false);
                setClearOpen(true);
              }}
            >
              <Icon name="trash" />
              <span className="chat-clear-label">清空历史</span>
            </Button>
          </>
        }
      />
      {readOnly && (
        <InlineAlert tone="info" title="当前会话只读">
          可以查看聊天流与提示词历史，清空历史需要管理权限。
        </InlineAlert>
      )}
      {list.loading && !list.data && <EmptyState compact>正在读取聊天流…</EmptyState>}
      {list.error && (
        <InlineAlert
          tone="error"
          title="读取聊天流失败"
          actions={<Button onClick={() => void list.refetch()}>重新读取</Button>}
        />
      )}

      {list.data && list.data.ok === false && (
        <EmptyState icon="bot" title="聊天流不可用">
          <p>{list.data.error || '后端未注入 chat_flow_registry。'}</p>
        </EmptyState>
      )}

      {(!list.data || list.data.ok !== false) && flows.length === 0 && !list.loading && !list.error && (
        <EmptyState compact>还没有聊天流记录。Bot 收到消息并构建提示词后这里就会出现。</EmptyState>
      )}

      {flows.length > 0 && (
        <div className={'viewer-layout chat-viewer-layout' + (showDetail ? ' show-detail' : '')}>
          <ChatFlowList
            flows={flows}
            selected={selected}
            flowListRef={flowListRef}
            onSelect={(key) => {
              setSelected(key);
              setShowDetail(true);
              setShowHistory(false);
            }}
          />

          <section
            ref={flowDetailRef}
            className="card viewer-detail chat-flow-detail"
            aria-label="聊天流详情"
            tabIndex={-1}
          >
            {!snapshot && (
              <Button
                className="chat-empty-back"
                variant="ghost"
                size="sm"
                onClick={() => setShowDetail(false)}
              >
                <Icon name="back" size={15} />
                返回会话列表
              </Button>
            )}
            {!snapshot ? (
              detail.loading ? (
                <PanelSkeleton label="正在读取聊天流详情" kind="text" rows={5} />
              ) : (
                <EmptyState compact>选择左侧的聊天流查看详情</EmptyState>
              )
            ) : (
              <>
                <header className="chat-detail-toolbar">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="chat-inline-back"
                    aria-label="返回会话列表"
                    onClick={() => setShowDetail(false)}
                  >
                    <Icon name="back" size={15} />
                  </Button>
                  <div className="chat-detail-identity">
                    <h3 title={snapshot.display_name || snapshot.pipeline_key}>
                      {snapshot.display_name || snapshot.pipeline_key}
                    </h3>
                    <div>
                      <code title={snapshot.pipeline_key}>{snapshot.pipeline_key}</code>
                      <span title={snapshot.model}>{snapshot.model || '未知模型'}</span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="chat-session-info"
                    aria-label="查看会话信息"
                    onClick={() => setContextPanel('info')}
                  >
                    <Info size={15} aria-hidden="true" />
                  </Button>
                  <div className="config-tabs chat-flow-tabs">
                    <div role="tablist" aria-label="聊天流视图">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={tab === 'full'}
                        className={tab === 'full' ? 'active' : ''}
                        onClick={() => setTab('full')}
                      >
                        完整提示词
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={tab === 'quick'}
                        className={tab === 'quick' ? 'active' : ''}
                        onClick={() => setTab('quick')}
                      >
                        快速预览
                      </button>
                    </div>
                    {tab === 'full' && (
                      <Button
                        size="sm"
                        className="viewer-history-toggle"
                        aria-expanded={showHistory}
                        aria-label={showHistory ? '返回正文' : '历史记录'}
                        onClick={() => setShowHistory((value) => !value)}
                      >
                        <Icon name={showHistory ? 'back' : 'clock'} size={15} />
                        <span className="viewer-history-label">{showHistory ? '返回正文' : '历史记录'}</span>
                      </Button>
                    )}
                  </div>
                </header>

                {tab === 'quick' ? (
                  <QuickPreview snapshot={snapshot} onOpenContext={setContextPanel} />
                ) : (
                  <div
                    className={
                      'chat-prompt-layout viewer-prompt-layout' + (showHistory ? ' show-history' : '')
                    }
                  >
                    <PromptHistory
                      historyRef={historyRef}
                      promptItems={promptItems}
                      limit={limit}
                      onlyCurrent={onlyCurrent}
                      showingLatest={showingLatest}
                      latestSeq={latestSeq}
                      loading={prompts.loading}
                      activeSeq={activeSeq}
                      onOnlyCurrentChange={setOnlyCurrent}
                      onFollowLatest={() => setPickedSeq(null)}
                      onPick={(seq) => {
                        setPickedSeq(seq);
                        setShowHistory(false);
                      }}
                    />

                    <PromptReader
                      promptEntryRef={promptEntryRef}
                      promptData={promptData}
                      loading={prompts.loading}
                      activeSeq={activeSeq}
                      entryLoading={entryLoading}
                      activeEntry={activeEntry}
                      onRetry={() => void (showingLatest ? prompts.refetch() : entry.refetch())}
                    />
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}

      <ChatFlowHelpDialog
        helpOpen={helpOpen}
        limit={limit}
        promptCount={promptItems.length}
        storageBytes={storageBytes}
        imageRefs={imageRefs}
        onClose={() => setHelpOpen(false)}
      />
      <ChatFlowContextDialog
        contextPanel={contextPanel}
        snapshot={snapshot}
        onClose={() => setContextPanel(null)}
      />
      <ClearPromptHistoryDialog
        clearOpen={clearOpen}
        clearing={clearing}
        clearChecked={clearChecked}
        readOnly={readOnly}
        promptCount={promptItems.length}
        limit={limit}
        onClose={() => setClearOpen(false)}
        onCheckedChange={setClearChecked}
        onConfirm={() => void clearHistory()}
      />
    </div>
  );
}
