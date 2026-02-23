import React from 'react';

const WorkflowOptionCard = ({
  icon: Icon,
  title,
  description,
  highlights = [],
  badge = '',
  onClick,
  accent = 'blue',
  className = '',
}) => {
  const accentClasses = {
    blue: 'border-blue-200 bg-blue-50 hover:bg-blue-100 text-blue-700',
    primary: 'border-primary bg-primary/5 hover:bg-primary/10 text-primary',
  };

  const rootAccent = accentClasses[accent] || accentClasses.blue;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative w-full rounded-xl border p-6 text-left transition-colors ${rootAccent} ${className}`}
    >
      {badge ? (
        <div className="absolute right-2 top-2">
          <span className="rounded-full bg-white px-2 py-1 text-xs font-bold text-primary shadow-sm">
            {badge}
          </span>
        </div>
      ) : null}

      <div className="mb-3 flex items-center justify-between">
        {Icon ? <Icon className="h-8 w-8" /> : null}
      </div>

      <h3 className="mb-2 text-lg font-semibold">{title}</h3>
      <p className="mb-4 text-sm text-gray-600">{description}</p>

      {highlights.length > 0 ? (
        <div className="text-xs font-medium text-inherit">
          {highlights.map((item) => (
            <div key={item}>✓ {item}</div>
          ))}
        </div>
      ) : null}
    </button>
  );
};

export default WorkflowOptionCard;
