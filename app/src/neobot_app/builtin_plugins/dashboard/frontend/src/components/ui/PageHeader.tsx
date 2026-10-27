import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  actions?: ReactNode;
  children?: ReactNode;
}

export default function PageHeader({ title, actions, children }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-heading">
        <h1 className="page-title">{title}</h1>
        {children}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
