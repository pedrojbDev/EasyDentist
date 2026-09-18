// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Button } from './button';

afterEach(cleanup);

describe('Button (interaction)', () => {
  it('calls the click handler once through the real DOM', async () => {
    const onClick = vi.fn();
    render(
      <Button type="button" onClick={onClick}>
        Salvar
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not fire when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button type="button" disabled onClick={onClick}>
        Salvar
      </Button>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));

    expect(onClick).not.toHaveBeenCalled();
  });
});
