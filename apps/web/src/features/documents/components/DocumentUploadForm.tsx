'use client';

import { Paperclip, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';

import {
  documentErrorMessage,
  uploadDocument,
  type DocumentCategory,
  type PatientDocument,
} from '../api';
import { categoryLabel, formatFileSize } from '../labels';
import { ACCEPTED_DOCUMENT_TYPES, DOCUMENT_FORMAT_HINT, fileSizeError } from '../upload';

export function DocumentUploadForm({
  clinicId,
  patientId,
  categories,
  onUploaded,
}: {
  clinicId: string;
  patientId: string;
  categories: DocumentCategory[];
  onUploaded: (document: PatientDocument) => void;
}) {
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<DocumentCategory>(categories[0] ?? 'ADMINISTRATIVE');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const sizeError = file === null ? null : fileSizeError(file);
  const canSubmit = file !== null && sizeError === null && title.trim() !== '' && !pending;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (file === null) {
      setError('Selecione um arquivo PDF, JPEG ou PNG.');
      return;
    }
    const sizeProblem = fileSizeError(file);
    if (sizeProblem !== null) {
      setError(sizeProblem);
      return;
    }
    if (title.trim() === '') {
      setError('Informe um título para o documento.');
      return;
    }
    setError(null);
    setPending(true);
    try {
      const created = await uploadDocument(clinicId, patientId, {
        file,
        title: title.trim(),
        category,
      });
      onUploaded(created);
      setTitle('');
      setFile(null);
      if (inputRef.current !== null) {
        inputRef.current.value = '';
      }
      setMessage('Documento enviado com sucesso.');
    } catch (cause) {
      setError(documentErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="flex flex-col gap-4 border-t border-border pt-4"
    >
      {error !== null && <Feedback tone="error">{error}</Feedback>}
      {message !== null && <Feedback tone="success">{message}</Feedback>}

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,12rem)]">
        <div className="flex flex-col gap-1">
          <label htmlFor="document-title" className="app-label">
            Título
          </label>
          <input
            id="document-title"
            name="document-title"
            type="text"
            value={title}
            maxLength={200}
            onChange={(event) => setTitle(event.target.value)}
            className="app-field"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="document-category" className="app-label">
            Categoria
          </label>
          <select
            id="document-category"
            name="document-category"
            value={category}
            onChange={(event) => setCategory(event.target.value as DocumentCategory)}
            className="app-field"
          >
            {categories.map((option) => (
              <option key={option} value={option}>
                {categoryLabel(option)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <span id="document-file-label" className="app-label">
          Arquivo
        </span>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            id="document-file"
            name="document-file"
            type="file"
            accept={ACCEPTED_DOCUMENT_TYPES}
            aria-labelledby="document-file-label"
            aria-describedby="document-file-hint"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError(null);
              setMessage(null);
            }}
            className="peer sr-only"
          />
          <Button asChild variant="outline" size="sm">
            <label
              htmlFor="document-file"
              className="cursor-pointer peer-focus-visible:border-ring peer-focus-visible:ring-3 peer-focus-visible:ring-ring/30"
            >
              <Paperclip aria-hidden="true" />
              Selecionar arquivo
            </label>
          </Button>
          <p className="text-sm text-muted-foreground">
            {file === null
              ? 'Nenhum arquivo selecionado.'
              : `${file.name} · ${formatFileSize(file.size)}`}
          </p>
        </div>
        {sizeError !== null && <Feedback tone="error">{sizeError}</Feedback>}
        <p id="document-file-hint" className="text-xs text-muted-foreground">
          {DOCUMENT_FORMAT_HINT}
        </p>
      </div>

      <Button type="submit" size="sm" disabled={!canSubmit} className="w-fit">
        <Upload aria-hidden="true" />
        {pending ? 'Enviando...' : 'Enviar documento'}
      </Button>
    </form>
  );
}
