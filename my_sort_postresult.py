import os
import numpy as np
import re
import pandas as pd
import time
location_up = 'D:\\wangpeilin\\cst_20200218\\cst_new\\my_subject_kbann\\result20210308001\\'
location = 'D:\\wangpeilin\\cst_20200218\\cst_new\\my_subject_kbann\\result20210308001\\data01\\result\\'
output_name = ['frequent','R_divide_Q','shunt_impedance','Q-factor','voltage','total_loss']
text_name = ["Frequency", "R_Q", "ShuntImpedance", "Q-Factor", "Voltage", "TotalLoss"]
input_name = ['nmodes','fmin','mode']

# for root,dirs,files in os.walk(location):
    # for dir in dirs: 
        # print os.path.join(root,dir).decode('gbk'); 
    # for file in files: 
        # print os.path.join(root,file).decode('gbk'); 

def return_location(sub,string):
    return [i.start() for i in re.finditer(sub, string)]
    
def get_value(file):
    f = open(file)
    text = f.read()
    # print(text[140:])
    return float(text[140:])


samples = pd.DataFrame(columns=input_name+output_name)
if (os.path.exists(location)):
    files = os.listdir(location)
    for file in files:
        m = os.path.join(location,file)
        if "frequency000000_" in m:
            sub_files = os.listdir(m+"\\")
            # fmin_start = int(return_location("frequency000000_",m)[0]+16)
            # print(fmin_start)
            print(m)
            try:
                fmin = int(m[-4:])
            except:
                fmin = int(m[-3:])

            mode1 = np.zeros(len(input_name)+len(text_name))
            mode2 = np.zeros(len(input_name)+len(text_name))
            mode3 = np.zeros(len(input_name)+len(text_name))
            
            mode1[0] = mode2[0] = mode3[0] = 3
            mode1[1] = mode2[1] = mode3[1] = fmin
            mode1[2] = 1
            mode2[2] = 2
            mode3[2] = 3
            # print(mode1,"\n",mode2,"\n",mode3)

            for sub_file in sub_files:
                sub_m = os.path.join(m+"\\",sub_file)
                
                if "Mode1" in sub_m:
                    for i in range(len(text_name)):
                        if text_name[i] in sub_m:
                            mode1[len(input_name)+i] = get_value(sub_m)
                            
                if "Mode2" in sub_m:
                    for i in range(len(text_name)):
                        if text_name[i] in sub_m:
                            mode2[len(input_name)+i] = get_value(sub_m)
                            
                if "Mode3" in sub_m:
                    for i in range(len(text_name)):
                        if text_name[i] in sub_m:
                            mode3[len(input_name)+i] = get_value(sub_m)
            print(mode1,"\n",mode2,"\n",mode3)
            samples = samples.append(pd.DataFrame([list(mode1)], columns=input_name+output_name))
            samples = samples.append(pd.DataFrame([list(mode2)], columns=input_name+output_name))
            samples = samples.append(pd.DataFrame([list(mode3)], columns=input_name+output_name))
            #time.sleep(1)
else:
    print(location+" does not exit")
samples.to_csv(location_up+"picture\\all_result.csv",index=True,sep=',')