"""Immutable catalog of the ``cfo_2026_v1`` anamnesis and dental inventory.

The clinical wording is original pt-BR writing structured after Anexo 1 of the
CFO 2026 prontuário manual, which is used as a reference only: no text from the
manual was copied. The catalog is versioned by the ``cfo_2026_v1`` identifier;
section and question IDs are stable and are never reused with another meaning.

Consumers import section and question IDs from here and must not mutate the
catalog. Any content change requires a new template identifier.

Each question declares how it is answered (``AnswerType``) and, when a textual
complement is accepted, a ``details_prompt``. ``details_required`` marks the
complement as mandatory for answers that describe a positive finding (``YES``
for ``YES_NO_UNKNOWN`` or a selected option for ``SINGLE_CHOICE``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class YesNoUnknown(StrEnum):
    """Closed vocabulary for ``YES_NO_UNKNOWN`` answers."""

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class AnswerType(StrEnum):
    """Shape of the answer expected by a catalog question."""

    YES_NO_UNKNOWN = "YES_NO_UNKNOWN"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class Option:
    """Alternative of a ``SINGLE_CHOICE`` question, with a stable ID."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class Question:
    """Immutable question with a stable ID and a typed answer."""

    id: str
    prompt: str
    answer_type: AnswerType
    options: tuple[Option, ...] = ()
    details_prompt: str | None = None
    details_required: bool = False


@dataclass(frozen=True, slots=True)
class Section:
    """Immutable catalog section with a stable ID and a deterministic order."""

    id: str
    title: str
    questions: tuple[Question, ...]


def _yes_no_unknown(
    question_id: str,
    prompt: str,
    *,
    details_prompt: str | None = None,
    details_required: bool = False,
) -> Question:
    return Question(
        id=question_id,
        prompt=prompt,
        answer_type=AnswerType.YES_NO_UNKNOWN,
        details_prompt=details_prompt,
        details_required=details_required,
    )


def _single_choice(
    question_id: str,
    prompt: str,
    options: tuple[Option, ...],
) -> Question:
    return Question(
        id=question_id,
        prompt=prompt,
        answer_type=AnswerType.SINGLE_CHOICE,
        options=options,
    )


def _text(question_id: str, prompt: str) -> Question:
    return Question(id=question_id, prompt=prompt, answer_type=AnswerType.TEXT)


TEMPLATE_ID: Final[str] = "cfo_2026_v1"
TEMPLATE_LABEL: Final[str] = "Anamnese e inventário odontológico — CFO 2026 (v1)"

SECTIONS: Final[tuple[Section, ...]] = (
    Section(
        id="chief_complaint",
        title="Queixa principal",
        questions=(
            _text(
                "chief_complaint.description",
                "Descreva a queixa principal relatada pelo paciente, com as palavras "
                "utilizadas por ele.",
            ),
            _text(
                "chief_complaint.duration",
                "Há quanto tempo a queixa principal teve início?",
            ),
            _text(
                "chief_complaint.evolution",
                "Como a queixa evoluiu desde o início, considerando intensidade, "
                "frequência e fatores de melhora ou piora?",
            ),
        ),
    ),
    Section(
        id="current_history",
        title="História atual",
        questions=(
            _yes_no_unknown(
                "current_history.previous_treatment",
                "Já realizou algum tratamento para a queixa atual?",
                details_prompt="Descreva os tratamentos realizados e o resultado obtido.",
            ),
            _yes_no_unknown(
                "current_history.current_medication",
                "Está usando algum medicamento para a queixa atual?",
                details_prompt="Informe os medicamentos, as doses e a frequência de uso.",
            ),
            _yes_no_unknown(
                "current_history.associated_symptoms",
                "Apresenta outros sintomas associados, como febre, inchaço ou "
                "dificuldade para mastigar ou engolir?",
                details_prompt="Descreva os sintomas associados.",
            ),
            _text(
                "current_history.notes",
                "Outras informações relevantes sobre a história atual.",
            ),
        ),
    ),
    Section(
        id="medical_history",
        title="História médica",
        questions=(
            _yes_no_unknown(
                "medical_history.diagnoses",
                "Possui alguma doença ou condição médica diagnosticada?",
                details_prompt="Liste as doenças ou condições diagnosticadas.",
                details_required=True,
            ),
            _yes_no_unknown(
                "medical_history.hospitalization",
                "Foi internado ou submetido a procedimento hospitalar nos últimos doze meses?",
                details_prompt="Informe o motivo e a data aproximada.",
            ),
            _yes_no_unknown(
                "medical_history.continuous_follow_up",
                "Está em acompanhamento médico contínuo?",
                details_prompt="Informe o especialista e o motivo do acompanhamento.",
            ),
            _text(
                "medical_history.notes",
                "Outras informações relevantes sobre a história médica.",
            ),
        ),
    ),
    Section(
        id="dental_history",
        title="História odontológica",
        questions=(
            _single_choice(
                "dental_history.last_visit",
                "Quando foi a última consulta odontológica?",
                options=(
                    Option("less_than_six_months", "Há menos de seis meses"),
                    Option("six_to_twelve_months", "Entre seis e doze meses"),
                    Option("one_to_five_years", "Entre um e cinco anos"),
                    Option("more_than_five_years", "Há mais de cinco anos"),
                    Option("never", "Nunca foi ao dentista"),
                ),
            ),
            _yes_no_unknown(
                "dental_history.previous_treatment",
                "Já realizou tratamento odontológico?",
                details_prompt="Descreva os tratamentos odontológicos realizados.",
            ),
            _yes_no_unknown(
                "dental_history.treatment_anxiety",
                "Sente medo ou ansiedade em consultas odontológicas?",
                details_prompt="Descreva a experiência que gera desconforto.",
            ),
            _text(
                "dental_history.notes",
                "Outras informações relevantes sobre a história odontológica.",
            ),
        ),
    ),
    Section(
        id="family_history",
        title="História familiar",
        questions=(
            _yes_no_unknown(
                "family_history.conditions",
                "Possui familiares com doenças de relevância clínica ou odontológica?",
                details_prompt="Informe as condições e o grau de parentesco.",
                details_required=True,
            ),
            _text(
                "family_history.notes",
                "Outras informações relevantes sobre a história familiar.",
            ),
        ),
    ),
    Section(
        id="social_history",
        title="História social",
        questions=(
            _yes_no_unknown(
                "social_history.occupational_exposure",
                "Sua ocupação ou rotina envolve exposição a agentes que possam "
                "afetar a saúde bucal?",
                details_prompt="Descreva a exposição e a frequência.",
            ),
            _yes_no_unknown(
                "social_history.care_access",
                "Enfrenta dificuldade para acessar atendimento odontológico?",
                details_prompt="Descreva a dificuldade relatada.",
            ),
            _text(
                "social_history.notes",
                "Outras informações relevantes sobre a história social.",
            ),
        ),
    ),
    Section(
        id="digestive_conditions",
        title="Condições digestivas",
        questions=(
            _yes_no_unknown(
                "digestive_conditions.diagnosis",
                "Possui alguma condição digestiva diagnosticada, como refluxo, "
                "gastrite ou doença intestinal?",
                details_prompt="Informe a condição diagnosticada e o tratamento em curso.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="hepatic_conditions",
        title="Condições hepáticas",
        questions=(
            _yes_no_unknown(
                "hepatic_conditions.diagnosis",
                "Possui alguma condição hepática diagnosticada, como hepatite ou esteatose?",
                details_prompt="Informe a condição diagnosticada e o acompanhamento atual.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="cardiovascular_conditions",
        title="Condições cardiovasculares",
        questions=(
            _yes_no_unknown(
                "cardiovascular_conditions.diagnosis",
                "Possui alguma condição cardiovascular diagnosticada, como "
                "hipertensão, arritmia, infarto prévio ou marca-passo?",
                details_prompt="Informe a condição diagnosticada e o tratamento em curso.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="respiratory_conditions",
        title="Condições respiratórias",
        questions=(
            _yes_no_unknown(
                "respiratory_conditions.diagnosis",
                "Possui alguma condição respiratória diagnosticada, como asma, "
                "bronquite ou apneia do sono?",
                details_prompt="Informe a condição diagnosticada e o tratamento em curso.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="renal_conditions",
        title="Condições renais",
        questions=(
            _yes_no_unknown(
                "renal_conditions.diagnosis",
                "Possui alguma condição renal diagnosticada, como insuficiência "
                "renal ou cálculo urinário?",
                details_prompt="Informe a condição diagnosticada e o acompanhamento atual.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="motor_conditions",
        title="Condições motoras",
        questions=(
            _yes_no_unknown(
                "motor_conditions.diagnosis",
                "Possui alguma condição motora ou de mobilidade diagnosticada?",
                details_prompt="Informe a condição diagnosticada e as limitações relatadas.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="infectious_conditions",
        title="Condições infecciosas",
        questions=(
            _yes_no_unknown(
                "infectious_conditions.diagnosis",
                "Possui ou já teve alguma doença infecciosa de relevância clínica, "
                "como hepatite, tuberculose ou HIV?",
                details_prompt="Informe a doença, o período e o acompanhamento atual.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="endocrine_metabolic_conditions",
        title="Condições endócrinas e metabólicas",
        questions=(
            _yes_no_unknown(
                "endocrine_metabolic_conditions.diagnosis",
                "Possui alguma condição endócrina ou metabólica diagnosticada, "
                "como diabetes, doença da tireoide ou dislipidemia?",
                details_prompt="Informe a condição diagnosticada e o tratamento em curso.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="allergies",
        title="Alergias",
        questions=(
            _yes_no_unknown(
                "allergies.known_allergy",
                "Possui alergia conhecida a medicamentos, materiais odontológicos, "
                "alimentos ou outras substâncias?",
                details_prompt="Informe as substâncias e as reações apresentadas.",
                details_required=True,
            ),
            _yes_no_unknown(
                "allergies.emergency_care",
                "Já precisou de atendimento de urgência por causa de uma reação alérgica?",
                details_prompt="Descreva a reação e o atendimento recebido.",
            ),
        ),
    ),
    Section(
        id="anesthesia",
        title="Anestesia",
        questions=(
            _yes_no_unknown(
                "anesthesia.previous_exposure",
                "Já recebeu anestesia local ou geral?",
                details_prompt="Informe o tipo de anestesia e o contexto.",
            ),
            _yes_no_unknown(
                "anesthesia.adverse_reaction",
                "Já apresentou alguma reação adversa à anestesia?",
                details_prompt="Descreva a reação apresentada.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="bleeding",
        title="Sangramento",
        questions=(
            _yes_no_unknown(
                "bleeding.diagnosed_disorder",
                "Possui diagnóstico de distúrbio de coagulação ou de sangramento?",
                details_prompt="Informe o diagnóstico e o acompanhamento atual.",
                details_required=True,
            ),
            _yes_no_unknown(
                "bleeding.prolonged_bleeding",
                "Costuma apresentar sangramento prolongado após ferimentos ou procedimentos?",
                details_prompt="Descreva as situações observadas.",
            ),
        ),
    ),
    Section(
        id="healing",
        title="Cicatrização",
        questions=(
            _yes_no_unknown(
                "healing.difficulty",
                "Já teve dificuldade de cicatrização após ferimentos, cirurgias ou "
                "procedimentos odontológicos?",
                details_prompt="Descreva a situação e o tempo de cicatrização.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="surgeries",
        title="Cirurgias",
        questions=(
            _yes_no_unknown(
                "surgeries.history",
                "Já foi submetido a alguma cirurgia?",
                details_prompt="Informe quais cirurgias foram realizadas e quando.",
                details_required=True,
            ),
            _yes_no_unknown(
                "surgeries.recent",
                "Realizou alguma cirurgia nos últimos doze meses?",
                details_prompt="Informe a cirurgia e a data aproximada.",
            ),
        ),
    ),
    Section(
        id="pregnancy",
        title="Gestação",
        questions=(
            _single_choice(
                "pregnancy.status",
                "Qual situação se aplica atualmente?",
                options=(
                    Option("not_applicable", "Não se aplica"),
                    Option("not_pregnant", "Não gestante"),
                    Option("pregnant", "Gestante"),
                    Option("breastfeeding", "Em amamentação"),
                    Option("unknown", "Não sabe informar"),
                ),
            ),
            _text(
                "pregnancy.trimester",
                "Se gestante, informe o trimestre gestacional e as orientações médicas recebidas.",
            ),
        ),
    ),
    Section(
        id="neoplasms",
        title="Neoplasias",
        questions=(
            _yes_no_unknown(
                "neoplasms.history",
                "Possui ou já teve algum tipo de neoplasia?",
                details_prompt="Informe o tipo, o local e o período do tratamento.",
                details_required=True,
            ),
            _yes_no_unknown(
                "neoplasms.active_treatment",
                "Está em tratamento oncológico atualmente, como quimioterapia, "
                "radioterapia ou imunoterapia?",
                details_prompt="Informe o tratamento em curso.",
            ),
        ),
    ),
    Section(
        id="psychological_conditions",
        title="Condições psicológicas",
        questions=(
            _yes_no_unknown(
                "psychological_conditions.diagnosis",
                "Possui alguma condição psicológica ou psiquiátrica diagnosticada?",
                details_prompt="Informe a condição diagnosticada e o acompanhamento atual.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="disabilities",
        title="Deficiências",
        questions=(
            _yes_no_unknown(
                "disabilities.presence",
                "Possui alguma deficiência ou necessidade específica de acessibilidade?",
                details_prompt="Descreva a deficiência e as adaptações necessárias.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="medications",
        title="Medicamentos",
        questions=(
            _yes_no_unknown(
                "medications.continuous_use",
                "Faz uso contínuo de algum medicamento?",
                details_prompt="Informe os medicamentos, as doses e a frequência de uso.",
                details_required=True,
            ),
            _yes_no_unknown(
                "medications.anticoagulants",
                "Usa anticoagulante ou antiagregante plaquetário?",
                details_prompt="Informe o medicamento e a dose.",
                details_required=True,
            ),
        ),
    ),
    Section(
        id="habits",
        title="Hábitos",
        questions=(
            _single_choice(
                "habits.smoking",
                "Qual é a sua situação em relação ao tabagismo?",
                options=(
                    Option("never", "Nunca fumou"),
                    Option("former", "Ex-fumante"),
                    Option("current", "Fumante atual"),
                ),
            ),
            _single_choice(
                "habits.alcohol",
                "Com que frequência consome bebidas alcoólicas?",
                options=(
                    Option("never", "Nunca"),
                    Option("occasionally", "Ocasionalmente"),
                    Option("weekly", "Semanalmente"),
                    Option("daily", "Diariamente"),
                ),
            ),
            _yes_no_unknown(
                "habits.other_substances",
                "Usa outras substâncias, como produtos de tabaco sem fumaça ou drogas ilícitas?",
                details_prompt="Descreva as substâncias e a frequência de uso.",
            ),
        ),
    ),
    Section(
        id="dental_inventory",
        title="Inventário odontológico",
        questions=(
            _single_choice(
                "dental_inventory.hygiene",
                "Com que frequência escova os dentes?",
                options=(
                    Option("twice_or_more_daily", "Duas vezes ou mais por dia"),
                    Option("once_daily", "Uma vez por dia"),
                    Option("occasionally", "Algumas vezes por semana"),
                    Option("never", "Não escova"),
                ),
            ),
            _single_choice(
                "dental_inventory.flossing",
                "Com que frequência usa fio dental?",
                options=(
                    Option("daily", "Diariamente"),
                    Option("sometimes", "Algumas vezes por semana"),
                    Option("never", "Nunca"),
                ),
            ),
            _yes_no_unknown(
                "dental_inventory.pain",
                "Sente dor nos dentes, nas gengivas ou na articulação "
                "temporomandibular atualmente?",
                details_prompt="Descreva a localização e as características da dor.",
                details_required=True,
            ),
            _yes_no_unknown(
                "dental_inventory.bleeding",
                "As gengivas sangram durante a escovação ou espontaneamente?",
                details_prompt="Descreva quando o sangramento ocorre.",
            ),
            _yes_no_unknown(
                "dental_inventory.mobility",
                "Percebe dentes moles ou com mobilidade?",
                details_prompt="Informe quais dentes parecem móveis.",
            ),
            _yes_no_unknown(
                "dental_inventory.halitosis",
                "Percebe mau hálito com frequência ou já recebeu esse relato?",
                details_prompt="Descreva a frequência e o contexto.",
            ),
            _yes_no_unknown(
                "dental_inventory.xerostomia",
                "Sente a boca seca com frequência?",
                details_prompt="Descreva a frequência e os fatores associados.",
            ),
            _yes_no_unknown(
                "dental_inventory.atm",
                "Sente dor, estalido ou dificuldade para abrir ou fechar a boca?",
                details_prompt="Descreva o sintoma e quando ele ocorre.",
                details_required=True,
            ),
            _yes_no_unknown(
                "dental_inventory.sensitivity",
                "Sente sensibilidade dentária ao frio, ao calor ou a alimentos doces?",
                details_prompt="Informe os dentes e os estímulos que desencadeiam a sensibilidade.",
            ),
            _yes_no_unknown(
                "dental_inventory.lesions",
                "Possui lesão, ferida ou alteração na boca que não cicatrizou?",
                details_prompt="Descreva a lesão, a localização e o tempo de evolução.",
                details_required=True,
            ),
            _yes_no_unknown(
                "dental_inventory.bruxism",
                "Aperta ou range os dentes, inclusive durante o sono?",
                details_prompt="Descreva a frequência e os sintomas associados.",
            ),
            _single_choice(
                "dental_inventory.diet",
                "Com que frequência consome alimentos ou bebidas açucaradas entre as refeições?",
                options=(
                    Option("rarely", "Raramente"),
                    Option("sometimes", "Algumas vezes por semana"),
                    Option("daily", "Diariamente"),
                    Option("several_times_daily", "Várias vezes ao dia"),
                ),
            ),
            _yes_no_unknown(
                "dental_inventory.endodontics",
                "Já realizou tratamento de canal (endodontia)?",
                details_prompt="Informe quais dentes foram tratados.",
            ),
            _yes_no_unknown(
                "dental_inventory.prostheses",
                "Usa ou já usou próteses, coroas ou implantes?",
                details_prompt="Descreva os elementos e a data aproximada.",
            ),
            _yes_no_unknown(
                "dental_inventory.previous_surgeries",
                "Já realizou cirurgias odontológicas, como extrações ou enxertos?",
                details_prompt="Descreva as cirurgias realizadas e a data aproximada.",
            ),
        ),
    ),
)
