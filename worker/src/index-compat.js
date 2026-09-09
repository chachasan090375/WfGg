// WFGG_API_ENTRY_COMPAT_V1
// Runtime behavior remains delegated to the canonical worker/src/index.js.
// The named export below only preserves the legacy Durable Object class required by Cloudflare.

import app from './index.js';
export { LastWarUserContainer } from './lastwar-user-container-compat.js';

export default app;
