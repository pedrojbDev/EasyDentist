export function normalizeCpf(value: string): string {
  return value.replace(/\D/g, '');
}

export function isValidCpf(digits: string): boolean {
  if (digits.length !== 11 || !/^\d{11}$/.test(digits)) {
    return false;
  }
  if (/^(\d)\1{10}$/.test(digits)) {
    return false;
  }
  const numbers = digits.split('').map(Number);
  for (const length of [9, 10]) {
    let total = 0;
    for (let index = 0; index < length; index += 1) {
      total += numbers[index] * (length + 1 - index);
    }
    let checkDigit = (total * 10) % 11;
    if (checkDigit === 10) {
      checkDigit = 0;
    }
    if (checkDigit !== numbers[length]) {
      return false;
    }
  }
  return true;
}

export function formatCpf(digits: string): string {
  if (digits.length !== 11) {
    return digits;
  }
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}
