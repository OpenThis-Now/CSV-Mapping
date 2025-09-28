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

# Build the app
RUN npm run build

# Install serve to serve the built files
RUN npm install -g serve

# Expose port
EXPOSE 3000

# Create a simple start script
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'serve -s dist -l 3000' >> /app/start.sh && \
    chmod +x /app/start.sh

# Use the start script
CMD ["/app/start.sh"]