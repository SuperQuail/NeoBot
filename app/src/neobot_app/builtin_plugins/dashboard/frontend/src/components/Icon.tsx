// Icon.tsx —— 统一图标入口
// 全部图标来自 lucide-react，通过 name 白名单暴露，调用方写 <Icon name="save" size={16} />。
// 约定：
//   - 需要「按名字查表」时用这里（例如由配置/数据驱动的场景）；
//   - 布局里位置固定的图标可以直接 import lucide 组件（如 Layout 的侧栏），性能更好；
//   - 不要新增手写内联 <svg>（图表类 LineChart / Sparkline 例外）。
import type { ReactNode, SVGProps } from 'react';
import {
  ArrowLeft,
  BarChart3,
  Bot,
  Check,
  ChevronRight,
  Code,
  Cpu,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Home,
  MoreHorizontal,
  Package,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  Trash2,
  Undo2,
} from 'lucide-react';
import { cn } from '../utils/cn';

/** 图标名 → lucide 组件（同时作为 icon 白名单） */
const registry = {
  search: Search,
  plus: Plus,
  refresh: RefreshCw,
  save: Save,
  play: Play,
  pause: Pause,
  trash: Trash2,
  external: ExternalLink,
  code: Code,
  settings: Settings,
  package: Package,
  check: Check,
  chevron: ChevronRight,
  back: ArrowLeft,
  eye: Eye,
  more: MoreHorizontal,
  download: Download,
  undo: Undo2,
  // 侧栏导航使用（Layout 的 NAV 表按名字取图标）
  home: Home,
  cpu: Cpu,
  chart: BarChart3,
  bot: Bot,
  log: FileText,
} as const;

export type IconName = keyof typeof registry;

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName;
  /** 渲染尺寸（px），默认 18 —— 与旧 Icon 组件默认值一致 */
  size?: number;
  /** 描边宽度，默认 1.6（lucide 默认 2，这里保持旧观感） */
  strokeWidth?: number;
  className?: string;
  children?: ReactNode;
}

export default function Icon({ name, size = 18, strokeWidth = 1.6, className, ...props }: IconProps) {
  const Glyph = registry[name];
  if (!Glyph) return null;
  return (
    <Glyph
      size={size}
      strokeWidth={strokeWidth}
      aria-hidden="true"
      className={cn('shrink-0', className)}
      {...props}
    />
  );
}
