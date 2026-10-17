# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# CrossFit Judge — WEB image (Next.js UI + API proxy)
# The Python AI engine has its own image: mini-services/crossfit-judge/Dockerfile
# ---------------------------------------------------------------------------
FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# bun is only used as a fast, lockfile-exact installer (bun.lock is the source of truth)
RUN npm install -g bun@1 --silent
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
RUN npx next build

FROM node:22-slim AS run
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
# the standalone trace drags the Python engine sources in; they are NOT needed here
RUN rm -rf mini-services docs *.md
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
