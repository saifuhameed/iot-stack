FROM arm32v7/debian:bullseye-slim


# Install build tools and required libraries TEST
RUN apt-get update && apt-get install -y \
    build-essential \
    nano \
    libmodbus-dev \
    libcjson-dev \
    libsqlite3-dev \
    libhiredis-dev \
    && rm -rf /var/lib/apt/lists/*

# add new user for docker image
RUN useradd -ms /bin/bash iotuser

 

USER iotuser

WORKDIR /app

# Copy source code
COPY . .

# Compile your C application
RUN gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis

WORKDIR /app

COPY --from=build /app/app /app/app
# Run the app
CMD ["./modbus_to_redis"]
