'use client';

import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';

import { getWorkingHours, replaceWorkingHours, type WorkingHourInterval } from '../api';

const weekdays = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

function readableError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return 'Há consultas futuras fora do novo expediente. Resolva-as antes de reduzir os horários.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return 'Você só pode alterar o expediente do seu próprio cadastro profissional.';
  }
  return 'Não foi possível carregar ou salvar o expediente.';
}

export function WorkingHoursEditor({
  clinicId,
  professionalId,
  enabled,
}: {
  clinicId: string;
  professionalId: string;
  enabled: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [intervals, setIntervals] = useState<WorkingHourInterval[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!expanded || loaded) return;
    let active = true;
    setLoading(true);
    void getWorkingHours(clinicId, professionalId)
      .then((result) => {
        if (active) setIntervals(result.intervals);
      })
      .catch((cause: unknown) => {
        if (active) setError(readableError(cause));
      })
      .finally(() => {
        if (active) {
          setLoading(false);
          setLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [clinicId, expanded, loaded, professionalId]);

  function change(index: number, key: keyof WorkingHourInterval, value: string) {
    setIntervals((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: key === 'weekday' ? Number(value) : value } : item,
      ),
    );
    setSaved(false);
    setError(null);
  }

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await replaceWorkingHours(clinicId, professionalId, { intervals });
      setSaved(true);
    } catch (cause) {
      setError(readableError(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-3 border-t border-border pt-3">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? 'Ocultar expediente' : 'Configurar expediente semanal'}
      </Button>
      {expanded && (
        <div className="mt-3 grid gap-3">
          {!enabled && (
            <p className="text-xs text-muted-foreground">Acesso somente para consulta.</p>
          )}
          {loading ? (
            <p className="text-sm text-muted-foreground" role="status">
              Carregando expediente…
            </p>
          ) : intervals.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Sem horários semanais. Este profissional ainda não pode receber consultas.
            </p>
          ) : (
            <ul className="grid gap-2">
              {intervals.map((interval, index) => (
                <li
                  key={`${interval.weekday}-${interval.starts_at}-${index}`}
                  className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]"
                >
                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    Dia
                    <select
                      className="app-field min-h-9 text-sm text-foreground"
                      disabled={!enabled || saving}
                      value={interval.weekday}
                      onChange={(event) => change(index, 'weekday', event.target.value)}
                    >
                      {weekdays.map((day, weekday) => (
                        <option key={day} value={weekday}>
                          {day}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    Início
                    <input
                      className="app-field min-h-9 text-sm text-foreground"
                      type="time"
                      disabled={!enabled || saving}
                      value={interval.starts_at.slice(0, 5)}
                      onChange={(event) => change(index, 'starts_at', event.target.value)}
                    />
                  </label>
                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    Fim
                    <input
                      className="app-field min-h-9 text-sm text-foreground"
                      type="time"
                      disabled={!enabled || saving}
                      value={interval.ends_at.slice(0, 5)}
                      onChange={(event) => change(index, 'ends_at', event.target.value)}
                    />
                  </label>
                  {enabled && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={saving}
                      onClick={() =>
                        setIntervals((current) => current.filter((_, i) => i !== index))
                      }
                    >
                      Remover
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {enabled && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={saving}
                onClick={() =>
                  setIntervals((current) => [
                    ...current,
                    {
                      weekday: 0,
                      starts_at: '08:00',
                      ends_at: '17:00',
                    },
                  ])
                }
              >
                Adicionar intervalo
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={saving || loading}
                onClick={() => void save()}
              >
                {saving ? 'Salvando…' : 'Salvar expediente'}
              </Button>
            </div>
          )}
          {error && <Feedback tone="error">{error}</Feedback>}
          {saved && <Feedback tone="success">Expediente atualizado.</Feedback>}
        </div>
      )}
    </div>
  );
}
