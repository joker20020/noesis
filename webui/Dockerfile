# ---- Build stage ----
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* vars are inlined at build time; set defaults for Docker
ARG NEXT_PUBLIC_API_HOST=localhost
ARG NEXT_PUBLIC_API_PORT=8000
ENV NEXT_PUBLIC_API_HOST=$NEXT_PUBLIC_API_HOST
ENV NEXT_PUBLIC_API_PORT=$NEXT_PUBLIC_API_PORT

RUN npm run build

# ---- Run stage ----
FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./

# Only production deps
RUN npm ci --omit=dev

EXPOSE 3000

CMD ["npx", "next", "start"]
