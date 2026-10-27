import * as Select from '@radix-ui/react-select';
import { Fragment, type AriaAttributes } from 'react';
import { Check, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  group?: string;
}

interface SelectControlProps extends Pick<AriaAttributes, 'aria-invalid' | 'aria-describedby'> {
  value: string;
  onValueChange: (value: string) => void;
  options: readonly SelectOption[];
  label: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  id?: string;
  title?: string;
}

function Option({ option }: { option: SelectOption }) {
  return (
    <Select.Item
      className="select-control-option"
      value={`option:${option.value}`}
      disabled={option.disabled}
      textValue={option.label}
    >
      <Select.ItemText>{option.label}</Select.ItemText>
      <Select.ItemIndicator className="select-control-check">
        <Check size={14} />
      </Select.ItemIndicator>
    </Select.Item>
  );
}

/** 统一筛选控件；空字符串也可作为“全部”的有效选项。 */
export default function SelectControl({
  value,
  onValueChange,
  options,
  label,
  className,
  disabled = false,
  placeholder = '请选择',
  ...triggerProps
}: SelectControlProps) {
  const selected = options.find((option) => option.value === value);
  const groups: Array<{ label?: string; options: SelectOption[] }> = [];
  for (const option of options) {
    const previous = groups.at(-1);
    if (previous && previous.label === option.group) previous.options.push(option);
    else groups.push({ label: option.group, options: [option] });
  }
  return (
    <Select.Root
      value={selected ? `option:${value}` : ''}
      onValueChange={(next) => onValueChange(next.slice('option:'.length))}
      disabled={disabled}
    >
      <Select.Trigger {...triggerProps} className={cn('select-control', className)} aria-label={label}>
        <Select.Value placeholder={placeholder} />
        <Select.Icon className="select-control-icon">
          <ChevronDown size={15} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="select-control-menu"
          position="popper"
          align="start"
          sideOffset={6}
          collisionPadding={12}
        >
          <Select.ScrollUpButton className="select-control-scroll">
            <ChevronUp size={14} />
          </Select.ScrollUpButton>
          <Select.Viewport className="select-control-options">
            {groups.map((group) =>
              group.label ? (
                <Select.Group className="select-control-group" key={group.options[0].value}>
                  <Select.Label className="select-control-group-label">{group.label}</Select.Label>
                  {group.options.map((option) => (
                    <Option key={option.value} option={option} />
                  ))}
                </Select.Group>
              ) : (
                <Fragment key={group.options[0].value}>
                  {group.options.map((option) => (
                    <Option key={option.value} option={option} />
                  ))}
                </Fragment>
              ),
            )}
          </Select.Viewport>
          <Select.ScrollDownButton className="select-control-scroll">
            <ChevronDown size={14} />
          </Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
