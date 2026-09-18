// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';

import { useFocusFirstInvalid } from './use-focus-first-invalid';

function TestForm() {
  const formRef = useRef<HTMLFormElement>(null);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  useFocusFirstInvalid(errors, formRef);

  return (
    <form
      ref={formRef}
      onSubmit={(event) => {
        event.preventDefault();
        setErrors({ email: 'Informe seu e-mail.', password: 'Informe sua senha.' });
      }}
    >
      <label htmlFor="t-email">E-mail</label>
      <input id="t-email" aria-invalid={errors.email !== undefined} />
      <label htmlFor="t-password">Senha</label>
      <input id="t-password" aria-invalid={errors.password !== undefined} />
      <button type="submit">Enviar</button>
    </form>
  );
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useFocusFirstInvalid', () => {
  it('focuses the first invalid field after validation', async () => {
    render(<TestForm />);

    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }));

    expect(document.activeElement).toBe(screen.getByLabelText('E-mail'));
  });

  it('does not steal focus while there are no errors', () => {
    render(<TestForm />);

    expect(document.activeElement).toBe(document.body);
  });
});
