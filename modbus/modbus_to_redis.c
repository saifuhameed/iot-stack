#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sqlite3.h>
#include <modbus/modbus.h>
#include <hiredis/hiredis.h>
#include <cjson/cJSON.h>
#include "config.h"
#include <errno.h>
#include <arpa/inet.h>  // for socket functions

#define MAX_DEVICES 128
#define MAX_REGISTERS 64
#define RETRY_DELAY 5   // seconds between retries for checking status of redis server

//gcc -o  modbus_to_redis  modbus_to_redis.c config.c -lmodbus -lcjson -lsqlite3 -lhiredis 


typedef struct {
    int function;
    int address;
    int count;
} RegisterDef;

typedef struct {
    int slaveid;
    char devicename[64];
    RegisterDef registers[MAX_REGISTERS];
    int register_count;
} Device;

int parse_register_list(const char *json_str, RegisterDef *regs, int *count) {
    cJSON *root = cJSON_Parse(json_str);
    if (!root || !cJSON_IsArray(root)) return -1;

    *count = 0;
    int len = cJSON_GetArraySize(root);
    for (int i = 0; i < len && i < MAX_REGISTERS; i++) {
        cJSON *item = cJSON_GetArrayItem(root, i);
        cJSON *fn = cJSON_GetObjectItem(item, "function");
        cJSON *addr = cJSON_GetObjectItem(item, "address");
        cJSON *cnt = cJSON_GetObjectItem(item, "count");
        if (cJSON_IsNumber(fn) && cJSON_IsNumber(addr) && cJSON_IsNumber(cnt)) {
            regs[*count].function = fn->valueint;
            regs[*count].address = addr->valueint;
            regs[*count].count = cnt->valueint;
            (*count)++;
        }
    }
    cJSON_Delete(root);
    return 0;
}

int load_devices(sqlite3 *db, Device *devices, int *device_count) {
    sqlite3_stmt *stmt;
    const char *sql =
        "SELECT d.slaveid, d.devicename, t.register_list "
        "FROM iotdevices d JOIN iot_devices_types t ON d.devices_type_id = t.devices_type_id";

    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) != SQLITE_OK) return -1;

    *device_count = 0;
    while (sqlite3_step(stmt) == SQLITE_ROW && *device_count < MAX_DEVICES) {
        Device *dev = &devices[*device_count];
        dev->slaveid = sqlite3_column_int(stmt, 0);
        const unsigned char *name = sqlite3_column_text(stmt, 1);
        const unsigned char *reglist = sqlite3_column_text(stmt, 2);
        strncpy(dev->devicename, name ? (const char *)name : "", sizeof(dev->devicename));
        if (reglist && parse_register_list((const char *)reglist, dev->registers, &dev->register_count) == 0) {
            (*device_count)++;
        }
    }

    sqlite3_finalize(stmt);
    return 0;
}

int read_modbus(modbus_t *ctx, int function, int address, int count, uint16_t *buffer) {
    if (count <= 0 || count > 64) return -1;

    int rc = -1;
    if (function == 3) {
        rc = modbus_read_registers(ctx, address, count, buffer);
    } else if (function == 4) {
        rc = modbus_read_input_registers(ctx, address, count, buffer);
    }

    return (rc == count) ? 0 : -1;
}


void upload_registers(redisContext *redis, int slaveid, int base_index, uint16_t *regs, int count, int ttl) {
    for (int k = 0; k < count; k++) {
        char key[64], val[32];
        snprintf(key, sizeof(key), "modbus:%d:reg%d", slaveid, base_index + k);
        snprintf(val, sizeof(val), "%d", regs[k]);
        redisReply *reply = redisCommand(redis, "SET %s %s EX %d", key, val, ttl);
        if (reply) freeReplyObject(reply);
    }
}

void populate_redis_keys_for_flask(sqlite3 *db, redisContext *redis, int ttl) {
    sqlite3_stmt *stmt1, *stmt2;

    const char *sql1 = "SELECT slaveid, devices_type_id FROM iotdevices";
    if (sqlite3_prepare_v2(db, sql1, -1, &stmt1, NULL) != SQLITE_OK) {
        fprintf(stderr, "Failed to prepare iotdevices query: %s\n", sqlite3_errmsg(db));
        return;
    }

    while (sqlite3_step(stmt1) == SQLITE_ROW) {
        int slaveid = sqlite3_column_int(stmt1, 0);
        int devices_type_id = sqlite3_column_int(stmt1, 1);

        const char *sql2 =
            "SELECT parameter_name, register_address FROM sensor_data_register_mapping "
            "WHERE devices_type_id = ?";
        if (sqlite3_prepare_v2(db, sql2, -1, &stmt2, NULL) != SQLITE_OK) continue;

        sqlite3_bind_int(stmt2, 1, devices_type_id);

        while (sqlite3_step(stmt2) == SQLITE_ROW) {
            const unsigned char *param = sqlite3_column_text(stmt2, 0);
            int address = sqlite3_column_int(stmt2, 1);

            if (!param) continue;

            char key[128], val[32];
            snprintf(key, sizeof(key), "modbus:%d:%s", slaveid, param);
            snprintf(val, sizeof(val), "%d", address);

            redisReply *reply = redisCommand(redis, "SET %s %s EX %d", key, val, ttl);
            if (reply) freeReplyObject(reply);

            printf("Loaded Redis key: %s → %s\n", key, val);
        }

        sqlite3_finalize(stmt2);
    }

    sqlite3_finalize(stmt1);
}

//SET modbus:write:7:4 3  SLAVEID=7, register_address=4, value=3
void handle_modbus_write_command(sqlite3 *db, redisContext *redis, modbus_t *ctx, int redis_ttl) {
    redisReply *keys = redisCommand(redis, "KEYS modbus:write:*");
    if (!keys || keys->type != REDIS_REPLY_ARRAY) {
        if (keys) freeReplyObject(keys);
        return;
    }

    for (size_t i = 0; i < keys->elements; i++) {
        const char *key = keys->element[i]->str;
        int slaveid;
        int address;
        if (sscanf(key, "modbus:write:%d:%d", &slaveid, &address) != 2) continue;

        redisReply *val = redisCommand(redis, "GET %s", key);
        if (!val || val->type != REDIS_REPLY_STRING) {
            if (val) freeReplyObject(val);
            continue;
        }

        int value = atoi(val->str);
        freeReplyObject(val);
 
        if (address < 0) continue; 
        modbus_set_slave(ctx, slaveid);
		char fail_key[128], result_key[128];
		snprintf(result_key, sizeof(result_key), "modbus:result:%d:%d", slaveid, address);
		snprintf(fail_key, sizeof(fail_key), "modbus:failcount:%d:%d", slaveid, address);

		//printf("WRITING TO MODBUS SLAVEID: %D,address: %d, value: %d\n", slaveid ,address,value);
		int rc = modbus_write_register(ctx, address, value);
		//printf("modbus_write_register returned %d for slave %d addr %d\n", rc, slaveid, address);

		if (rc >= 0 || errno == 0) {
			//printf("Wrote %d to slave %d register %d\n", value, slaveid, address);
			redisCommand(redis, "SET %s OK EX %d", result_key,redis_ttl);
			redisCommand(redis, "DEL %s", key);
			redisCommand(redis, "DEL %s", fail_key);  // reset failure count
		} else {
			fprintf(stderr, "Modbus write failed for %s\n", key);
			redisReply *fail = redisCommand(redis, "INCR %s", fail_key);
			int attempts = (fail && fail->type == REDIS_REPLY_INTEGER) ? fail->integer : 0;
			if (fail) freeReplyObject(fail);

			if (attempts >= 3) {				
				redisCommand(redis, "SET %s ERROR: Max retries reached EX %d", result_key,redis_ttl);
				redisCommand(redis, "DEL %s", key);
				redisCommand(redis, "DEL %s", fail_key);
				redisCommand(redis, "DEL %s", result_key); // delete result key too

			} else {				
				redisCommand(redis, "SET %s ERROR: Attempt %d EX %d", result_key, attempts,redis_ttl);
			}
		}


    }

    freeReplyObject(keys);
}

//SET modbus:write:7:SLAVEID 3 , 7 is slaveid 3 is value, SLAVEID is the register
void handle_modbus_write_command2(sqlite3 *db, redisContext *redis, modbus_t *ctx, int redis_ttl) {
    redisReply *keys = redisCommand(redis, "KEYS modbus:write:*");
    if (!keys || keys->type != REDIS_REPLY_ARRAY) {
        if (keys) freeReplyObject(keys);
        return;
    }

    for (size_t i = 0; i < keys->elements; i++) {
        const char *key = keys->element[i]->str;
        int slaveid;
        char param[64];
        if (sscanf(key, "modbus:write:%d:%63[^:]", &slaveid, param) != 2) continue;

        redisReply *val = redisCommand(redis, "GET %s", key);
        if (!val || val->type != REDIS_REPLY_STRING) {
            if (val) freeReplyObject(val);
            continue;
        }

        int value = atoi(val->str);
        freeReplyObject(val);

        sqlite3_stmt *stmt;
        const char *sql1 = "SELECT devices_type_id FROM iotdevices WHERE slaveid = ?";
        if (sqlite3_prepare_v2(db, sql1, -1, &stmt, NULL) != SQLITE_OK) continue;
        sqlite3_bind_int(stmt, 1, slaveid);
        int devices_type_id = -1;
        if (sqlite3_step(stmt) == SQLITE_ROW)
            devices_type_id = sqlite3_column_int(stmt, 0);
        sqlite3_finalize(stmt);
        if (devices_type_id < 0) continue;

        const char *sql2 =
            "SELECT register_address FROM sensor_data_register_mapping "
            "WHERE devices_type_id = ? AND parameter_name = ?";
        if (sqlite3_prepare_v2(db, sql2, -1, &stmt, NULL) != SQLITE_OK) continue;
        sqlite3_bind_int(stmt, 1, devices_type_id);
        sqlite3_bind_text(stmt, 2, param, -1, SQLITE_STATIC);
        int address = -1;
        if (sqlite3_step(stmt) == SQLITE_ROW)
            address = sqlite3_column_int(stmt, 0);
        sqlite3_finalize(stmt);
        if (address < 0) continue;

        modbus_set_slave(ctx, slaveid);
		char fail_key[128], result_key[128];
		snprintf(result_key, sizeof(result_key), "modbus:result:%d:%s", slaveid, param);
		snprintf(fail_key, sizeof(fail_key), "modbus:failcount:%d:%s", slaveid, param);

		//printf("WRITING TO MODBUS SLAVEID: %D,address: %d, value: %d\n", slaveid ,address,value);
		int rc = modbus_write_register(ctx, address, value);
		//printf("modbus_write_register returned %d for slave %d addr %d\n", rc, slaveid, address);

		if (rc >= 0 || errno == 0) {
			printf("Wrote %d to slave %d register %d (%s)\n", value, slaveid, address, param);
			redisCommand(redis, "SET %s OK EX %d", result_key,redis_ttl);
			redisCommand(redis, "DEL %s", key);
			redisCommand(redis, "DEL %s", fail_key);  // reset failure count
		} else {
			fprintf(stderr, "Modbus write failed for %s\n", key);
			redisReply *fail = redisCommand(redis, "INCR %s", fail_key);
			int attempts = (fail && fail->type == REDIS_REPLY_INTEGER) ? fail->integer : 0;
			if (fail) freeReplyObject(fail);

			if (attempts >= 3) {				
				redisCommand(redis, "SET %s ERROR: Max retries reached EX %d", result_key,redis_ttl);
				redisCommand(redis, "DEL %s", key);
				redisCommand(redis, "DEL %s", fail_key);
				redisCommand(redis, "DEL %s", result_key); // delete result key too

			} else {				
				redisCommand(redis, "SET %s ERROR: Attempt %d EX %d", result_key, attempts,redis_ttl);
			}
		}


    }

    freeReplyObject(keys);
}


// Function to check if Redis is accepting TCP connections
int is_redis_running(char * redis_host, int redis_port) {
    int sockfd;
    struct sockaddr_in serv_addr;

    // Create socket
    if ((sockfd = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
        perror("Socket creation failed");
        return 0;
    }

    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(redis_port);

    // Convert IPv4 address from text to binary
    if (inet_pton(AF_INET, redis_host, &serv_addr.sin_addr) <= 0) {
        perror("Invalid address");
        close(sockfd);
        return 0;
    }

    // Try connecting to Redis
    int result = connect(sockfd, (struct sockaddr *)&serv_addr, sizeof(serv_addr));
    close(sockfd);

    return (result == 0); // 1 if connected, 0 otherwise
}

int main() {
    Config cfg;
    if (load_config("config.ini", &cfg) != 0) {
        fprintf(stderr, "Failed to load config.ini\n");
        return 1;
    }
	if (cfg.redis_ttl <= 0) cfg.redis_ttl = 60;

    sqlite3 *db;
    if (sqlite3_open(cfg.db_path, &db) != SQLITE_OK) {
        fprintf(stderr, "SQLite open error: %s\n", sqlite3_errmsg(db));
        return 1;
    }
	while (!is_redis_running(cfg.redis_host, cfg.redis_port)) {
        printf("Redis not available yet. Retrying in %d second(s)...\n", RETRY_DELAY);
        sleep(RETRY_DELAY);
    }

    printf("✅ Redis server is running! Proceeding...\n");

    redisContext *redis = redisConnect(cfg.redis_host, cfg.redis_port);
    if (!redis || redis->err) {
        fprintf(stderr, "Redis error: %s\n", redis ? redis->errstr : "NULL");
        sqlite3_close(db);
        return 1;
    }
	populate_redis_keys_for_flask(db, redis, cfg.redis_ttl);
	
    modbus_t *ctx = modbus_new_rtu(cfg.device, cfg.baudrate, cfg.parity, cfg.data_bits, cfg.stop_bits);
	//modbus_set_debug(ctx, TRUE);
    if (!ctx || modbus_connect(ctx) == -1) {
        fprintf(stderr, "Modbus connection failed\n");
        redisFree(redis);
        sqlite3_close(db);
        return 1;
    }

    Device devices[MAX_DEVICES];
    int device_count = 0;
    if (load_devices(db, devices, &device_count) != 0) {
        fprintf(stderr, "Failed to load devices\n");
        modbus_close(ctx);
        modbus_free(ctx);
        redisFree(redis);
        sqlite3_close(db);
        return 1;
    }

    while (1) {
        for (int i = 0; i < device_count; i++) {
            modbus_set_slave(ctx, devices[i].slaveid);
			int reg_offset = 0;
			for (int j = 0; j < devices[i].register_count; j++) {
				RegisterDef *reg = &devices[i].registers[j];
				uint16_t regs[64];
				if (read_modbus(ctx, reg->function, reg->address, reg->count, regs) == 0) {
					printf("slaveid: %d  ",devices[i].slaveid);
					for (int k = 0; k < reg->count; k++) {
						printf("%02d, ",regs[k]);
					}
					printf("\n");
					upload_registers(redis, devices[i].slaveid, reg_offset, regs, reg->count, cfg.redis_ttl);
					reg_offset += reg->count;
				}
			}
        }
        handle_modbus_write_command(db, redis, ctx, cfg.redis_ttl);
        sleep(cfg.poll_interval);
    }

    modbus_close(ctx);
    modbus_free(ctx);
    redisFree(redis);
    sqlite3_close(db);
    return 0;

}
