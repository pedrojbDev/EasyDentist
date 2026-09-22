FROM node:24.19.0-alpine3.23 AS dependencies

ENV pnpm_config_fetch_retries=5 \
    pnpm_config_fetch_timeout=300000

WORKDIR /app
RUN npm install --global pnpm@11.10.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM dependencies AS builder

ARG API_INTERNAL_BASE_URL=http://api:8000
ARG APP_ENV=development
ENV API_INTERNAL_BASE_URL=$API_INTERNAL_BASE_URL
ENV APP_ENV=$APP_ENV

COPY apps/web ./apps/web
RUN pnpm --filter @easydentist/web build

FROM node:24.19.0-alpine3.23 AS runtime

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
