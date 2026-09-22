import { describe, expect, it } from 'vitest';

import { fileSizeError, MAX_DOCUMENT_BYTES } from './upload';

describe('fileSizeError', () => {
  it('accepts files up to exactly ten megabytes', () => {
    expect(fileSizeError({ size: 0 })).toBeNull();
    expect(fileSizeError({ size: MAX_DOCUMENT_BYTES })).toBeNull();
  });

  it('reports the formatted size when the file exceeds the limit', () => {
    expect(fileSizeError({ size: MAX_DOCUMENT_BYTES + 1 })).toBe(
      'O arquivo tem 10 MB e excede o limite de 10 MB.',
    );
    expect(fileSizeError({ size: 12 * 1024 * 1024 })).toBe(
      'O arquivo tem 12 MB e excede o limite de 10 MB.',
    );
  });
});
