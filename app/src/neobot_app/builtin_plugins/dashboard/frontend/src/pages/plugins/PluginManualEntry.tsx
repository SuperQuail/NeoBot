import { useCallback, useEffect, useRef, useState } from 'react';
import { BookOpen } from 'lucide-react';
import PluginPonderScreen from './PluginPonderScreen';
import Button from '../../components/ui/Button';
import { PanelSkeleton } from '../../components/ui/PageSkeleton';
import { useQueryErrorNotice } from '../../hooks/useQueryErrorNotice';
import PluginPonderPlayer from './PluginPonderPlayer';
import { usePluginViews } from './usePluginViews';
import { usePluginSurface } from './usePluginSurface';
import type { FieldDescriptor } from '../../api/types';

interface Props {
  pluginId: string;
  onOpenChange?: (open: boolean) => void;
  configFields?: FieldDescriptor[];
}

function ManualEntry({ pluginId, onOpenChange, configFields }: Props) {
  const [open, setOpen] = useState(false);
  const [guideId, setGuideId] = useState('');
  const openRef = useRef(false);
  const openChange = useRef(onOpenChange);
  openChange.current = onOpenChange;
  const query = usePluginSurface(pluginId);
  const changeOpen = useCallback((next: boolean) => {
    setOpen(next);
    if (openRef.current === next) return;
    openRef.current = next;
    openChange.current?.(next);
  }, []);
  const contract = query.data?.contract;
  const guides = contract?.guides ?? [];
  const guide = guides.find((item) => item.id === guideId) ?? guides[0];
  const hasScenes = guides.some((item) => item.steps.some((step) => step.target.startsWith('view.')));
  const views = usePluginViews(pluginId, hasScenes, open);
  useQueryErrorNotice(query.error, query.updatedAt, '使用说明读取失败', open);
  useQueryErrorNotice(views.error, views.updatedAt, '说明画面读取失败', open && hasScenes);

  const unavailable = !!query.data && !guides.length && !query.error;
  useEffect(() => {
    if (unavailable && openRef.current) changeOpen(false);
  }, [unavailable, changeOpen]);
  useEffect(
    () => () => {
      if (!openRef.current) return;
      openRef.current = false;
      openChange.current?.(false);
    },
    [],
  );

  if (unavailable) return null;
  const loadingScene = hasScenes && views.loading && !views.data;
  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        disabled={query.loading && !query.data}
        onClick={() => changeOpen(true)}
      >
        <BookOpen size={15} />
        使用说明
      </Button>
      {open && guide && contract && query.data && !loadingScene ? (
        <PluginPonderPlayer
          pluginId={pluginId}
          surface={{ ...query.data, contract, configFields }}
          guide={guide}
          guides={guides}
          views={views.data ?? []}
          onGuideChange={setGuideId}
          onClose={() => changeOpen(false)}
        />
      ) : open ? (
        <PluginPonderScreen pluginId={pluginId} onClose={() => changeOpen(false)}>
          {query.loading || loadingScene ? (
            <PanelSkeleton label="正在读取使用说明…" rows={3} />
          ) : (
            <Button size="sm" onClick={() => void query.refetch()}>
              重试读取
            </Button>
          )}
        </PluginPonderScreen>
      ) : null}
    </>
  );
}

/** 切换插件即开始独立的说明书会话，不保留上一个插件的选择。 */
export default function PluginManualEntry(props: Props) {
  return <ManualEntry key={props.pluginId} {...props} />;
}
