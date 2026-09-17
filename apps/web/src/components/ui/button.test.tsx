import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/ui/button';

describe('Button', () => {
  it('renders through the @ alias with the JSX runtime', () => {
    const markup = renderToStaticMarkup(<Button type="button">Salvar</Button>);

    expect(markup).toContain('<button');
    expect(markup).toContain('Salvar');
  });
});
