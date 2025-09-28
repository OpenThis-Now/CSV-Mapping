# frontend/Dockerfile
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Set environment variable for Railway backend
ENV VITE_API_BASE=https://csv-mapping-production.up.railway.app/api

# Build the app with TypeScript check disabled for Railway
RUN npm run build:prod

# Install serve to serve the built files
RUN npm install -g serve

# Create start script for Railway
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'serve -s dist -l 3000' >> /app/start.sh && \
    chmod +x /app/start.sh

# Expose port
EXPOSE 3000

# Use start script
CMD ["/app/start.sh"]