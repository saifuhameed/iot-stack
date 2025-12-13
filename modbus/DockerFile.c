FROM arm32v7/debian:bullseye-slim

# Install build tools and required libraries TEST
RUN apt-get update && apt-get install -y \
    build-essential \
    libmodbus-dev \
    libcjson-dev \
    libsqlite3-dev \
    libhiredis-dev     

# add new user for docker image
RUN useradd -ms /bin/bash iotuser

 

USER iotuser

WORKDIR /app

# Copy source code
COPY . .

# Compile your C application
RUN gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis

# Run the app
CMD ["./modbus_to_redis"]
