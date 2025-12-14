 
# -------- BUILD STAGE --------
FROM debian:bookworm AS builder


RUN apt-get update && apt-get install -y \    
    build-essential \       
    libmodbus-dev \
    libcjson-dev \
    libsqlite3-dev \
    libhiredis-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY . .

RUN gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis

# Ensure the binary has execute permissions (though 'COPY' usually preserves them)
RUN chmod +x modbus_to_redis


# -------- RUNTIME STAGE --------
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \      
    nano \
    libmodbus5 \
    libcjson1 \
    libsqlite3-0 \
    libhiredis0.14 \
    && rm -rf /var/lib/apt/lists/*
# Create a new group and user
# -r creates a system account
# -m creates the home directory
# -s specifies the default shell
RUN groupadd -r appgroup && useradd -r -m -s /bin/bash -g appgroup appuser

# Switch to the new non-root user
USER appuser

WORKDIR /app

COPY --from=builder /build/modbus_to_redis .
COPY   config.ini .
# Run the app
CMD ["./modbus_to_redis"]
