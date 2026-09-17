import { describe, expect, it } from 'vitest';

import { cn } from './utils';

describe('cn', () => {
  it('joins conditional classes and resolves Tailwind conflicts', () => {
    expect(cn('rounded-md p-2', false && 'hidden', 'p-4')).toBe('rounded-md p-4');
  });

  it('accepts class values supplied as objects and arrays', () => {
    expect(cn(['flex', { hidden: false, 'items-center': true }], 'gap-2')).toBe(
      'flex items-center gap-2',
    );
  });
});
