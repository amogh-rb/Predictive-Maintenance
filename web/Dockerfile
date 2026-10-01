# Build context is web/ itself (unlike the Python services, this has no
# repo-root dependency to pull in). Multi-stage: build with Vite, serve the
# static output with `vite preview` so this needs no extra web-server image.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_KEYCLOAK_URL=http://localhost:8082
ARG VITE_KEYCLOAK_REALM=fleetpulse
ARG VITE_KEYCLOAK_CLIENT_ID=fleetpulse-web
ENV VITE_API_URL=$VITE_API_URL \
    VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL \
    VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM \
    VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID
RUN npm run build

FROM node:22-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
EXPOSE 5173
CMD ["npm", "run", "preview"]
