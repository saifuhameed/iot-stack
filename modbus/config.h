#ifndef CONFIG_H
#define CONFIG_H

typedef struct {
    char device[64];
    int baudrate;
    char parity;
    int data_bits;
    int stop_bits;
    char redis_host[64];
    int redis_port;
    char db_path[128];
    int poll_interval;
    int log_interval;
	int redis_ttl;
} Config;

int load_config(const char *filename, Config *cfg);

#endif
