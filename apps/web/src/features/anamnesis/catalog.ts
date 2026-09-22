import rawCatalog from './catalog.json';

export type AnamnesisAnswerKind = 'YES_NO_UNKNOWN' | 'SINGLE_CHOICE' | 'TEXT';

export type CatalogOption = {
  id: string;
  label: string;
};

export type CatalogQuestion = {
  id: string;
  prompt: string;
  answer_type: AnamnesisAnswerKind;
  options: CatalogOption[];
  details_prompt: string | null;
  details_required: boolean;
};

export type CatalogSection = {
  id: string;
  title: string;
  questions: CatalogQuestion[];
};

export const TEMPLATE_ID: string = rawCatalog.template_id;
export const TEMPLATE_LABEL: string = rawCatalog.template_label;
export const SECTIONS: CatalogSection[] = rawCatalog.sections as CatalogSection[];

export const TOTAL_QUESTIONS = SECTIONS.reduce(
  (total, section) => total + section.questions.length,
  0,
);

/** Short payload field of a catalog question (the part after the dot). */
export function questionShortName(questionId: string): string {
  const [, short] = questionId.split('.');
  return short ?? questionId;
}

export function sectionAnchorId(sectionId: string): string {
  return `anamnesis-section-${sectionId}`;
}
