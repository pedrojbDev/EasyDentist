export function clinicToday(timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
  return `${value('year')}-${value('month')}-${value('day')}`;
}

export function addLocalDays(value: string, amount: number): string {
  const date = new Date(`${value}T12:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

export function addLocalMinutes(value: string, minutes: number): string {
  const normalized = value.length === 16 ? `${value}:00` : value;
  const date = new Date(`${normalized}Z`);
  date.setUTCMinutes(date.getUTCMinutes() + minutes);
  return date.toISOString().slice(0, 16);
}

export function localWeekday(value: string): number {
  return new Date(`${value}T12:00:00.000Z`).getUTCDay();
}

export function startOfClinicWeek(value: string): string {
  const mondayOffset = (localWeekday(value) + 6) % 7;
  return addLocalDays(value, -mondayOffset);
}

export function clinicLocalInstant(value: string, timeZone: string): Date {
  const [datePart, timePart] = value.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  const [hour = 0, minute = 0, second = 0] = (timePart ?? '00:00:00').split(':').map(Number);
  const desired = Date.UTC(year, month - 1, day, hour, minute, second);
  let guess = desired;
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const parts = formatter.formatToParts(new Date(guess));
    const valueFor = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
    const represented = Date.UTC(
      valueFor('year'),
      valueFor('month') - 1,
      valueFor('day'),
      valueFor('hour'),
      valueFor('minute'),
      valueFor('second'),
    );
    const difference = desired - represented;
    if (difference === 0) return new Date(guess);
    guess += difference;
  }
  throw new Error('Não foi possível converter a data no fuso da clínica.');
}

export function clinicLocalDateTimeInput(value: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

export function clinicLocalDate(value: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function formatClinicTime(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

export function formatClinicDate(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    timeZone,
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
  }).format(clinicLocalInstant(value, timeZone));
}

export function clinicDateRange(value: string, view: 'day' | 'week', timeZone: string) {
  const startsOn = view === 'week' ? startOfClinicWeek(value) : value;
  const days = view === 'week' ? 7 : 1;
  return {
    starts_at: clinicLocalInstant(startsOn, timeZone).toISOString(),
    ends_at: clinicLocalInstant(addLocalDays(startsOn, days), timeZone).toISOString(),
    days: Array.from({ length: days }, (_, index) => addLocalDays(startsOn, index)),
  };
}
