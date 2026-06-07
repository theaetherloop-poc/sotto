import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;

// Sotto is an ambient observer of a two-party consult. The local participant joins as either
// "doctor" or "patient" (identity = role), and the Sotto agent auto-dispatches to the room
// (it registers with no agent_name), so no explicit agent dispatch is stamped here.
const ALLOWED_ROLES = new Set(['doctor', 'patient']);

// don't cache the results
export const revalidate = 0;

export async function POST(req: Request) {
  // POC NOTE: this route mints LiveKit room tokens without authentication. That is
  // intentional for the shareable demo deployment of Sotto. Any traffic to it consumes
  // LiveKit Inference credits on the configured project. Before opening this URL to a
  // broader audience, gate it (shared secret, OAuth, etc.).
  if (process.env.NODE_ENV === 'production') {
    console.warn('[sotto] /api/token is open. POC demo only — not for real PHI traffic.');
  }

  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }
    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }
    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    const body = await req.json().catch(() => ({}));
    const role = ALLOWED_ROLES.has(body?.role) ? (body.role as string) : 'doctor';
    const roomName =
      typeof body?.room === 'string' && body.room.trim()
        ? body.room.trim()
        : `sotto-${Math.floor(Math.random() * 1_000_000)}`;

    // Identity must be UNIQUE per connection or LiveKit kicks duplicates (which, with
    // React StrictMode double-mounting in dev, drops the session). The role is carried as
    // the identity prefix (`doctor-xxxxxx`); the agent derives the speaker label from it.
    const suffix = Math.random().toString(36).slice(2, 8);
    const participantToken = await createParticipantToken(
      { identity: `${role}-${suffix}`, name: role.charAt(0).toUpperCase() + role.slice(1) },
      roomName
    );

    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName: role,
      participantToken,
    };
    return NextResponse.json(data, { headers: new Headers({ 'Cache-Control': 'no-store' }) });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}

function createParticipantToken(userInfo: AccessTokenOptions, roomName: string): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '60m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);
  return at.toJwt();
}
