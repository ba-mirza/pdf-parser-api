#!/bin/bash

set -e

echo "🐳 ТЕСТИРОВАНИЕ ЛЕГКОВЕСНОГО DOCKER ОБРАЗА"
echo "==========================================="

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "${YELLOW}📦 ШАГ 1: Сборка Docker образа...${NC}"
echo "Ожидаемое время: 1-2 минуты"
echo ""

start_time=$(date +%s)
docker build -t pdf-parser-api:light .
end_time=$(date +%s)
build_time=$((end_time - start_time))

if [ $? -eq 0 ]; then
    echo "${GREEN}✅ Образ собран успешно за ${build_time} секунд!${NC}"
else
    echo "${RED}❌ Ошибка при сборке образа${NC}"
    exit 1
fi

echo ""
echo "${YELLOW}📏 ШАГ 2: Проверка размера образа...${NC}"

image_size=$(docker images pdf-parser-api:light --format "{{.Size}}")
echo "Размер образа: ${BLUE}${image_size}${NC}"

size_mb=$(docker images pdf-parser-api:light --format "{{.Size}}" | sed 's/MB//' | sed 's/GB/*1024/' | bc 2>/dev/null || echo "unknown")

if [ "$size_mb" != "unknown" ] && [ $(echo "$size_mb < 1000" | bc -l) -eq 1 ]; then
    echo "${GREEN}✅ Размер оптимален! (<1 GB)${NC}"
    echo "${GREEN}💰 Экономия по сравнению с ML версией: ~2.5 GB${NC}"
else
    echo "${YELLOW}⚠️  Размер образа больше ожидаемого${NC}"
fi

echo ""
echo "${YELLOW}🚀 ШАГ 3: Запуск контейнера...${NC}"

docker stop pdf-parser-test 2>/dev/null || true
docker rm pdf-parser-test 2>/dev/null || true

docker run -d \
  --name pdf-parser-test \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  pdf-parser-api:light

if [ $? -eq 0 ]; then
    echo "${GREEN}✅ Контейнер запущен!${NC}"
else
    echo "${RED}❌ Ошибка при запуске контейнера${NC}"
    exit 1
fi

echo ""
echo "${YELLOW}⏳ ШАГ 4: Ожидание готовности API...${NC}"
echo "Легковесный образ стартует быстро (~2-5 секунд)"

sleep 3

echo ""
echo "${YELLOW}🏥 ШАГ 5: Проверка работы API...${NC}"

max_attempts=5
attempt=0

while [ $attempt -lt $max_attempts ]; do
    response=$(curl -s http://localhost:8000/ 2>/dev/null)

    if echo "$response" | grep -q "status"; then
        echo "${GREEN}✅ API отвечает корректно!${NC}"
        echo "Ответ: $response"
        break
    else
        attempt=$((attempt + 1))
        if [ $attempt -lt $max_attempts ]; then
            echo "Попытка $attempt/$max_attempts..."
            sleep 2
        else
            echo "${RED}❌ API не отвечает${NC}"
            echo ""
            echo "${YELLOW}📋 Логи контейнера:${NC}"
            docker logs pdf-parser-test
            exit 1
        fi
    fi
done

echo ""
echo "${YELLOW}💻 ШАГ 6: Проверка использования ресурсов...${NC}"

sleep 2

stats=$(docker stats pdf-parser-test --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}")
echo "$stats"

echo ""
echo "${YELLOW}📊 ШАГ 7: Детальная информация...${NC}"
echo ""
echo "${BLUE}Информация об образе:${NC}"
docker images pdf-parser-api:light --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

echo ""
echo "${BLUE}Слои образа:${NC}"
docker history pdf-parser-api:light --format "table {{.Size}}\t{{.CreatedBy}}" --no-trunc=false | head -15

echo ""
echo "${GREEN}════════════════════════════════════════${NC}"
echo "${GREEN}✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!${NC}"
echo "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "${BLUE}📊 ИТОГОВАЯ СТАТИСТИКА:${NC}"
echo "  Время сборки:       ${build_time} секунд"
echo "  Размер образа:      ${image_size}"
echo "  Контейнер:          pdf-parser-test"
echo "  URL:                http://localhost:8000"
echo "  Swagger docs:       http://localhost:8000/docs"
echo ""
echo "${BLUE}🎯 КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ:${NC}"
echo "  Просмотр логов:     docker logs -f pdf-parser-test"
echo "  Остановка:          docker stop pdf-parser-test"
echo "  Удаление:           docker rm pdf-parser-test"
echo "  Статистика:         docker stats pdf-parser-test"
echo ""
echo "${YELLOW}Для остановки нажмите Ctrl+C, затем:${NC}"
echo "docker stop pdf-parser-test && docker rm pdf-parser-test"
