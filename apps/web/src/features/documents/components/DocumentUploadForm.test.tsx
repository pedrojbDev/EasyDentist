// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { uploadDocumentMock } = vi.hoisted(() => ({ uploadDocumentMock: vi.fn() }));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, uploadDocument: uploadDocumentMock };
});

import { ApiError } from '@/lib/api/problem';

import { makeDocument } from '../test-fixtures';
import { DocumentUploadForm } from './DocumentUploadForm';

function pickFile(size: number, name = 'laudo.pdf'): File {
  const file = new File([], name, { type: 'application/pdf' });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

beforeEach(() => {
  uploadDocumentMock.mockReset();
});

afterEach(cleanup);

describe('DocumentUploadForm', () => {
  it('shows the selected file name and formatted size', async () => {
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['CLINICAL']}
        onUploaded={vi.fn()}
      />,
    );

    await userEvent.upload(screen.getByLabelText('Arquivo'), pickFile(2048, 'exame.pdf'));

    expect(screen.getByText('exame.pdf · 2 KB')).toBeTruthy();
    expect(screen.getByText(/Formatos aceitos: PDF, JPEG e PNG/)).toBeTruthy();
  });

  it('keeps the native input accessible behind the styled pt-BR label', () => {
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['CLINICAL']}
        onUploaded={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Arquivo') as HTMLInputElement;
    expect(input.type).toBe('file');
    expect(input.classList.contains('sr-only')).toBe(true);
    expect(screen.getByText('Selecionar arquivo')).toBeTruthy();
    expect(screen.getByText('Nenhum arquivo selecionado.')).toBeTruthy();
  });

  it('blocks files over ten megabytes with client-side feedback', async () => {
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['CLINICAL']}
        onUploaded={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByLabelText('Título'), 'Documento grande');
    await userEvent.upload(screen.getByLabelText('Arquivo'), pickFile(11 * 1024 * 1024));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'O arquivo excede o limite de 10 MB.',
    );
    expect(screen.getByText('laudo.pdf · 11 MB')).toBeTruthy();
    expect(screen.getByText('Selecionar arquivo')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Enviar documento' })).toHaveProperty(
      'disabled',
      true,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }));
    expect(uploadDocumentMock).not.toHaveBeenCalled();
  });

  it('uploads a valid file and clears the form', async () => {
    const onUploaded = vi.fn();
    uploadDocumentMock.mockResolvedValue(makeDocument());
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['CLINICAL']}
        onUploaded={onUploaded}
      />,
    );

    await userEvent.type(screen.getByLabelText('Título'), 'Tomografia');
    await userEvent.upload(screen.getByLabelText('Arquivo'), pickFile(1024));
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }));

    await waitFor(() => {
      expect(uploadDocumentMock).toHaveBeenCalledTimes(1);
    });
    const [clinicId, patientId, payload] = uploadDocumentMock.mock.calls[0] as [
      string,
      string,
      { title: string; category: string; file: File },
    ];
    expect(clinicId).toBe('c1');
    expect(patientId).toBe('p1');
    expect(payload.title).toBe('Tomografia');
    expect(payload.category).toBe('CLINICAL');
    expect(payload.file.name).toBe('laudo.pdf');
    expect(onUploaded).toHaveBeenCalledWith(makeDocument());
    expect(screen.getByText('Documento enviado com sucesso.')).toBeTruthy();
    expect((screen.getByLabelText('Título') as HTMLInputElement).value).toBe('');
  });

  it('offers only the categories the role can manage', () => {
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['ADMINISTRATIVE']}
        onUploaded={vi.fn()}
      />,
    );

    const options = screen.getAllByRole('option').map((option) => option.textContent);
    expect(options).toEqual(['Administrativo']);
  });

  it('translates upload failures into pt-BR guidance', async () => {
    uploadDocumentMock.mockRejectedValue(
      new ApiError({ status: 415, title: 'Formato não suportado' }),
    );
    render(
      <DocumentUploadForm
        clinicId="c1"
        patientId="p1"
        categories={['CLINICAL']}
        onUploaded={vi.fn()}
      />,
    );

    await userEvent.type(screen.getByLabelText('Título'), 'Arquivo estranho');
    await userEvent.upload(screen.getByLabelText('Arquivo'), pickFile(1024));
    await userEvent.click(screen.getByRole('button', { name: 'Enviar documento' }));

    expect((await screen.findByRole('alert')).textContent).toContain(
      'Formato não aceito. Envie um arquivo PDF, JPEG ou PNG.',
    );
  });
});
