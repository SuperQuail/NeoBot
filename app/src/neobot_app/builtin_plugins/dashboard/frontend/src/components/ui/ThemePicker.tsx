import { Monitor, Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getThemePreference, setThemePreference, type ThemePreference } from '../../utils/theme';
const choices = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'auto', label: '跟随系统', icon: Monitor },
] as const;
export default function ThemePicker() {
  const [preference, setPreference] = useState<ThemePreference>(getThemePreference);
  useEffect(() => {
    const sync = () => setPreference(getThemePreference());
    window.addEventListener('dashboard-theme-change', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('dashboard-theme-change', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  return (
    <div className="theme-picker" role="group" aria-label="界面主题">
      {choices.map(({ value, label, icon: Glyph }) => (
        <button
          key={value}
          type="button"
          aria-label={label}
          title={label}
          aria-pressed={preference === value}
          onClick={() => setThemePreference(value)}
        >
          <Glyph size={15} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
