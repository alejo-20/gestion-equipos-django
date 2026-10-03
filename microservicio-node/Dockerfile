# Imagen del microservicio de equipos en Node.js.
#
# Son dos etapas a proposito: la primera instala las dependencias y la segunda
# copia SOLO node_modules + el codigo. La imagen final no tiene ni el npm ni los
# sources de compilacion de las dependencias, asi que es mas chica y tiene menos
# superficie que un `npm install` en cada arranque.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
# `npm ci` instala exactamente lo que dice package-lock.json. Si no hay lock
# todavia, `npm install` lo genera y el comando falla, que es lo que evita que
# la imagen se construya con versiones distintas a las probadas en local.
RUN npm ci --omit=dev

FROM node:20-alpine
WORKDIR /app

ENV NODE_ENV=production
# Puerto por defecto del servicio. El entrypoint de Docker puede sobreescribirlo
# con -e PORT=..., que es como lo publican los hosting de contenedores.
ENV PORT=8082

COPY --from=deps /app/node_modules ./node_modules
COPY package*.json ./
COPY src ./src

# usuario sin privilegios: si alguien logra ejecutar codigo adentro del
# contenedor, no puede escribir en el sistema de archivos.
USER node

EXPOSE 8082

CMD ["node", "src/server.js"]
