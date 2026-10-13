FROM node:22-alpine AS build
WORKDIR /app
COPY VERSION ./VERSION
COPY ui/package*.json ./ui/
WORKDIR /app/ui
RUN npm install
COPY ui/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/ui/dist /usr/share/nginx/html
EXPOSE 80
