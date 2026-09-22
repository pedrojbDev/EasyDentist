import { describe, expect, it } from 'vitest';

import {
  SECTIONS,
  TEMPLATE_ID,
  TOTAL_QUESTIONS,
  questionShortName,
  sectionAnchorId,
} from './catalog';

describe('anamnesis catalog', () => {
  it('keeps the versioned template identifier', () => {
    expect(TEMPLATE_ID).toBe('cfo_2026_v1');
  });

  it('covers every approved topic with unique stable IDs', () => {
    expect(SECTIONS.length).toBeGreaterThanOrEqual(20);
    const questionIds = SECTIONS.flatMap((section) =>
      section.questions.map((question) => question.id),
    );
    expect(new Set(questionIds).size).toBe(questionIds.length);
    expect(TOTAL_QUESTIONS).toBe(questionIds.length);
    expect(questionIds).toContain('allergies.known_allergy');
    expect(questionIds).toContain('dental_inventory.hygiene');
    expect(questionIds).toContain('pregnancy.status');
  });

  it('keeps short payload names unique inside each section', () => {
    for (const section of SECTIONS) {
      const shortNames = section.questions.map((question) => questionShortName(question.id));
      expect(new Set(shortNames).size).toBe(shortNames.length);
    }
  });

  it('builds stable anchor identifiers', () => {
    expect(sectionAnchorId('chief_complaint')).toBe('anamnesis-section-chief_complaint');
  });
});
