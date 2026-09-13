import { useRef, useState } from 'react';
import type { DragEvent, ChangeEvent } from 'react';
import { Upload, Image as ImageIcon, X } from 'lucide-react';
import { getFileTypeIcon } from '@/shared/utils/fileTypeIcon';

export interface FileUploadProps {
  accept?: string;
  multiple?: boolean;
  maxSize?: number; // in MB
  onFilesSelected?: (files: File[]) => void;
  variant?: 'default' | 'compact' | 'image';
  disabled?: boolean;
  className?: string;
}

export const FileUpload = ({
  accept,
  multiple = false,
  maxSize = 10,
  onFilesSelected,
  variant = 'default',
  disabled = false,
  className = ''
}: FileUploadProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFiles = (files: File[]): File[] => {
    const maxSizeBytes = maxSize * 1024 * 1024;
    const validFiles: File[] = [];

    for (const file of files) {
      if (file.size > maxSizeBytes) {
        setError(`El archivo ${file.name} excede el tamaño máximo de ${maxSize}MB`);
        continue;
      }
      validFiles.push(file);
    }

    return validFiles;
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setError(null);
    const fileArray = Array.from(files);
    const validFiles = validateFiles(fileArray);

    if (validFiles.length > 0 && onFilesSelected) {
      onFilesSelected(validFiles);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (!disabled) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
  };

  const handleClick = () => {
    inputRef.current?.click();
  };

  if (variant === 'compact') {
    return (
      <div className={className}>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleChange}
          disabled={disabled}
          className="hidden"
        />
        <button
          type="button"
          onClick={handleClick}
          disabled={disabled}
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-brand-600 border border-transparent rounded-lg hover:bg-brand-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-brand-500 disabled:opacity-50 disabled:cursor-not-allowed dark:bg-brand-500 dark:hover:bg-brand-600"
        >
          <Upload className="w-5 h-5 mr-2" />
          Seleccionar archivo{multiple ? 's' : ''}
        </button>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
    );
  }

  if (variant === 'image') {
    return (
      <div className={className}>
        <input
          ref={inputRef}
          type="file"
          accept={accept || 'image/*'}
          multiple={multiple}
          onChange={handleChange}
          disabled={disabled}
          className="hidden"
        />
        <div
          onClick={handleClick}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
            isDragging
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/10'
              : 'border-gray-300 dark:border-gray-600 hover:border-brand-400 dark:hover:border-brand-500'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <div className="flex flex-col items-center justify-center space-y-3">
            <div className="flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full">
              <ImageIcon className="w-8 h-8 text-gray-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                Clic para subir o arrastra aquí
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                PNG, JPG, GIF hasta {maxSize}MB
              </p>
            </div>
          </div>
        </div>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
    );
  }

  return (
    <div className={className}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={handleChange}
        disabled={disabled}
        className="hidden"
      />
      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/10'
            : 'border-gray-300 dark:border-gray-600 hover:border-brand-400 dark:hover:border-brand-500'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <div className="flex flex-col items-center justify-center space-y-4">
          <Upload className="w-12 h-12 text-gray-400" />
          <div>
            <p className="text-base font-medium text-gray-900 dark:text-white">
              Arrastra y suelta tu{multiple ? 's' : ''} archivo{multiple ? 's' : ''} aquí
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              o haz clic para seleccionar
            </p>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Tamaño máximo: {maxSize}MB
          </p>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
};

// File List component to show selected files
export interface SelectedFile {
  name: string;
  size: number;
  type: string;
}

export interface FileListProps {
  files: SelectedFile[];
  onRemove?: (index: number) => void;
  className?: string;
}

export const FileList = ({ files, onRemove, className = '' }: FileListProps) => {
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getFileIcon = (type: string) => {
    const Icon = getFileTypeIcon(type);
    return <Icon className="w-5 h-5" />;
  };

  if (files.length === 0) return null;

  return (
    <ul className={`divide-y divide-gray-200 dark:divide-gray-700 ${className}`}>
      {files.map((file, index) => (
        <li key={index} className="py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3 flex-1 min-w-0">
            <div className="shrink-0 text-gray-400 dark:text-gray-500">
              {getFileIcon(file.type)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {file.name}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {formatFileSize(file.size)}
              </p>
            </div>
          </div>
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="ml-4 shrink-0 text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
};
