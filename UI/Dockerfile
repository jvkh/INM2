FROM node:22-alpine AS build
WORKDIR /app
COPY VERSION ./VERSION
COPY UI/package*.json ./UI/
WORKDIR /app/UI
RUN npm install
COPY UI/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY UI/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/UI/dist /usr/share/nginx/html
EXPOSE 80
