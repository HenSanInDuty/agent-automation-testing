FROM node:22-alpine

WORKDIR /benchmark
COPY server.mjs seed.json ./

EXPOSE 7200
CMD ["node", "server.mjs"]
