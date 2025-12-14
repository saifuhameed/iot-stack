from flask import Flask, request, render_template, jsonify
import sqlite3
import random
import redis
from enum import Enum
import time

TEMPERATURE_ERROR_VALUE=5010

class SENS_PARAM_POS(Enum):
    CAP_LEVEL_ZERO_PF       = 0        # cap_level_zero_pf
    CAP_LEVEL_FULL_PF       = 1        # cap_level_full_pf
    LEVEL_FULL_MM           = 2        # level full mm
    OSC_RES1_VAL_LSB        = 3         # osc_res1_val_lsb
    OSC_RES1_VAL_MSB        = 4         # osc_res1_val_msb
    OSC_RES2_VAL_LSB        = 5         # osc_res2_val_lsb
    OSC_RES2_VAL_MSB        = 6         # osc_res2_val_msb
    OSC_K_VAL               = 7                # osc_k_val
    LEVEL_HIGH_IN_PERC_SET  = 8   # level_high_in_perc_set
    LEVEL_LOW_IN_PERC_SET   = 9    # level_low_in_perc_set    
    SENS_PARAM_COUNT        = 10        # total count
    
class SENS_DATA_POS(Enum):
    LEVEL_IN_MM         = 0         # level_in_mm
    CAP_PF              = 1              # cap_pf
    FREQUENCY_LSB       = 2       # frequency_lsb
    FREQUENCY_MSB       = 3       # frequency_msb
    LIQUID_TEMP         = 4         # liquid_temp    
    ALARM_LEVEL_LOW     = 5     # level_alarm_low
    ALARM_LEVEL_HIGH    = 6    # level_alarm_high
    SENS_DATA_COUNT     = 7     # total number of data fields

class holding_registers(Enum):
    SLAVEID                 = 0
    BAUDRATE                = 1
    SENSOR1_CONFIG          = 2
    SENSOR2_CONFIG          = SENSOR1_CONFIG    + SENS_PARAM_POS.SENS_PARAM_COUNT.value
    SENSOR1_DATA            = SENSOR2_CONFIG    + SENS_PARAM_POS.SENS_PARAM_COUNT.value
    SENSOR2_DATA            = SENSOR1_DATA      + SENS_DATA_POS.SENS_DATA_COUNT.value  
    
app = Flask(__name__)

# Redis connection
r = redis.Redis(host='redis', port=6379, decode_responses=True)

# SQLite connection
def get_db_connection():
    conn = sqlite3.connect('/data/iot.db')
    conn.row_factory = sqlite3.Row
    return conn

def is_number(val):
    if val is None:
        return False
    try:
        float(val)
        return True
    except ValueError:
        return False       
    
def string_to_number(val):
    return float(val) if '.' in val else int(val)
    
def string_to_int_by10_negated(val):
    val= string_to_number(val) if is_number(val) else 0   
    val=round((val/10 )-10 ,1)  
    return val
    
def string_to_int(val):
    val= string_to_number(val) if is_number(val) else 0    
    return val
def string_to_int_by10(val):
    val= round(string_to_number(val)/10,1) if is_number(val) else 0    
    return val
def string_to_int_by1000(val):
    val= round(string_to_number(val)/1000,4) if is_number(val) else 0    
    return val

    
def string_to_intX10(val):
    val= string_to_number(val)*10 if is_number(val) else 0    
    return val
def string_to_intX1000(val):
    val= string_to_number(val)*1000 if is_number(val) else 0    
    return val
    
def denormalize_data(val):
    val= string_to_number(val)*10 if is_number(val) else 0    
    return val
    
def getRegisterValue (slaveid,registeradress):
    try:
        value = r.get(f"modbus:{slaveid}:reg{registeradress}")
        return value
    except redis.exceptions.ConnectionError:
        return None  # Redis not running / not reachable

def check_redis_alive():
    try:
        r.set("health_check_key", "1")
        return True
    except redis.exceptions.ConnectionError:
        return False
    except redis.exceptions.RedisError:
        # other Redis errors (e.g., read-only)
        return False
      
@app.route("/health")
def health():
    """Optional: health check"""
    try:
        if r.ping():
            return jsonify({"redis": "ok"}), 200
    except redis.exceptions.ConnectionError:
        return jsonify({"redis": "down"}), 503  
  
# POST /api/update-parameters
#   body: { tank, zeroPf, fullPf,  levelFullMm, levelHighSet, levelLowSet, oscRes1, oscRes2, oscKVal }
@app.route("/api/update-parameters", methods=['POST'])
def updateParameters():
    if request.method == 'POST':
        if not check_redis_alive():
            return {"status": "redis-connection-error", "updated": "None"}
        data = request.get_json()
        tank = data.get("tank")
        zeroPf=  string_to_intX10(data.get('zeroPf'))        
        fullPf = string_to_intX10(data.get('fullPf'))
        levelFullMm = string_to_intX10(data.get('levelFullMm'))       
        levelHighSet = string_to_intX10(data.get('levelHighSet'))
        levelLowSet = string_to_intX10(data.get('levelLowSet'))
        advanced_settings=False
        if(data.get('oscRes1')is not None):
            advanced_settings=True
        if advanced_settings:    
            oscRes1 = string_to_int(data.get('oscRes1'))
            oscRes2 = string_to_int(data.get('oscRes2'))
            oscKVal = string_to_intX1000(data.get('oscKVal'))
        if(tank=='overhead1'):
            slaveid =5       
            sensorconfig=holding_registers.SENSOR1_CONFIG.value
            sensordata=holding_registers.SENSOR1_DATA.value          
        if(tank=='overhead2'):
            slaveid =5       
            sensorconfig=holding_registers.SENSOR2_CONFIG.value
            sensordata=holding_registers.SENSOR2_DATA.value
        if(tank=='underground'):
            slaveid =6       
            sensorconfig=holding_registers.SENSOR1_CONFIG.value
            sensordata=holding_registers.SENSOR1_DATA.value
        
        zeroPf_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.CAP_LEVEL_ZERO_PF.value))
        fullPf_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.CAP_LEVEL_FULL_PF.value))
        levelFullMm_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_FULL_MM.value))
        levelHighSet_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_HIGH_IN_PERC_SET.value))
        levelLowSet_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_LOW_IN_PERC_SET.value))
        if(zeroPf!=zeroPf_modbus):
            r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.CAP_LEVEL_ZERO_PF.value}", zeroPf)
            #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.CAP_LEVEL_ZERO_PF.value}", zeroPf)
        if(fullPf!=fullPf_modbus):
            r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.CAP_LEVEL_FULL_PF.value}", fullPf)
            #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.CAP_LEVEL_FULL_PF.value}", fullPf)             
        if(levelFullMm!=levelFullMm_modbus):
            r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.LEVEL_FULL_MM.value}", levelFullMm)
            #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.LEVEL_FULL_MM.value}", levelFullMm)        
        if(levelHighSet!=levelHighSet_modbus):
            r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.LEVEL_HIGH_IN_PERC_SET.value}", levelHighSet)
            #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.LEVEL_HIGH_IN_PERC_SET.value}", levelHighSet)
        if(levelLowSet!=levelLowSet_modbus):
            r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.LEVEL_LOW_IN_PERC_SET.value}", levelLowSet)
            #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.LEVEL_LOW_IN_PERC_SET.value}", levelLowSet)         
        if advanced_settings:
            oscRes1_modbus_lsb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_LSB.value))
            oscRes1_modbus_msb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_MSB.value))
            oscRes2_modbus_lsb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_LSB.value))
            oscRes2_modbus_msb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_MSB.value))
            oscKVal_modbus=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_K_VAL.value))        
            oscRes1_modbus=   oscRes1_modbus_msb<<16 | oscRes1_modbus_lsb
            oscRes2_modbus=   oscRes2_modbus_msb<<16 | oscRes2_modbus_lsb

            if(oscRes1!=oscRes1_modbus):
                oscRes1_lsb=oscRes1 & 0xFFFF
                oscRes1_msb=(oscRes1>>16) & 0xFFFF           
                r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_LSB.value}", oscRes1_lsb)
                r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_MSB.value}", oscRes1_msb)
                #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_LSB.value}", oscRes1_lsb)
                #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_MSB.value}", oscRes1_msb)            
            if(oscRes2!=oscRes2_modbus):
                oscRes2_lsb=oscRes2 & 0xFFFF
                oscRes2_msb=(oscRes2>>16) & 0xFFFF 
                r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_LSB.value}", oscRes2_lsb)
                r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_MSB.value}", oscRes2_msb)
                #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_LSB.value}", oscRes2_lsb)
                #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_MSB.value}", oscRes2_msb)
            if(oscKVal!=oscKVal_modbus):
                r.set(f"modbus:write:{slaveid}:{sensorconfig+SENS_PARAM_POS.OSC_K_VAL.value}", oscKVal) 
                #r.set(f"modbus:{slaveid}:reg{sensorconfig+SENS_PARAM_POS.OSC_K_VAL.value}", oscKVal)            
            
        return {"status": "ok", "updated": data['tank']}
#GET /api/parameters?tank=if(tank=='overhead1'):|overhead2|underground
@app.route("/api/parameters")
def parameters():
    tank = request.args.get('tank')
    if(tank=='overhead1'):
        slaveid =5       
        sensorconfig=holding_registers.SENSOR1_CONFIG.value
        sensordata=holding_registers.SENSOR1_DATA.value
    if(tank=='overhead2'):
        slaveid =5       
        sensorconfig=holding_registers.SENSOR2_CONFIG.value
        sensordata=holding_registers.SENSOR2_DATA.value
    if(tank=='underground'):
        slaveid =6       
        sensorconfig=holding_registers.SENSOR1_CONFIG.value
        sensordata=holding_registers.SENSOR1_DATA.value
     
    zeroPf=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.CAP_LEVEL_ZERO_PF.value))
    fullPf=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.CAP_LEVEL_FULL_PF.value))
    levelFullMm=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_FULL_MM.value)) 
    oscRes1_lsb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_LSB.value))
    oscRes1_msb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES1_VAL_MSB.value))
    oscRes2_lsb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_LSB.value))
    oscRes2_msb=string_to_int(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_RES2_VAL_MSB.value))
    oscKVal=string_to_int_by1000(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.OSC_K_VAL.value)) 
    levelHighSet=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_HIGH_IN_PERC_SET.value))
    levelLowSet=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_LOW_IN_PERC_SET.value))    
    oscRes1=   oscRes1_msb<<16 | oscRes1_lsb
    oscRes2=   oscRes2_msb<<16 | oscRes2_lsb
    
    pfPerCm=round((fullPf-zeroPf)*10/levelFullMm,2) if levelFullMm>0 else 0
    data = {
        
            "zeroPf": zeroPf,    
            "fullPf": fullPf,   
            "levelFullMm": levelFullMm,     
            "levelHighSet": levelHighSet,   
            "levelLowSet": levelLowSet ,
            "oscRes1":oscRes1,
            "oscRes2": oscRes2 , 
            "oscKVal": oscKVal ,   
            "pfPerCm": pfPerCm             
        }
    return jsonify(data)        

#GET "/api/get-update-status"
@app.route("/api/get-update-status")
def get_update_status():
    if not check_redis_alive():
        return {"status": "redis-connection-error", "updated": "None"}
    write_pattern="modbus:write:*"
    write_keys = []
    for key in r.scan_iter(match=write_pattern):
        write_keys.append(key) # Decode bytes to string  
    if len(write_keys)==0:
        return jsonify({"status":"Nothing to update"})        
    result_key="modbus:result:*"
    timeout = 15  # seconds
    start_time = time.time() 
    keys  =[]
    while time.time() - start_time < timeout:
        for key in r.scan_iter(match=result_key, count=10):
            keys.append(key)
            r.delete(key)    
        if len(keys)>=len(write_keys):  # non-empty value found
            break
        time.sleep(0.1)  # small delay to avoid busy loop
    if len(keys)>=len(write_keys):
        return jsonify({"status": f"{len(keys)} parameter/s updated" })
    else:
        return jsonify({"status":"Failed"})        
    
#GET /api/readings?tank=if(tank=='overhead1'):|overhead2|underground
@app.route("/api/readings")
def readings():
    tank = request.args.get('tank')
    if(tank=='overhead1'):
        slaveid =5       
        sensorconfig=holding_registers.SENSOR1_CONFIG.value
        sensordata=holding_registers.SENSOR1_DATA.value
    if(tank=='overhead2'):
        slaveid =5       
        sensorconfig=holding_registers.SENSOR2_CONFIG.value
        sensordata=holding_registers.SENSOR2_DATA.value
    if(tank=='underground'):
        slaveid =6       
        sensorconfig=holding_registers.SENSOR1_CONFIG.value
        sensordata=holding_registers.SENSOR1_DATA.value
    #CAP_PF will return None if no modbus device available and 
    # return "0" if modbus available but sensor not connected, 
    sensor_check=getRegisterValue(slaveid,sensordata+SENS_DATA_POS.CAP_PF.value)
    #None="No MODBUS device found", 0= "Sensor head not connected", >0 = "OK"
    sensorStatus="No MODBUS device found" if sensor_check is None else "OK" if string_to_int(sensor_check)>0 else "Sensor head is not connected"
    #sensorStatus="OK" if sensor_check>0 else ("No MODBUS device found" if sensor_check is None else "Sensor head not connected")
    level_full=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_FULL_MM.value)) 
    liquidLevel=string_to_int_by10_negated(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.LEVEL_IN_MM.value))
    sensorCap=string_to_int_by10(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.CAP_PF.value))
    frequency_lsb=string_to_int(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.FREQUENCY_LSB.value))
    frequency_msb=string_to_int(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.FREQUENCY_MSB.value))
    temp=string_to_int(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.LIQUID_TEMP.value))
    if(temp!= TEMPERATURE_ERROR_VALUE):
        temp=round((temp/10)-10,1)
    else:
        temp=None
    alarmLow=string_to_int_by10(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.ALARM_LEVEL_LOW.value))
    alarmHigh=string_to_int_by10(getRegisterValue(slaveid,sensordata+SENS_DATA_POS.ALARM_LEVEL_HIGH.value))
    levelHighSet=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_HIGH_IN_PERC_SET.value))
    levelLowSet=string_to_int_by10(getRegisterValue(slaveid,sensorconfig+SENS_PARAM_POS.LEVEL_LOW_IN_PERC_SET.value))
    freq=frequency_msb<<16 | frequency_lsb
    liquidLevelPct=round(liquidLevel*100/level_full,1) if level_full>0 else 0
    alarm="LOW" if (alarmLow==1) else "NORMAL"
    alarm="HIGH" if (alarmHigh==1) else "NORMAL"
    data = {
            "sensorStatus": sensorStatus  , # non zero means sensor OK
            "liquidTemperature": temp if freq>0 else None,    
            "sensorCap": sensorCap if freq>0 else None,   # percentage
            "frequency": freq if freq>0 else None,     # °C
            "liquidLevel": liquidLevel if freq>0 else None,   
            "alarm": alarm if freq>0 else None,
            "liquidLevelPct":liquidLevelPct if freq>0 else None,  
            "liquidLevelHighSet":levelHighSet,
            "liquidLevelLowSet":levelLowSet
        }
    return jsonify(data)
    
@app.route("/api/iot_data")
def iot_data():

    # Option B: Full JSON object
    raw = r.get("iot:data")
    capacitance1= (r.get("modbus:5:reg23"))
    capacitance1= int(capacitance1) if is_number(capacitance1) else 0
        
    level_mm1=(r.get("modbus:5:reg22"))
    level_mm1= int(level_mm1) if is_number(level_mm1) else 0
    level_mm1=(level_mm1-10)/10
    
    level_full_mm1=(r.get("modbus:5:reg4"))
    level_full_mm1= int(level_full_mm1) if is_number(level_full_mm1) else 0
    level_full_mm1=(level_full_mm1)/10
    
    level_percentage1=round(level_mm1*100/level_full_mm1,1) if level_full_mm1>0 else 0
    
    temperature1=(r.get("modbus:5:reg26"))
    temperature1= round((int(temperature1)/10)-10,1) if is_number(temperature1) else 0
    
    capacitance2= (r.get("modbus:5:reg30"))
    capacitance2= int(capacitance2) if is_number(capacitance2) else 0 
    
    level_mm2=((r.get("modbus:5:reg29")))
    level_mm2= int(level_mm2) if is_number(level_mm2) else 0 
    level_mm2=(level_mm2-10)/10
    
    level_full_mm2=(r.get("modbus:5:reg14"))
    level_full_mm2= int(level_full_mm2) if is_number(level_full_mm2) else 0 
    level_full_mm2=(level_full_mm2)/10
    
    level_percentage2=round(level_mm2*100/level_full_mm2,1) if level_full_mm2>0 else 0
    
    temperature2=(r.get("modbus:5:reg33"))  
    temperature2=round((int(temperature2)/10)-10,1) if is_number(temperature2) else 0     
    temperature1=temperature2
    
    #Under Ground Tank
    capacitance3= (r.get("modbus:6:reg23"))
    capacitance3= int(capacitance1) if is_number(capacitance1) else 0
        
    level_mm3=(r.get("modbus:6:reg22"))
    level_mm3= int(level_mm3) if is_number(level_mm3) else 0
    level_mm3=(level_mm3-10)/10
    
    level_full_mm3=(r.get("modbus:6:reg4"))
    level_full_mm3= int(level_full_mm3) if is_number(level_full_mm3) else 0
    level_full_mm3=(level_full_mm3)/10
    
    level_percentage3=round(level_mm3*100/level_full_mm3,1) if level_full_mm3>0 else 0
    
    temperature3=(r.get("modbus:6:reg26"))
    temperature3= round((int(temperature3)/10)-10,1) if is_number(temperature3) else 0
    
    data = {
        "overhead1": {
            "capacitance": capacitance1,    
            "level": level_percentage1,   # percentage
            "temp": temperature1     # °C
        },
        "overhead2": {
            "capacitance": capacitance2,    
            "level": level_percentage2,   # percentage
            "temp": temperature2     # °C
        },
        "underground": {
            "capacitance": capacitance3,  
            "level": level_mm3,  # percentage
            "temp": temperature3
        },
        "humidity": random.randint(40, 70),      # %
        "ambient_temp": random.randint(20, 35),  # °C
        "rain": random.choice([0, 1]),           # 0=dry, 1=rain
        "wind": {
            "speed": random.randint(0, 40),      # km/h
            "direction": random.randint(0, 359)  # degrees
        },
        "rooms": {
            "room1": random.randint(22, 28),
            "room2": random.randint(22, 28),
            "room3": random.randint(22, 28),
            "room4": random.randint(22, 28)
        }
    }
    return jsonify(data)

@app.route('/')
def index():
    return render_template('live.html')

@app.route('/levelconfig')
def levelconfig():
    return render_template('levelconfig.html')

@app.route('/registers')
def registers():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Join iotdevices and sensor_data_register_mapping
    cursor.execute("""
        SELECT d.slaveid, m.parameter_name, m.register_address
        FROM iotdevices d
        JOIN sensor_data_register_mapping m
        ON d.devices_type_id = m.devices_type_id
    """)

    rows = cursor.fetchall()
    data = []

    for row in rows:
        slaveid = row['slaveid']
        param = row['parameter_name']
        #redis_key = f"modbus:{slaveid}:{param}"
        redis_key = f"modbus:{slaveid}:reg{row['register_address']}"
        redis_val = r.get(redis_key)
        data.append({
            'slaveid': slaveid,
            'parameter': param,
            'register': row['register_address'],
            'redis_key': redis_key,
            'redis_val': redis_val
        })

    conn.close()
    return render_template('registers.html', data=data)
if __name__ == '__main__':
    app.run()
    