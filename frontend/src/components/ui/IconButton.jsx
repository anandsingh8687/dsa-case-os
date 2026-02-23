import React from 'react';

const SIZE_CLASSES = {
  sm: 'h-8 w-8',
  md: 'h-9 w-9',
  lg: 'h-10 w-10',
};

const VARIANT_CLASSES = {
  ghost: 'border border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900',
  danger: 'border border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700',
  primary: 'border border-blue-200 text-primary hover:bg-blue-50 hover:text-blue-700',
};

const IconButton = ({
  icon: Icon,
  label,
  title,
  size = 'md',
  variant = 'ghost',
  className = '',
  disabled = false,
  ...props
}) => (
  <button
    type="button"
    aria-label={label || title}
    title={title || label}
    disabled={disabled}
    className={`inline-flex items-center justify-center rounded-full transition-colors ${
      SIZE_CLASSES[size] || SIZE_CLASSES.md
    } ${VARIANT_CLASSES[variant] || VARIANT_CLASSES.ghost} ${
      disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
    } ${className}`}
    {...props}
  >
    {Icon ? <Icon className={size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4'} /> : null}
  </button>
);

export default IconButton;
