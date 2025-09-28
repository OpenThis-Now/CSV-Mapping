#!/bin/bash

# Deployment script for production

echo "🚀 Starting deployment..."

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo "❌ .env.production file not found!"
    echo "Please create .env.production with your production settings"
    exit 1
fi

# Build and start services
echo "📦 Building Docker images..."
docker-compose -f docker-compose.prod.yml build

echo "🔄 Starting services..."
docker-compose -f docker-compose.prod.yml up -d

echo "✅ Deployment complete!"
echo "🌐 Your app should be available at: http://your-domain.com"
echo "📊 Check logs with: docker-compose -f docker-compose.prod.yml logs -f"
