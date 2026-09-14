import crypto from 'crypto';
import express from 'express';

// Legacy development-only server. No baked-in secret is used: without an
// explicit JWT_SECRET_KEY the server falls back to a random per-process key so
// tokens are never signed with a predictable value.
const JWT_SECRET = process.env.JWT_SECRET_KEY || crypto.randomBytes(32).toString('hex');
const JWT_ALGORITHM = process.env.JWT_ALGORITHM || 'HS256';
const TOKEN_EXPIRY_SECONDS = parseInt(process.env.ACCESS_TOKEN_EXPIRE_MINUTES || '60', 10) * 60;

export interface TokenPayload {
  sub: string;
  role: 'clinician' | 'admin' | 'investigator' | 'auditor';
  iat: number;
  exp: number;
}

export interface AuthenticatedUser {
  username: string;
  role: 'clinician' | 'admin' | 'investigator' | 'auditor';
}

// In-memory user store with hashed passwords
interface StoredUser {
  username: string;
  role: 'clinician' | 'admin' | 'investigator' | 'auditor';
  salt: string;
  passwordHash: string;
}

const users: Map<string, StoredUser> = new Map();

/**
 * Hash password securely with PBKDF2 (SHA-512, 100,000 iterations)
 */
export function hashPassword(password: string, salt?: string): { salt: string; hash: string } {
  const userSalt = salt || crypto.randomBytes(16).toString('hex');
  const hash = crypto
    .pbkdf2Sync(password, userSalt, 100000, 64, 'sha512')
    .toString('hex');
  return { salt: userSalt, hash };
}

/**
 * Verify password against stored salt and hash using timingSafeEqual
 */
export function verifyPassword(password: string, salt: string, expectedHash: string): boolean {
  const hash = crypto
    .pbkdf2Sync(password, salt, 100000, 64, 'sha512')
    .toString('hex');
  const bufA = Buffer.from(hash, 'hex');
  const bufB = Buffer.from(expectedHash, 'hex');
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

// Seed users are created ONLY from explicitly provided environment variables.
// No hardcoded passwords exist: without AUTH_CLINICIAN_PASSWORD / AUTH_ADMIN_PASSWORD
// the auth endpoints fail closed (there are no accounts to log in to).
function initializeUsers() {
  if (users.size === 0) {
    const clinicianPassword = process.env.AUTH_CLINICIAN_PASSWORD;
    const adminPassword = process.env.AUTH_ADMIN_PASSWORD;

    if (clinicianPassword) {
      const clinician = hashPassword(clinicianPassword);
      users.set('clinical_evaluator', {
        username: 'clinical_evaluator',
        role: 'clinician',
        salt: clinician.salt,
        passwordHash: clinician.hash,
      });
    }

    if (adminPassword) {
      const admin = hashPassword(adminPassword);
      users.set('admin', {
        username: 'admin',
        role: 'admin',
        salt: admin.salt,
        passwordHash: admin.hash,
      });
    }

    if (!clinicianPassword && !adminPassword) {
      console.warn(
        '[AUTH] No seed credentials configured (AUTH_CLINICIAN_PASSWORD / AUTH_ADMIN_PASSWORD); ' +
          'legacy auth endpoints are disabled.'
      );
    }
  }
}
initializeUsers();

/**
 * Base64Url encode helper
 */
function base64UrlEncode(str: string): string {
  return Buffer.from(str, 'utf8')
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

/**
 * Base64Url decode helper
 */
function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) {
    base64 += '=';
  }
  return Buffer.from(base64, 'base64').toString('utf8');
}

/**
 * Generate standard JWT (HS256)
 */
export function generateToken(
  username: string,
  role: 'clinician' | 'admin' | 'investigator' | 'auditor',
  expiresInSeconds: number = TOKEN_EXPIRY_SECONDS
): string {
  const now = Math.floor(Date.now() / 1000);
  const header = {
    alg: 'HS256',
    typ: 'JWT',
  };
  const payload: TokenPayload = {
    sub: username,
    role,
    iat: now,
    exp: now + expiresInSeconds,
  };

  const headerEncoded = base64UrlEncode(JSON.stringify(header));
  const payloadEncoded = base64UrlEncode(JSON.stringify(payload));
  const signatureInput = `${headerEncoded}.${payloadEncoded}`;

  const signature = crypto
    .createHmac('sha256', JWT_SECRET)
    .update(signatureInput)
    .digest('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');

  return `${signatureInput}.${signature}`;
}

export type VerifyResult =
  | { valid: true; payload: TokenPayload }
  | { valid: false; reason: 'invalid_format' | 'invalid_signature' | 'expired' };

/**
 * Verify JWT signature and expiration
 */
export function verifyToken(token: string): VerifyResult {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return { valid: false, reason: 'invalid_format' };
  }

  const [headerEncoded, payloadEncoded, signatureEncoded] = parts;
  const signatureInput = `${headerEncoded}.${payloadEncoded}`;

  const expectedSignature = crypto
    .createHmac('sha256', JWT_SECRET)
    .update(signatureInput)
    .digest('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');

  const bufA = Buffer.from(signatureEncoded);
  const bufB = Buffer.from(expectedSignature);
  if (bufA.length !== bufB.length || !crypto.timingSafeEqual(bufA, bufB)) {
    return { valid: false, reason: 'invalid_signature' };
  }

  try {
    const payload: TokenPayload = JSON.parse(base64UrlDecode(payloadEncoded));
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now) {
      return { valid: false, reason: 'expired' };
    }
    return { valid: true, payload };
  } catch {
    return { valid: false, reason: 'invalid_format' };
  }
}

/**
 * Authenticate credentials
 */
export function authenticateUser(username: string, password: string): AuthenticatedUser | null {
  const user = users.get(username);
  if (!user) return null;
  if (!verifyPassword(password, user.salt, user.passwordHash)) {
    return null;
  }
  return {
    username: user.username,
    role: user.role,
  };
}

/**
 * Express middleware to extract & verify token if present
 */
export function extractAuth(req: express.Request, _res: express.Response, next: express.NextFunction) {
  const authHeader = req.headers['authorization'];
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.substring(7).trim();
    const result = verifyToken(token);
    if (result.valid) {
      (req as any).user = {
        username: result.payload.sub,
        role: result.payload.role,
      };
    }
  }
  next();
}

/**
 * Express middleware requiring valid JWT
 */
export function requireAuth(req: express.Request, res: express.Response, next: express.NextFunction) {
  const authHeader = req.headers['authorization'];
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ detail: 'Not authenticated' });
  }

  const token = authHeader.substring(7).trim();
  const result = verifyToken(token);

  if (result.valid === false) {
    if (result.reason === 'expired') {
      return res.status(401).json({ detail: 'Token has expired' });
    }
    return res.status(401).json({ detail: 'Could not validate credentials' });
  }

  (req as any).user = {
    username: result.payload.sub,
    role: result.payload.role,
  };
  next();
}
