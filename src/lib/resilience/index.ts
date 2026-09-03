// Vendored from cubiczan-resilience (typescript/src). No npm registry available,
// so the needed primitives are copied here verbatim. Keep in sync upstream.
export {
  ResilienceError,
  isResilienceError,
  type ResilienceErrorKind,
  type ResilienceErrorOptions,
} from "./errors";

export { withTimeout } from "./timeout";

export { retry, computeBackoff, type RetryOptions } from "./retry";

export {
  safeFetch,
  type SafeFetchOptions,
  type AllowlistHook,
} from "./safeFetch";

export {
  SlidingWindowRateLimiter,
  type RateLimitOptions,
  type RateLimitResult,
} from "./rateLimit";

export {
  requireAuth,
  requireAuthResponse,
  type AuthResult,
  type RequireAuthOptions,
} from "./auth";
