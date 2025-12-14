# Use a minimal base image, e.g., 'alpine' is very small, 
# but requires static linking for C apps (use -static in gcc options).
# If you don't use -static, use a glibc-based image like 'ubuntu:focal-slim' or 'debian:buster-slim'
FROM arm32v7/alpine:latest

RUN apt-get update && apt-get install -y \    
    build-essential \   
    nano \
    libmodbus-dev \
    libcjson-dev \
    libsqlite3-dev \
    libhiredis-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis

# Ensure the binary has execute permissions (though 'COPY' usually preserves them)
RUN chmod +x modbus_to_redis

# Run the app
CMD ["./modbus_to_redis"]
