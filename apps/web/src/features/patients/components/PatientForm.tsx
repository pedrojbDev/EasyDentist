'use client';

import { CircleAlert } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Feedback } from '@/components/ui/feedback';
import { ApiError } from '@/lib/api/problem';
import { useFocusFirstInvalid } from '@/lib/use-focus-first-invalid';

import { createPatient, updatePatient, type Patient, type PatientCreateRequest } from '../api';
import { formatCpf, isValidCpf, normalizeCpf } from '../cpf';
import { patientAge } from '../labels';

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const STATE_PATTERN = /^[A-Za-z]{2}$/;

type FormValues = {
  fullName: string;
  socialName: string;
  birthDate: string;
  cpf: string;
  phone: string;
  phoneSecondary: string;
  email: string;
  postalCode: string;
  street: string;
  number: string;
  complement: string;
  district: string;
  city: string;
  state: string;
  occupation: string;
  nationality: string;
  birthplace: string;
  guardianName: string;
  guardianRelationship: string;
  guardianPhone: string;
  emergencyContactName: string;
  emergencyContactRelationship: string;
  emergencyContactPhone: string;
  administrativeNotes: string;
};

type FieldErrors = Partial<Record<keyof FormValues, string>>;

const EMPTY_VALUES: FormValues = {
  fullName: '',
  socialName: '',
  birthDate: '',
  cpf: '',
  phone: '',
  phoneSecondary: '',
  email: '',
  postalCode: '',
  street: '',
  number: '',
  complement: '',
  district: '',
  city: '',
  state: '',
  occupation: '',
  nationality: '',
  birthplace: '',
  guardianName: '',
  guardianRelationship: '',
  guardianPhone: '',
  emergencyContactName: '',
  emergencyContactRelationship: '',
  emergencyContactPhone: '',
  administrativeNotes: '',
};

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function initialValues(patient?: Patient): FormValues {
  if (!patient) {
    return EMPTY_VALUES;
  }
  return {
    fullName: patient.full_name,
    socialName: patient.social_name ?? '',
    birthDate: patient.birth_date,
    cpf: patient.cpf ? formatCpf(patient.cpf) : '',
    phone: patient.phone,
    phoneSecondary: patient.phone_secondary ?? '',
    email: patient.email ?? '',
    postalCode: patient.postal_code ?? '',
    street: patient.street ?? '',
    number: patient.number ?? '',
    complement: patient.complement ?? '',
    district: patient.district ?? '',
    city: patient.city ?? '',
    state: patient.state ?? '',
    occupation: patient.occupation ?? '',
    nationality: patient.nationality ?? '',
    birthplace: patient.birthplace ?? '',
    guardianName: patient.guardian_name ?? '',
    guardianRelationship: patient.guardian_relationship ?? '',
    guardianPhone: patient.guardian_phone ?? '',
    emergencyContactName: patient.emergency_contact_name ?? '',
    emergencyContactRelationship: patient.emergency_contact_relationship ?? '',
    emergencyContactPhone: patient.emergency_contact_phone ?? '',
    administrativeNotes: patient.administrative_notes ?? '',
  };
}

export function validatePatientForm(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  const fullName = values.fullName.trim();
  if (!fullName) {
    errors.fullName = 'Informe o nome completo.';
  } else if (fullName.length > 200) {
    errors.fullName = 'O nome completo deve ter no máximo 200 caracteres.';
  }

  const today = todayIso();
  if (!values.birthDate) {
    errors.birthDate = 'Informe a data de nascimento.';
  } else if (values.birthDate > today) {
    errors.birthDate = 'A data de nascimento não pode estar no futuro.';
  }

  if (!values.phone.trim()) {
    errors.phone = 'Informe o telefone principal.';
  }

  if (values.cpf.trim() && !isValidCpf(normalizeCpf(values.cpf))) {
    errors.cpf = 'Informe um CPF válido.';
  }

  if (values.email.trim() && !EMAIL_PATTERN.test(values.email.trim())) {
    errors.email = 'Informe um e-mail válido.';
  }

  if (values.state.trim() && !STATE_PATTERN.test(values.state.trim())) {
    errors.state = 'Use a sigla de duas letras (ex.: BA).';
  }

  if (values.birthDate && values.birthDate <= today) {
    const age = patientAge(values.birthDate);
    if (age !== null && age < 18) {
      const complete = Boolean(
        values.guardianName.trim() &&
          values.guardianRelationship.trim() &&
          values.guardianPhone.trim(),
      );
      if (!complete) {
        errors.guardianName =
          'Paciente menor de idade exige responsável com nome, vínculo e telefone.';
      }
    }
  }

  const emergencyInformed = Boolean(
    values.emergencyContactName.trim() ||
      values.emergencyContactRelationship.trim() ||
      values.emergencyContactPhone.trim(),
  );
  if (
    emergencyInformed &&
    !(values.emergencyContactName.trim() && values.emergencyContactPhone.trim())
  ) {
    errors.emergencyContactName = 'Contato de emergência exige nome e telefone.';
  }

  return errors;
}

export function patientErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return 'Você não tem permissão para alterar este paciente.';
    }
    if (error.status === 404) {
      return 'Paciente não encontrado. Atualize a página.';
    }
    if (error.status === 409) {
      return 'Já existe um paciente com este CPF nesta clínica.';
    }
    if (error.status === 422) {
      return 'Não foi possível salvar o paciente. Verifique os campos e tente novamente.';
    }
    if (error.status === 429) {
      return error.retryAfter === undefined
        ? 'Muitas tentativas. Tente novamente em instantes.'
        : `Muitas tentativas. Tente novamente em ${error.retryAfter} segundos.`;
    }
  }
  return 'Não foi possível salvar o paciente. Tente novamente.';
}

function optional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function toPayload(values: FormValues): PatientCreateRequest {
  return {
    full_name: values.fullName.trim(),
    social_name: optional(values.socialName),
    birth_date: values.birthDate,
    cpf: optional(values.cpf) ? normalizeCpf(values.cpf) : null,
    phone: values.phone.trim(),
    phone_secondary: optional(values.phoneSecondary),
    email: optional(values.email),
    postal_code: optional(values.postalCode),
    street: optional(values.street),
    number: optional(values.number),
    complement: optional(values.complement),
    district: optional(values.district),
    city: optional(values.city),
    state: values.state.trim() ? values.state.trim().toUpperCase() : null,
    occupation: optional(values.occupation),
    nationality: optional(values.nationality),
    birthplace: optional(values.birthplace),
    guardian_name: optional(values.guardianName),
    guardian_relationship: optional(values.guardianRelationship),
    guardian_phone: optional(values.guardianPhone),
    emergency_contact_name: optional(values.emergencyContactName),
    emergency_contact_relationship: optional(values.emergencyContactRelationship),
    emergency_contact_phone: optional(values.emergencyContactPhone),
    administrative_notes: optional(values.administrativeNotes),
  };
}

function TextField({
  id,
  label,
  value,
  onChange,
  error,
  type = 'text',
  required = false,
  placeholder,
  autoComplete,
  maxLength,
  inputMode,
  className,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
  maxLength?: number;
  inputMode?: 'numeric' | 'text' | 'tel' | 'email';
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ''}`}>
      <label htmlFor={id} className="app-label">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        autoComplete={autoComplete}
        maxLength={maxLength}
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? `${id}-error` : undefined}
        className="app-field"
      />
      {error !== undefined && (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function TextAreaField({
  id,
  label,
  value,
  onChange,
  error,
  maxLength,
  rows = 3,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  maxLength?: number;
  rows?: number;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="app-label">
        {label}
      </label>
      <textarea
        id={id}
        name={id}
        value={value}
        rows={rows}
        maxLength={maxLength}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? `${id}-error` : undefined}
        className="app-field"
      />
      {error !== undefined && (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function PatientForm({
  clinicId,
  mode,
  patient,
}: {
  clinicId: string;
  mode: 'create' | 'edit';
  patient?: Patient;
}) {
  const router = useRouter();
  const [values, setValues] = useState<FormValues>(() => initialValues(patient));
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  useFocusFirstInvalid(fieldErrors, formRef);

  function update(field: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validatePatientForm(values);
    setFieldErrors(errors);
    setFormError(null);
    setSaved(false);
    if (Object.keys(errors).length > 0) {
      return;
    }

    const payload = toPayload(values);
    setPending(true);
    try {
      if (mode === 'create') {
        const created = await createPatient(clinicId, payload);
        router.push(`/clinics/${clinicId}/patients/${created.id}`);
      } else if (patient) {
        await updatePatient(clinicId, patient.id, payload);
        setSaved(true);
        router.refresh();
      }
    } catch (cause) {
      setFormError(patientErrorMessage(cause));
    } finally {
      setPending(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Identificação</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Nome, nascimento e telefone são obrigatórios.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id="patient-full-name"
            label="Nome completo"
            value={values.fullName}
            onChange={(value) => update('fullName', value)}
            error={fieldErrors.fullName}
            required
            maxLength={200}
            autoComplete="name"
          />
          <TextField
            id="patient-social-name"
            label="Nome social"
            value={values.socialName}
            onChange={(value) => update('socialName', value)}
            error={fieldErrors.socialName}
            maxLength={200}
          />
          <TextField
            id="patient-birth-date"
            label="Data de nascimento"
            type="date"
            value={values.birthDate}
            onChange={(value) => update('birthDate', value)}
            error={fieldErrors.birthDate}
            required
          />
          <TextField
            id="patient-cpf"
            label="CPF"
            value={values.cpf}
            onChange={(value) => update('cpf', value)}
            error={fieldErrors.cpf}
            placeholder="000.000.000-00"
            inputMode="numeric"
          />
        </div>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Contato</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Canais para confirmações e lembretes administrativos.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            id="patient-phone"
            label="Telefone principal"
            type="tel"
            value={values.phone}
            onChange={(value) => update('phone', value)}
            error={fieldErrors.phone}
            required
            maxLength={40}
            autoComplete="tel"
          />
          <TextField
            id="patient-phone-secondary"
            label="Telefone secundário"
            type="tel"
            value={values.phoneSecondary}
            onChange={(value) => update('phoneSecondary', value)}
            error={fieldErrors.phoneSecondary}
            maxLength={40}
          />
          <TextField
            id="patient-email"
            label="E-mail"
            type="email"
            value={values.email}
            onChange={(value) => update('email', value)}
            error={fieldErrors.email}
            maxLength={320}
            autoComplete="email"
          />
        </div>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Endereço</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Opcional, útil para correspondências.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <TextField
            id="patient-postal-code"
            label="CEP"
            value={values.postalCode}
            onChange={(value) => update('postalCode', value)}
            error={fieldErrors.postalCode}
            maxLength={20}
            inputMode="numeric"
          />
          <TextField
            id="patient-street"
            label="Logradouro"
            value={values.street}
            onChange={(value) => update('street', value)}
            error={fieldErrors.street}
            maxLength={200}
            className="lg:col-span-2"
          />
          <TextField
            id="patient-number"
            label="Número"
            value={values.number}
            onChange={(value) => update('number', value)}
            error={fieldErrors.number}
            maxLength={200}
          />
          <TextField
            id="patient-complement"
            label="Complemento"
            value={values.complement}
            onChange={(value) => update('complement', value)}
            error={fieldErrors.complement}
            maxLength={200}
          />
          <TextField
            id="patient-district"
            label="Bairro"
            value={values.district}
            onChange={(value) => update('district', value)}
            error={fieldErrors.district}
            maxLength={200}
          />
          <TextField
            id="patient-city"
            label="Cidade"
            value={values.city}
            onChange={(value) => update('city', value)}
            error={fieldErrors.city}
            maxLength={200}
          />
          <TextField
            id="patient-state"
            label="UF"
            value={values.state}
            onChange={(value) => update('state', value.toUpperCase())}
            error={fieldErrors.state}
            maxLength={2}
            placeholder="BA"
          />
        </div>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Responsável legal</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Obrigatório para pacientes menores de 18 anos.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            id="patient-guardian-name"
            label="Nome do responsável"
            value={values.guardianName}
            onChange={(value) => update('guardianName', value)}
            error={fieldErrors.guardianName}
            maxLength={200}
          />
          <TextField
            id="patient-guardian-relationship"
            label="Vínculo do responsável"
            value={values.guardianRelationship}
            onChange={(value) => update('guardianRelationship', value)}
            error={fieldErrors.guardianRelationship}
            maxLength={200}
          />
          <TextField
            id="patient-guardian-phone"
            label="Telefone do responsável"
            type="tel"
            value={values.guardianPhone}
            onChange={(value) => update('guardianPhone', value)}
            error={fieldErrors.guardianPhone}
            maxLength={40}
          />
        </div>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Contato de emergência</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Quando informado, exige nome e telefone.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            id="patient-emergency-name"
            label="Nome do contato de emergência"
            value={values.emergencyContactName}
            onChange={(value) => update('emergencyContactName', value)}
            error={fieldErrors.emergencyContactName}
            maxLength={200}
          />
          <TextField
            id="patient-emergency-relationship"
            label="Vínculo do contato de emergência"
            value={values.emergencyContactRelationship}
            onChange={(value) => update('emergencyContactRelationship', value)}
            error={fieldErrors.emergencyContactRelationship}
            maxLength={200}
          />
          <TextField
            id="patient-emergency-phone"
            label="Telefone do contato de emergência"
            type="tel"
            value={values.emergencyContactPhone}
            onChange={(value) => update('emergencyContactPhone', value)}
            error={fieldErrors.emergencyContactPhone}
            maxLength={40}
          />
        </div>
      </section>

      <section className="app-panel flex flex-col gap-4">
        <div>
          <h2 className="font-semibold text-foreground">Informações adicionais</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Dados complementares do cadastro administrativo.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            id="patient-occupation"
            label="Ocupação"
            value={values.occupation}
            onChange={(value) => update('occupation', value)}
            error={fieldErrors.occupation}
            maxLength={200}
          />
          <TextField
            id="patient-nationality"
            label="Nacionalidade"
            value={values.nationality}
            onChange={(value) => update('nationality', value)}
            error={fieldErrors.nationality}
            maxLength={200}
          />
          <TextField
            id="patient-birthplace"
            label="Naturalidade"
            value={values.birthplace}
            onChange={(value) => update('birthplace', value)}
            error={fieldErrors.birthplace}
            maxLength={200}
          />
        </div>
        <TextAreaField
          id="patient-notes"
          label="Observações administrativas"
          value={values.administrativeNotes}
          onChange={(value) => update('administrativeNotes', value)}
          error={fieldErrors.administrativeNotes}
          maxLength={2000}
        />
      </section>

      {formError !== null && <Feedback tone="error">{formError}</Feedback>}
      {saved && <Feedback tone="success">Dados do paciente atualizados.</Feedback>}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending}>
          {mode === 'create'
            ? pending
              ? 'Cadastrando...'
              : 'Cadastrar paciente'
            : pending
              ? 'Salvando...'
              : 'Salvar alterações'}
        </Button>
        <Button asChild variant="ghost">
          <Link href={`/clinics/${clinicId}/patients`}>Cancelar</Link>
        </Button>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CircleAlert aria-hidden="true" className="size-3.5" />
          CPF, nome e dados clínicos não aparecem em logs.
        </p>
      </div>
    </form>
  );
}
