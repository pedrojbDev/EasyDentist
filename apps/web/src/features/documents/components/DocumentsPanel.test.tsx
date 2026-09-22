// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { archiveDocumentMock, restoreDocumentMock, uploadDocumentMock } = vi.hoisted(() => ({
  archiveDocumentMock: vi.fn(),
  restoreDocumentMock: vi.fn(),
  uploadDocumentMock: vi.fn(),
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    archiveDocument: archiveDocumentMock,
    restoreDocument: restoreDocumentMock,
    uploadDocument: uploadDocumentMock,
  };
});

import { documentCapabilities } from '../permissions';
import { makeDocument } from '../test-fixtures';
import { DocumentsPanel } from './DocumentsPanel';

beforeEach(() => {
  archiveDocumentMock.mockReset();
  restoreDocumentMock.mockReset();
  uploadDocumentMock.mockReset();
});

afterEach(cleanup);

describe('DocumentsPanel', () => {
  it('lists documents with pt-BR metadata and a download link', () => {
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[makeDocument({ title: 'Laudo clínico' })]}
        capabilities={documentCapabilities('OWNER')}
      />,
    );

    const table = within(screen.getByRole('table'));
    expect(table.getByText('Laudo clínico')).toBeTruthy();
    expect(table.getByText('laudo.pdf · 2 KB')).toBeTruthy();
    expect(table.getByText('Clínico')).toBeTruthy();
    expect(table.getByText('Ativo')).toBeTruthy();
    const download = table.getByRole('link', { name: 'Baixar Laudo clínico' });
    expect(download.getAttribute('href')).toBe(
      '/api/v1/clinics/c1/patients/p1/documents/d1/content',
    );
  });

  it('shows an empty state without documents', () => {
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[]}
        capabilities={documentCapabilities('OWNER')}
      />,
    );

    expect(screen.getByText('Nenhum documento registrado ainda.')).toBeTruthy();
  });

  it('filters by status and hides archived documents by default', async () => {
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[
          makeDocument({ id: 'd1', title: 'Documento atual' }),
          makeDocument({
            id: 'd2',
            title: 'Documento antigo',
            status: 'ARCHIVED',
            archived_at: '2026-09-21T12:00:00Z',
          }),
        ]}
        capabilities={documentCapabilities('OWNER')}
      />,
    );

    expect(screen.getByText('Documento atual')).toBeTruthy();
    expect(screen.queryByText('Documento antigo')).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText('Filtrar por situação'), 'ARCHIVED');

    expect(screen.getByText('Documento antigo')).toBeTruthy();
    expect(screen.queryByText('Documento atual')).toBeNull();
    expect(within(screen.getByRole('table')).getByText('Arquivado')).toBeTruthy();
  });

  it('hides clinical documents from roles without clinical read', () => {
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[
          makeDocument({ id: 'd1', title: 'Documento administrativo', category: 'ADMINISTRATIVE' }),
          makeDocument({ id: 'd2', title: 'Laudo clínico', category: 'CLINICAL' }),
        ]}
        capabilities={documentCapabilities('RECEPTIONIST')}
      />,
    );

    expect(screen.getByText('Documento administrativo')).toBeTruthy();
    expect(screen.queryByText('Laudo clínico')).toBeNull();
    const categoryOptions = within(screen.getByLabelText('Filtrar por categoria'))
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(categoryOptions).toEqual(['Todas', 'Administrativo']);
  });

  it('archives a document and moves it to the archived filter', async () => {
    archiveDocumentMock.mockResolvedValue(
      makeDocument({ status: 'ARCHIVED', archived_at: '2026-09-22T12:00:00Z' }),
    );
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[makeDocument()]}
        capabilities={documentCapabilities('OWNER')}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /^Arquivar/ }));

    await waitFor(() => {
      expect(archiveDocumentMock).toHaveBeenCalledWith('c1', 'p1', 'd1');
    });
    expect(await screen.findByText('Documento arquivado.')).toBeTruthy();
    expect(screen.queryByText('Laudo clínico')).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText('Filtrar por situação'), 'ARCHIVED');

    expect(within(screen.getByRole('table')).getByText('Arquivado')).toBeTruthy();
  });

  it('restores an archived document back to the active list', async () => {
    restoreDocumentMock.mockResolvedValue(makeDocument());
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[makeDocument({ status: 'ARCHIVED', archived_at: '2026-09-22T12:00:00Z' })]}
        capabilities={documentCapabilities('OWNER')}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por situação'), 'ARCHIVED');

    await userEvent.click(screen.getByRole('button', { name: /^Restaurar/ }));

    await waitFor(() => {
      expect(restoreDocumentMock).toHaveBeenCalledWith('c1', 'p1', 'd1');
    });
    expect(await screen.findByText('Documento restaurado.')).toBeTruthy();

    await userEvent.selectOptions(screen.getByLabelText('Filtrar por situação'), 'ACTIVE');

    expect(within(screen.getByRole('table')).getByText('Ativo')).toBeTruthy();
  });

  it('hides management actions from read-only roles', () => {
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[makeDocument()]}
        capabilities={documentCapabilities('ASSISTANT')}
      />,
    );

    expect(screen.queryByRole('button', { name: /^Arquivar/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Enviar documento' })).toBeNull();
    expect(screen.queryByLabelText('Título')).toBeNull();
  });

  it('prepends an uploaded document to the list', async () => {
    uploadDocumentMock.mockResolvedValue(
      makeDocument({ id: 'd9', title: 'Novo exame', original_filename: 'exame.png' }),
    );
    render(
      <DocumentsPanel
        clinicId="c1"
        patientId="p1"
        documents={[makeDocument()]}
        capabilities={documentCapabilities('DENTIST')}
      />,
    );

    await userEvent.type(screen.getByLabelText('Título'), 'Novo exame');
    const file = new File([], 'exame.png', { type: 'image/png' });
    Object.defineProperty(file, 'size', { value: 1024 });
    await userEvent.upload(screen.getByLabelText('Arquivo'), file);
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }));

    expect(await screen.findByText('Novo exame')).toBeTruthy();
    expect(screen.getByText('Documento enviado com sucesso.')).toBeTruthy();
  });
});
