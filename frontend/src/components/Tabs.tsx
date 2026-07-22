export interface TabItem<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface TabsProps<T extends string> {
  value: T;
  items: TabItem<T>[];
  onChange: (value: T) => void;
}

export function Tabs<T extends string>({ value, items, onChange }: TabsProps<T>) {
  return (
    <nav className="tabs" role="tablist">
      {items.map((t) => (
        <button
          key={t.value}
          role="tab"
          className="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
        >
          {t.label}
          {t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}
