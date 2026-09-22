const MAILPIT_API_URL = process.env.MAILPIT_API_URL ?? 'http://127.0.0.1:8025';
const TOKEN_PATTERN = /#token=([A-Za-z0-9_-]{20,})/;
const POLL_INTERVAL_MS = 500;
const POLL_TIMEOUT_MS = 15_000;

type MailpitAddress = { Address?: string };
type MailpitMessage = {
  ID: string;
  To?: MailpitAddress[];
  Created?: string;
};

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function listMessages(): Promise<MailpitMessage[]> {
  const response = await fetch(`${MAILPIT_API_URL}/api/v1/messages?limit=50`);
  if (!response.ok) {
    throw new Error('Mailpit message list is unavailable');
  }
  const payload = (await response.json()) as { messages?: MailpitMessage[] };
  return payload.messages ?? [];
}

async function decodedMessage(id: string): Promise<string> {
  const response = await fetch(`${MAILPIT_API_URL}/api/v1/message/${id}`);
  if (!response.ok) {
    throw new Error('Mailpit did not return the message');
  }
  const payload = (await response.json()) as { Text?: string; HTML?: string };
  return `${payload.Text ?? ''}\n${payload.HTML ?? ''}`;
}

/**
 * Resolves the action token for the newest message sent to `email` after
 * `after`. The message body never leaves this helper: only the fragment token
 * is returned, so email contents are not printed by the suite.
 */
export async function findToken(email: string, after: Date): Promise<string> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const messages = await listMessages();
    const match = messages.find(
      (message) =>
        (message.To ?? []).some(
          (recipient) => recipient.Address?.toLowerCase() === email.toLowerCase(),
        ) &&
        message.Created !== undefined &&
        new Date(message.Created).getTime() >= after.getTime() - 1_000,
    );
    if (match) {
      const token = TOKEN_PATTERN.exec(await decodedMessage(match.ID))?.[1];
      if (token !== undefined) {
        return token;
      }
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error(`No Mailpit message with a token for ${email} was found`);
}
