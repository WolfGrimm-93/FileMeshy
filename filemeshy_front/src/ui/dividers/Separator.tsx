import React from 'react'

export interface SeparatorProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: 'horizontal' | 'vertical'
  variant?: 'solid' | 'dashed' | 'dotted'
  spacing?: 'none' | 'sm' | 'md' | 'lg'
  thickness?: 'thin' | 'medium' | 'thick'
  className?: string
}

const orientationClasses = {
  horizontal: 'w-full',
  vertical: 'h-full',
}

const variantClasses = {
  solid: 'border-solid',
  dashed: 'border-dashed',
  dotted: 'border-dotted',
}

const spacingClasses = {
  horizontal: {
    none: '',
    sm: 'my-2',
    md: 'my-4',
    lg: 'my-6',
  },
  vertical: {
    none: '',
    sm: 'mx-2',
    md: 'mx-4',
    lg: 'mx-6',
  },
}

const thicknessClasses = {
  horizontal: {
    thin: 'border-t',
    medium: 'border-t-2',
    thick: 'border-t-4',
  },
  vertical: {
    thin: 'border-l',
    medium: 'border-l-2',
    thick: 'border-l-4',
  },
}

export function Separator({
  orientation = 'horizontal',
  variant = 'solid',
  spacing = 'md',
  thickness = 'thin',
  className = '',
  ...props
}: SeparatorProps) {
  const baseClasses = 'border-gray-200 dark:border-gray-800'

  return (
    <div
      className={`
        ${baseClasses}
        ${orientationClasses[orientation]}
        ${variantClasses[variant]}
        ${spacingClasses[orientation][spacing]}
        ${thicknessClasses[orientation][thickness]}
        ${className}
      `}
      role="separator"
      aria-orientation={orientation}
      {...props}
    />
  )
}
