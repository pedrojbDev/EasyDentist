'use client';

import { Archive, Download, FileText, RotateCcw } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { StatusBadge } from '@/components/ui/status-badge';

import {
  archiveDocument,
  documentErrorMessage,
  downloadDocumentUrl,
  restoreDocument,
  type DocumentCategory,
  type DocumentStatus,
  type PatientDocument,
} from '../api';
import { categoryLabel, formatDateTime, formatFileSize, statusLabel } from '../labels';
import {
  canManageCategory,
  canReadCategory,
  manageableCategories,
  readableCategories,
  type DocumentCapabilities,
} from '../permissions';
import { DocumentUploadForm } from './DocumentUploadForm';

type CategoryFilter = DocumentCategory | 'ALL';

export function DocumentsPanel({
  clinicId,
  patientId,
  documents,
  capabilities,
}: {
  clinicId: string;
  patientId: string;
  documents: PatientDocument[];
  capabilities: DocumentCapabilities;
}) {
  const [rows, setRows] = useState(documents);
  const [category, setCategory] = useState<CategoryFilter>('ALL');
  const [status, setStatus] = useState<DocumentStatus>('ACTIVE');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const readable = readableCategories(capabilities);
  const manageable = manageableCategories(capabilities);
  const visible = useMemo(
    () =>
      rows.filter(
        (row) =>
          canReadCategory(capabilities, row.category) &&
          row.status === status &&
          (category === 'ALL' || row.category === category),
      ),
    [rows, capabilities, status, category],
  );

  async function handleToggle(document: PatientDocument) {
    setMessage(null);
    setError(null);
    setPendingId(document.id);
    try {
      const updated =
        document.status === 'ACTIVE'
          ? await archiveDocument(clinicId, patientId, document.id)
          : await restoreDocument(clinicId, patientId, document.id);
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
      setMessage(updated.status === 'ACTIVE' ? 'Documento restaurado.' : 'Documento arquivado.');
    } catch (cause) {
      setError(documentErrorMessage(cause));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <section className="app-panel flex flex-col gap-4" aria-labelledby="documents-panel-title">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
        >
          <FileText className="size-5" />
        </span>
        <div>
          <h2 id="documents-panel-title" className="font-semibold text-foreground">
            Documentos do paciente
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Arquivos privados ficam acessíveis apenas pela API, com download e arquivamento
            controlados pelo seu papel na clínica.
          </p>
        </div>
      </div>

      {error !== null && <Feedback tone="error">{error}</Feedback>}
      {message !== null && <Feedback tone="success">{message}</Feedback>}

      <div className="grid gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,12rem)]">
        <div className="flex flex-col gap-1">
          <label htmlFor="document-filter-category" className="app-label">
            Filtrar por categoria
          </label>
          <select
            id="document-filter-category"
            name="document-filter-category"
            value={category}
            onChange={(event) => setCategory(event.target.value as CategoryFilter)}
            className="app-field"
          >
            <option value="ALL">Todas</option>
            {readable.map((option) => (
              <option key={option} value={option}>
                {categoryLabel(option)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="document-filter-status" className="app-label">
            Filtrar por situação
          </label>
          <select
            id="document-filter-status"
            name="document-filter-status"
            value={status}
            onChange={(event) => setStatus(event.target.value as DocumentStatus)}
            className="app-field"
          >
            <option value="ACTIVE">Ativos</option>
            <option value="ARCHIVED">Arquivados</option>
          </select>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="rounded-lg bg-muted/55 p-4 text-sm text-muted-foreground">
          {rows.length === 0
            ? 'Nenhum documento registrado ainda.'
            : 'Nenhum documento encontrado com os filtros selecionados.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm">
            <caption className="sr-only">Documentos do paciente</caption>
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Documento
                </th>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Categoria
                </th>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Enviado em
                </th>
                <th scope="col" className="py-2 pr-3 font-semibold">
                  Situação
                </th>
                <th scope="col" className="py-2 text-right font-semibold">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((document) => (
                <tr key={document.id} className="border-b border-border/70 align-top">
                  <td className="py-3 pr-3">
                    <p className="font-semibold text-foreground">{document.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {document.original_filename} · {formatFileSize(document.size_bytes)}
                    </p>
                  </td>
                  <td className="py-3 pr-3">
                    <StatusBadge tone="neutral">{categoryLabel(document.category)}</StatusBadge>
                  </td>
                  <td className="py-3 pr-3 text-muted-foreground">
                    {formatDateTime(document.created_at)}
                  </td>
                  <td className="py-3 pr-3">
                    <StatusBadge tone={document.status === 'ACTIVE' ? 'info' : 'neutral'}>
                      {statusLabel(document.status)}
                    </StatusBadge>
                  </td>
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      <Button asChild variant="ghost" size="sm">
                        <a
                          href={downloadDocumentUrl(clinicId, patientId, document.id)}
                          aria-label={`Baixar ${document.title}`}
                        >
                          <Download aria-hidden="true" />
                          Baixar
                        </a>
                      </Button>
                      {canManageCategory(capabilities, document.category) && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={pendingId === document.id}
                          onClick={() => void handleToggle(document)}
                          aria-label={
                            document.status === 'ACTIVE'
                              ? `Arquivar ${document.title}`
                              : `Restaurar ${document.title}`
                          }
                        >
                          {document.status === 'ACTIVE' ? (
                            <>
                              <Archive aria-hidden="true" />
                              Arquivar
                            </>
                          ) : (
                            <>
                              <RotateCcw aria-hidden="true" />
                              Restaurar
                            </>
                          )}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {manageable.length > 0 && (
        <DocumentUploadForm
          clinicId={clinicId}
          patientId={patientId}
          categories={manageable}
          onUploaded={(created) => setRows((current) => [created, ...current])}
        />
      )}
    </section>
  );
}
