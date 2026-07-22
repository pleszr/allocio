import { Fragment, type ReactNode } from "react";
import { Icon } from "./Icon";

interface TopBarProps {
  crumbs: string[];
  action?: ReactNode;
}

export function TopBar({ crumbs, action }: TopBarProps) {
  const month = new Date().toLocaleDateString("en-US", { month: "short", year: "numeric" });
  return (
    <header className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <Fragment key={i}>
            {i > 0 && <span className="crumbs-sep">/</span>}
            {i === crumbs.length - 1 ? <strong>{c}</strong> : <span>{c}</span>}
          </Fragment>
        ))}
      </div>
      <div className="topbar-actions">
        <span className="month-pill">
          <Icon name="calendar" size={12} /> {month}
        </span>
        {action}
      </div>
    </header>
  );
}
