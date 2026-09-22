import { formatFileSize } from './labels';

export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_DOCUMENT_TYPES = '.pdf,.jpg,.jpeg,.png';
export const DOCUMENT_FORMAT_HINT = 'Formatos aceitos: PDF, JPEG e PNG · limite de 10 MB.';

/** Client-side feedback only; the API remains the authority on the limit. */
export function fileSizeError(file: { size: number }): string | null {
  if (file.size <= MAX_DOCUMENT_BYTES) {
    return null;
  }
  return `O arquivo tem ${formatFileSize(file.size)} e excede o limite de 10 MB.`;
}
