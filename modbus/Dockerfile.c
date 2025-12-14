# --- Stage 1: Build Stage ---
FROM gcc:latest AS build

WORKDIR /app

# Install build tools and required libraries 
RUN apt-get update && apt-get install -y \
    build-essential \    
    libmodbus-dev \
    libcjson-dev \
    libsqlite3-dev \
    libhiredis-dev \
    && rm -rf /var/lib/apt/lists/*

# copy source code and related files   TEST
COPY . .

# Compile your C application
RUN gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis

# --- Stage 2: Run Stage ---
# Use a minimal base image, e.g., 'alpine' is very small, 
# but requires static linking for C apps (use -static in gcc options).
# If you don't use -static, use a glibc-based image like 'ubuntu:focal-slim' or 'debian:buster-slim'
FROM arm32v7/debian:bullseye-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    nano \
    libmodbus \
    libcjson \
    libsqlite3 \
    libhiredis \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled executable from the 'build' stage to the 'run' stage
COPY --from=build /app/modbus_to_redis /app/modbus_to_redis

# Ensure the binary has execute permissions (though 'COPY' usually preserves them)
RUN chmod +x modbus_to_redis

# Run the app
CMD ["./modbus_to_redis"]
