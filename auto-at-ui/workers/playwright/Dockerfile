FROM mcr.microsoft.com/playwright:v1.50.1-noble
WORKDIR /worker
COPY package.json ./
RUN npm install --ignore-scripts
COPY tsconfig.json ./
COPY src ./src
EXPOSE 7100
CMD ["npm", "run", "start"]
