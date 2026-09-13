import { Check } from 'lucide-react'

export interface ProgressProps {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  showLabel?: boolean;
  label?: string;
  className?: string;
}

export const Progress = ({
  value,
  max = 100,
  size = 'md',
  variant = 'default',
  showLabel = false,
  label,
  className = ''
}: ProgressProps) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  const sizeClasses = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3'
  };

  const variantClasses = {
    default: 'bg-brand-600 dark:bg-brand-500',
    success: 'bg-green-600 dark:bg-green-500',
    warning: 'bg-yellow-600 dark:bg-yellow-500',
    danger: 'bg-red-600 dark:bg-red-500',
    info: 'bg-blue-600 dark:bg-blue-500'
  };

  return (
    <div className={className}>
      {(showLabel || label) && (
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
          </span>
          {showLabel && (
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {Math.round(percentage)}%
            </span>
          )}
        </div>
      )}
      <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden ${sizeClasses[size]}`}>
        <div
          className={`${sizeClasses[size]} ${variantClasses[variant]} transition-all duration-300 ease-in-out`}
          style={{ width: `${percentage}%` }}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={max}
        />
      </div>
    </div>
  );
};

// Circle Progress
export interface CircleProgressProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  showLabel?: boolean;
  label?: string;
  className?: string;
}

export const CircleProgress = ({
  value,
  max = 100,
  size = 120,
  strokeWidth = 8,
  variant = 'default',
  showLabel = true,
  label,
  className = ''
}: CircleProgressProps) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (percentage / 100) * circumference;

  const variantColors = {
    default: '#ea580c', // brand-600
    success: '#16a34a', // green-600
    warning: '#ca8a04', // yellow-600
    danger: '#dc2626', // red-600
    info: '#2563eb' // blue-600
  };

  return (
    <div className={`inline-flex flex-col items-center ${className}`}>
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-gray-200 dark:text-gray-700"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={variantColors[variant]}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-300 ease-in-out"
        />
        {/* Percentage text */}
        {showLabel && (
          <text
            x="50%"
            y="50%"
            textAnchor="middle"
            dy=".3em"
            className="text-2xl font-bold fill-gray-900 dark:fill-white transform rotate-90"
            style={{ transformOrigin: 'center' }}
          >
            {Math.round(percentage)}%
          </text>
        )}
      </svg>
      {label && (
        <span className="mt-2 text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
        </span>
      )}
    </div>
  );
};

// Step Progress
export interface Step {
  id: string;
  label: string;
  description?: string;
}

export interface StepProgressProps {
  steps: Step[];
  currentStep: number;
  className?: string;
}

export const StepProgress = ({ steps, currentStep, className = '' }: StepProgressProps) => {
  return (
    <div className={className}>
      <ol className="flex items-center w-full">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isLast = index === steps.length - 1;

          return (
            <li key={step.id} className={`flex items-center ${!isLast ? 'flex-1' : ''}`}>
              <div className="flex flex-col items-center">
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors ${
                    isCompleted || isCurrent
                      ? 'border-brand-600 bg-brand-600 dark:border-brand-500 dark:bg-brand-500'
                      : 'border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800'
                  }`}
                >
                  {isCompleted ? (
                    <Check className="w-5 h-5 text-white" />
                  ) : (
                    <span
                      className={`text-sm font-semibold ${
                        isCurrent ? 'text-white' : 'text-gray-500 dark:text-gray-400'
                      }`}
                    >
                      {index + 1}
                    </span>
                  )}
                </div>
                <div className="mt-2 text-center">
                  <span
                    className={`text-sm font-medium ${
                      isCompleted || isCurrent
                        ? 'text-brand-600 dark:text-brand-500'
                        : 'text-gray-500 dark:text-gray-400'
                    }`}
                  >
                    {step.label}
                  </span>
                  {step.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {step.description}
                    </p>
                  )}
                </div>
              </div>
              {!isLast && (
                <div
                  className={`flex-1 h-0.5 mx-2 transition-colors ${
                    isCompleted
                      ? 'bg-brand-600 dark:bg-brand-500'
                      : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                  style={{ marginBottom: step.description ? '3rem' : '2rem' }}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
};
