import { describe, expect, it } from 'vitest';

import { fileSizeError, MAX_DOCUMENT_BYTES } from './upload';

describe('fileSizeError', () => {
  it('accepts files up to exactly ten megabytes', () => {
    expect(fileSizeError({ size: 0 })).toBeNull();
    expect(fileSizeError({ size: MAX_DOCUMENT_BYTES })).toBeNull();
  });

  it('reports the limit without echoing a rounded size that contradicts it', () => {
    expect(fileSizeError({ size: MAX_DOCUMENT_BYTES + 1 })).toBe(
      'O arquivo excede o limite de 10 MB.',
    );
    expect(fileSizeError({ size: 12 * 1024 * 1024 })).toBe('O arquivo excede o limite de 10 MB.');
  });
});
