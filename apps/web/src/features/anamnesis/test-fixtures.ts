import { SECTIONS, questionShortName } from './catalog';
import type { Anamnesis, AnamnesisPayload, ProfessionalProfile } from './api';

export function makeAnamnesis(overrides: Partial<Anamnesis> = {}): Anamnesis {
  return {
    id: 'a1',
    clinic_id: 'c1',
    patient_id: 'p1',
    status: 'DRAFT',
    version_number: null,
    template: 'cfo_2026_v1',
    payload: {},
    base_version_id: null,
    author_user_id: 'u1',
    author_professional_name: null,
    author_cro_number: null,
    author_cro_state: null,
    finalized_at: null,
    created_at: '2026-09-22T12:00:00Z',
    updated_at: '2026-09-22T12:00:00Z',
    ...overrides,
  };
}

export function makeFinal(version: number, overrides: Partial<Anamnesis> = {}): Anamnesis {
  return makeAnamnesis({
    id: `final-${version}`,
    status: 'FINAL',
    version_number: version,
    author_professional_name: 'Dra. Ana Souza',
    author_cro_number: '12345',
    author_cro_state: 'BA',
    finalized_at: '2026-09-22T13:00:00Z',
    ...overrides,
  });
}

export function makeProfile(overrides: Partial<ProfessionalProfile> = {}): ProfessionalProfile {
  return {
    professional_name: 'Dra. Ana Souza',
    cro_number: '12345',
    cro_state: 'BA',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

/** Complete payload accepted by finalization, built from the real catalog. */
export function completePayload(): AnamnesisPayload {
  const payload: Record<string, Record<string, Record<string, string>>> = {};
  for (const section of SECTIONS) {
    const answers: Record<string, Record<string, string>> = {};
    for (const question of section.questions) {
      const short = questionShortName(question.id);
      if (question.answer_type === 'TEXT') {
        answers[short] = { text: `Resposta ${question.id}` };
      } else if (question.answer_type === 'YES_NO_UNKNOWN') {
        answers[short] = { value: 'NO' };
      } else {
        answers[short] = { value: question.options[0]?.id ?? '' };
      }
    }
    payload[section.id] = answers;
  }
  return payload as unknown as AnamnesisPayload;
}
