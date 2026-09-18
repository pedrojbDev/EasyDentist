import { apiMutation, apiMutationVoid } from '@/lib/api/client';
import type { components } from '@/lib/api/generated/schema';

export type User = components['schemas']['UserResponse'];
export type LoginResponse = components['schemas']['LoginResponse'];

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiMutation<LoginResponse>(
    'POST',
    '/api/v1/auth/login',
    { email, password },
    { skipAuthRedirect: true },
  );
}

export async function logout(): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/auth/logout');
}

export async function logoutAll(): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/auth/logout-all');
}

export async function forgotPassword(email: string): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/auth/password/forgot', { email });
}

export async function resetPassword(token: string, password: string): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/auth/password/reset', { token, password });
}

export async function verifyEmail(token: string): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/auth/email-verification/confirm', { token });
}

export async function acceptInvitation(token: string, password?: string): Promise<void> {
  await apiMutationVoid('POST', '/api/v1/invitations/accept', {
    token,
    ...(password !== undefined ? { password } : {}),
  });
}
