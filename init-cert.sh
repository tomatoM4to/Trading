#!/bin/bash
# Nginx 컨테이너가 80포트를 점유하고 있다면 임시 중지
docker compose stop nginx-proxy || true

# 환경변수 로드 (.env)
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Error: DOMAIN and EMAIL environment variables must be set in .env"
  exit 1
fi

# Certbot 컨테이너를 일회성(--rm)으로 실행하여 인증서 발급
docker run -it --rm --name certbot \
  -p 80:80 \
  -v "$(pwd)/.nginx/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/.nginx/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --standalone \
  -d ${DOMAIN} \
  --email ${EMAIL} \
  --agree-tos \
  --no-eff-email

echo "인증서 초기 발급 완료! 서비스를 (재)시작합니다."
docker compose up -d