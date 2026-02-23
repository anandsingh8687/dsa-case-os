import React from 'react';
import { Loader2 } from 'lucide-react';
import Button from './Button';

const ActionButton = ({
  children,
  icon: Icon = null,
  trailingIcon: TrailingIcon = null,
  loading = false,
  loadingText = 'Please wait...',
  className = '',
  disabled = false,
  ...props
}) => {
  const isDisabled = disabled || loading;

  return (
    <Button
      disabled={isDisabled}
      className={`inline-flex items-center justify-center gap-2 ${className}`}
      {...props}
    >
      {loading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          {loadingText}
        </>
      ) : (
        <>
          {Icon ? <Icon className="w-4 h-4" /> : null}
          {children}
          {TrailingIcon ? <TrailingIcon className="w-4 h-4" /> : null}
        </>
      )}
    </Button>
  );
};

export default ActionButton;
