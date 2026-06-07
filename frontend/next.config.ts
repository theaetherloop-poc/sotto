import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // LiveKit's useSession() connects/disconnects the Room directly in effects (it does not use
  // the library's useSequentialRoomConnectDisconnect guard). React StrictMode's dev-only
  // mount→unmount→remount therefore tears the room down right after it connects. Sotto also
  // needs a STABLE room name (doctor + patient share it), which breaks useSession's
  // "refetch a brand-new room on disconnect" assumption. Disabling StrictMode keeps the
  // ambient consult connection stable in dev. (StrictMode double-invoke does not exist in prod.)
  reactStrictMode: false,
};

export default nextConfig;
