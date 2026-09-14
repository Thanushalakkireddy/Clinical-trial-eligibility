# Production Dockerfile for Clinical Trial Eligibility System
# Unified Full-Stack (Node.js + Express + Vite + Tailwind)

FROM node:20-alpine AS builder

WORKDIR /app

# Install build dependencies
COPY package*.json ./
RUN npm ci

# Copy application source
COPY . .

# Build Vite frontend assets and bundle Express server into dist/server.cjs
RUN npm run build

# --- Production Runtime Image ---
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Install production dependencies only
COPY package*.json ./
RUN npm ci --omit=dev

# Copy compiled bundles and assets from builder
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/data ./data
COPY --from=builder /app/storage ./storage

# Create non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 3000

# Run the compiled CommonJS server bundle
CMD ["node", "dist/server.cjs"]
