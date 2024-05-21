"""produce LHS sample"""
###修改内容
###runWithX 修改为 runWithParam 需要提供param_name_list 和 value_list 作为参数
###addTask 同上
###初值需要自己写，留空[]则为默认
###
import os
import result
import numpy as np
from . import yfunction
import time
import random
import pandas as pd


class myAlg01(object):
    def __init__(self, manager, params):
        self.parameter_range = 0
        self.params = params

        # self.state_x0 = copy.deepcopy(x0)
        self.state_x0 = []
        self.state_y0 = 0

        # 读写
        self.location = "H:\\test20200831\\test\\my_subject_kbann\\"  #'D:\\wangpeilin\\cst_new\\my subject\\'
        self.relative_location = "result121501\\"
        ##y函数,
        self.yFunc = yfunction.yfunc(yfunction.myYFunc01)

        ###OTHERS
        self.w = manager
        self.results = result.result
        logpath = os.path.join(self.w.getResultDir(), "result.log")
        self.log = open(logpath, "w")

        # produce random sample
        # self.location = 'H:\\test20200831\\test\\my subject kbann\\'#C:\\Users\\asus\\Desktop\\test20200831\\cst_new\\my subject\\'
        # self.relative_location = 'result113001\\'

        self.generation_num = 100
        self.input_name = [
            "Leq",
            "R3_left",
            "R3_right",
            "Req",
            "cocave",
            "concave_L",
            "nose",
            "r0_left",
            "r0_right",
            "r1_left",
            "r1_right",
            "r2_left",
            "r2_right",
        ]

        # self.input_name_calculate = ['l', 'ltube', 'number']
        self.output_name = [
            "global result",
            "frequent",
            "R divide Q",
            "Q-factor",
            "shunt impedance",
            "voltage",
            "total loss",
        ]
        self.dimension_input = len(self.input_name)
        self.dimension_output = len(self.output_name)

        # encoding
        self.bound = [
            [250, 280],
            [0, 125],
            [0, 125],
            [214, 254],
            [32, 33],
            [32, 33],
            [0, 40],
            [0, 15],
            [0, 15],
            [0, 25],
            [0, 25],
            [0, 100],
            [0, 100],
        ]

        # judge if end
        self.count = 0
        self.end_num = 5

        # choose number
        self.choose_num = 30  # less than 1/2*self.generation_num

    def find_line_end(self, ends):  # 返回下一行开头
        i = 0
        while ends[i] != "\n":
            i += 1
        return i + 1

    def get_y_start_position(self, ends):
        i = 0
        while ends[i] == "[":
            i += 1
        return i

    def get_y_len(self, ends):  # 得到当前数字的长度
        i = 0
        while (ends[i] == "\t" or ends[i] == "," or ends[i] == ")") == False:
            i += 1
        return i

    def get_nonsense_len(self, ends):
        i = 0
        #       print(ends[:10])
        while (
            ends[i] == " "
            or ends[i] == ","
            or ends[i] == "\t"
            or ends[i] == "]"
            or ends[i] == "["
            or ends[i] == "("
        ):
            i += 1
        return i

    def LHSample(self):
        bounds = []
        delta = []

        bounds = self.bound
        dimension = len(bounds)
        print("LHSample,x0", bounds)
        point_num = self.generation_num

        for i in bounds:
            # bounds.append([i*98/100,i*102/100])
            delta.append((i[0] - i[1]) / point_num)

        result = np.empty([point_num, dimension])
        temp = np.empty([point_num])
        d = 1.0 / point_num

        for i in range(dimension):
            for j in range(point_num):
                temp[j] = np.random.uniform(low=j * d, high=(j + 1) * d, size=1)[0]

            np.random.shuffle(temp)

            for j in range(point_num):
                result[j, i] = temp[j]

        print("LHSample result:", result)
        # 对样本数据进行拉伸
        b = np.array(bounds)
        lower_bounds = b[:, 0]
        upper_bounds = b[:, 1]
        # print(lower_bounds)
        # print(upper_bounds)
        if np.any(lower_bounds > upper_bounds):
            print("范围出错")
            return None

        #   sample * (upper_bound - lower_bound) + lower_bound
        np.add(
            np.multiply(result, (upper_bounds - lower_bounds), out=result),
            lower_bounds,
            out=result,
        )

        # x0 = np.append(np.full((len(result), 1), 44.5), result, axis=1)
        # x2 = np.append(x0, np.full((len(result), 1), 267.5), axis=1)
        # x3 = np.append(x2, np.full((len(result), 1), 381.5), axis=1)

        return result

    def get_pramater(self, location):
        f = open(location)
        print(location)
        ends = f.read()
        # print(ends)
        len_text = len(ends)
        print(len_text)

        X_mean = []
        X_std = []
        Y_mean = []
        Y_std = []

        present_position_start = 0
        while present_position_start < len_text - 1:
            delta_len = self.find_line_end(
                ends[present_position_start:]
            )  # 找到这一行的终止位置（判断换行符）
            present_position_end = present_position_start + delta_len  # 得到每一行的结尾
            string = ends[present_position_start:present_position_end]
            print("----" + string)

            if "X_mean" in string:
                present_position_start = present_position_end
                delta_len = self.find_line_end(
                    ends[present_position_start:]
                )  # 找到这一行的终止位置（判断换行符）
                present_position_end = present_position_start + delta_len
                while delta_len < 2:
                    present_position_start = present_position_end
                    delta_len = self.find_line_end(
                        ends[present_position_start:]
                    )  # 找到这一行的终止位置（判断换行符）
                    present_position_end = present_position_start + delta_len
                print(ends[present_position_start : present_position_end - 1])
                x_mean = []
                for i in ends[
                    present_position_start : present_position_end - 1
                ].split():
                    # print(i)
                    try:
                        x_mean.append(float(i))
                        print(float(i))
                    except:
                        try:
                            x_mean.append(float(i[1:]))
                            print(float(i[1:]))
                        except:
                            x_mean.append(float(i[:-1]))
                            print(float(i[:-1]))
                X_mean = np.array(x_mean)
                print("X_mean ", X_mean)

            if "X_std" in string:

                present_position_start = present_position_end
                delta_len = self.find_line_end(
                    ends[present_position_start:]
                )  # 找到这一行的终止位置（判断换行符）
                present_position_end = present_position_start + delta_len
                while delta_len < 2:
                    present_position_start = present_position_end
                    delta_len = self.find_line_end(
                        ends[present_position_start:]
                    )  # 找到这一行的终止位置（判断换行符）
                    present_position_end = present_position_start + delta_len
                x_std = []
                for i in ends[
                    present_position_start : present_position_end - 1
                ].split():
                    try:
                        x_std.append(float(i))
                        print(float(i))
                    except:
                        try:
                            x_std.append(float(i[1:]))
                            print(float(i[1:]))
                        except:
                            x_std.append(float(i[:-1]))
                            print(float(i[:-1]))
                X_std = np.array(x_std)

                print("X_std ", X_std)

            if "Y_mean" in string:
                present_position_start = present_position_end
                delta_len = self.find_line_end(
                    ends[present_position_start:]
                )  # 找到这一行的终止位置（判断换行符）
                present_position_end = present_position_start + delta_len
                # print(ends[present_position_start:present_position_end])
                while delta_len < 2:
                    present_position_start = present_position_end
                    delta_len = self.find_line_end(
                        ends[present_position_start:]
                    )  # 找到这一行的终止位置（判断换行符）
                    present_position_end = present_position_start + delta_len
                    # print(ends[present_position_start:present_position_end])
                y_mean = []
                for i in ends[
                    present_position_start : present_position_end - 1
                ].split():
                    try:
                        y_mean.append(float(i))
                        print(float(i))
                    except:
                        try:
                            y_mean.append(float(i[1:]))
                            print(float(i[1:]))
                        except:
                            y_mean.append(float(i[:-1]))
                            print(float(i[:-1]))
                Y_mean = np.array(y_mean)

                print("Y_mean ", Y_mean)

            if "Y_std" in string:
                present_position_start = present_position_end
                delta_len = self.find_line_end(
                    ends[present_position_start:]
                )  # 找到这一行的终止位置（判断换行符）
                present_position_end = present_position_start + delta_len
                while delta_len < 2:
                    present_position_start = present_position_end
                    delta_len = self.find_line_end(
                        ends[present_position_start:]
                    )  # 找到这一行的终止位置（判断换行符）
                    present_position_end = present_position_start + delta_len
                y_std = []
                for i in ends[
                    present_position_start : present_position_end - 1
                ].split():
                    try:
                        y_std.append(float(i))
                        print(float(i))
                    except:
                        try:
                            y_std.append(float(i[1:]))
                            print(float(i[1:]))
                        except:
                            y_std.append(float(i[:-1]))
                            print(float(i[:-1]))
                Y_std = np.array(y_std)

                print("Y_std ", Y_std)
            # print(present_position_start)
            present_position_start = present_position_end

        # if Y_std==0 or X_mean==0 or X_std==0 or Y_mean==0:
        # print("wrong!!!!!")

        return X_mean, X_std, Y_mean, Y_std

    def set_round(self, x):
        x_after_set = []
        num = 14
        for x0 in x:
            # x_after_set.append(Decimal(x0))
            x_after_set.append(x0)
            # self.write_end(Decimal(x0), x0, "temp")

        return x_after_set

    def get_y_trans_r_aprallel(self, xs, run_count):

        nor = self.state_y0
        print("nor:", nor)
        r = []
        y = []

        x_temp = []
        for x in xs:
            x_temp.append(self.set_round(x))
        xs = x_temp

        for j, x in enumerate(xs):
            self.w.addTask(self.input_name, x, str(run_count) + str(j))

        self.w.start()
        self.w.synchronize()  # 同步 很重要
        rg = self.w.getFullResults()
        ###SORT RESULTS

        rg = sorted(rg, key=lambda x: int(x["name"][10:]))

        for irg in rg:
            print(irg["name"])
            y.append(irg["value"])
            r.append(self.yFunc.Y(irg["value"], nor))

        print("y", y)
        print("r", r)

        if len(r) == 1:
            return y[0], r[0]
        else:
            return np.append(
                np.array(r).reshape(self.generation_num, 1),
                np.array(y).reshape(self.generation_num, self.dimension_output - 1),
                axis=1,
            )

    def write_end(self, x, r, save_name):
        exists = False
        # new_context = str(r)+"\t"+str(x)+"\r\n"

        txtName = self.location + self.relative_location + save_name + ".txt"
        # new_context = str(r)+"--------"+str(x)+"\r\n"
        with open(txtName, "a+") as f:
            f.write(str(r) + "\n")
            for i_s in x:
                for i in i_s:
                    f.write(str(i) + "\t")
                f.write("\n")
            print("write_end good!")

    def random_int_list(self, start, stop, length):
        start, stop = (
            (int(start), int(stop)) if start <= stop else (int(stop), int(start))
        )
        length = int(abs(length)) if length else 0
        random_list = []
        for i in range(length):
            random_list.append(random.randint(start, stop))
        return random_list

    def calculate_output(self, x, name):
        # x = x[:,1:]
        print("x is :", x)
        # model_rough = load_model('my_model_112103.h5')
        # X_mean, X_std, Y_mean, Y_std = self.get_pramater('log_112103.txt')

        # y = np.array(model_rough.predict([(x-X_mean)/X_std])).reshape(self.dimension_output,self.generation_num).T * Y_std + Y_mean
        y = self.get_y_trans_r_aprallel(x, name + str(1000000 + self.count)[1:] + "_")

        return y

    def get_output(self, samples, name):
        x = np.array(samples)

        # fitness_values = np.zeros((self.generation_num, self.dimension_output))
        # for j in range(self.generation_num):
        # fitness_values[j,:] = self.calculate_output(x[j,1:])
        fitness_values = self.calculate_output(x, name)

        for i in range(self.dimension_output):
            samples[self.output_name[i]] = fitness_values[:, i]
        #         np.append(fitness_values, x, axis=1)
        #         print(samples)
        return samples

    def produce_sample(self):
        # 在字典中赋值
        # x = np.zeros((self.generation_num, self.dimension_input))
        # for i in range(self.dimension_input):
        # x[:,i] = self.random_int_list(self.bound[i][0], self.bound[i][1], self.generation_num)
        x = self.LHSample()

        samples = pd.DataFrame(x)
        samples.columns = self.input_name
        samples = self.get_output(samples, "NEW")
        self.write_many("produce_sample", samples)

        return samples

    def get_sorted(self, samples_fresh):
        samples_fresh["nearest_to_500M"] = abs(
            np.array(samples_fresh["frequent"]) - 499.65
        )
        samples_sorted = samples_fresh.sort_values(
            by="nearest_to_500M", ascending=True
        ).head(self.generation_num * 2)
        # self.write_many("samples_sorted_nearest_to_500M", samples_sorted)
        samples_sorted = samples_sorted.sort_values(
            by="shunt impedance", ascending=False
        ).head(self.generation_num)
        # self.write_many("samples_sorted_nearest_to_500M", samples_sorted)
        return samples_sorted.drop(["nearest_to_500M"], 1)

    def get_p_variated(self, samples_fitted):
        p_variated = []
        for i in range(self.generation_num):
            p_variated.append(
                1
                - np.float(samples_fitted["fitness"].iloc[i])
                / np.sum(np.array(samples_fitted["fitness"]))
            )
        samples_fitted["p_variated"] = np.array(p_variated).reshape(
            self.generation_num, 1
        )

        return samples_fitted

    def get_samples_new_parameter(self, input_samples):
        #         print("input_samples\n",input_samples)
        samples_new_parameter = np.zeros(self.dimension_input)
        bound = np.zeros((self.dimension_input, 2))
        for i in range(self.dimension_input):
            #             print(input_samples[:,i])
            min_number = min(input_samples[:, i])
            max_number = max(input_samples[:, i])
            bound[i, 0] = min_number
            bound[i, 1] = max_number
        #         print("bound:\n",bound)

        for i in range(self.dimension_input):
            #             print(i)
            #             print(self.bound[i][1], self.bound[i][0])
            samples_new_parameter[i] = (
                random.random() * (bound[i, 1] - bound[i, 0]) + bound[i, 0]
            )

        return samples_new_parameter

    def real_num_encoding(self, samples_fresh):  # x=a+y(b-a)
        samples_input_value = np.array(samples_fresh.iloc[:, self.dimension_output :])
        #         print(samples_input_value.shape)

        bound = np.array(self.bound).reshape(self.dimension_input, 2)
        #         print("bound is: \n",bound)
        samples_encoded = (samples_input_value - bound[:, 0]) / (
            bound[:, 1] - bound[:, 0]
        )
        #         print("samples_encoded is: ",samples_encoded.shape,"\n",samples_encoded)

        return samples_encoded

    def get_choosed_sample(self, random_num, samples_fitted):
        i = 0
        while random_num > samples_fitted[i]:
            i += 1
            if i >= self.generation_num:
                print("warning!!!!", i)
                break
        #         print(i, random_num, samples_fitted)
        return i

    def get_next_generation(
        self, samples_choosed, samples_inheritanced, samples_variated
    ):
        samples_all = pd.concat(
            [samples_choosed, samples_inheritanced, samples_variated]
        )
        #         print("======================\n",samples_inheritanced)

        samples_all = samples_all.drop_duplicates(keep="first").reset_index(drop=True)
        #         print("======================\n",samples_all)
        samples_sorted = self.get_sorted(samples_all)
        #         print("YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY:\n",samples_sorted)
        samples_fitted = (
            self.get_fitness(samples_sorted)
            .reset_index(drop=True)
            .drop(["p_choosed", "fitness"], 1)
        )
        #         print("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n",samples_fitted)
        self.write_many("produce_sample", samples_fitted)
        return samples_fitted

    def judge_end(self, samples_fresh):
        self.count += 1
        if self.count > self.end_num:  # samples_fresh[0].all < 0.001:
            samples_sorted = self.get_sorted(samples_fresh).head(5)
            print("the best 5 sample is:\n", samples_sorted)
            self.write_many("the_best", samples_sorted)
            self.write_end(
                np.array(samples_sorted), self.output_name, "the_best_sample"
            )
            return False
        else:
            #             print(self.count)

            return True

    def variate(self, samples_fresh):
        # print("============================\n",samples_fresh)
        samples_sorted = self.get_sorted(samples_fresh)
        samples_fitted = self.get_fitness(samples_sorted)
        samples_fitted = self.get_p_variated(samples_fitted)

        #         print(samples_fitted)
        #         print(samples_new_parameter)

        for i in range(self.generation_num):
            p = random.random()
            #             print("p is :",p)
            if p < np.float(samples_fitted.loc[i, ["p_variated"]]):
                #                 print(np.array(samples_fresh[self.input_name]))
                samples_new_parameter = self.get_samples_new_parameter(
                    np.array(samples_fresh[self.input_name])
                )
                for j in range(len(samples_new_parameter)):
                    samples_fitted.loc[i, self.input_name[j]] = samples_new_parameter[j]
                # print(samples_new_parameter)

        output = self.calculate_output(np.array(samples_fitted[self.input_name]), "VAR")
        samples_fitted[self.output_name] = output
        # for j in range(len(output)):
        # samples_fitted.loc[i,self.output_name[j]] = output[j]

        samples_sorted = self.get_sorted(samples_fitted)
        samples_fitted = self.get_fitness(samples_sorted).drop(
            ["p_choosed", "fitness", "p_variated"], 1
        )
        #         print(samples_fitted)
        self.write_many("samples_variated", samples_fitted)
        return samples_fitted

    def choose(self, samples_fresh):
        samples_sorted = self.get_sorted(samples_fresh)
        samples_fitted = self.get_fitness(samples_sorted)
        #         print("----samples_fitted\n",samples_fitted)

        # choose
        #         print(samples_fitted)
        samples_choosed = []
        for i in range(self.generation_num - 5):
            num = self.get_choosed_sample(
                random.random(),
                np.array(samples_fitted["p_choosed"]).reshape(self.generation_num,),
            )
            #             print(num)
            samples_choosed.append(samples_fitted.iloc[num])
        for i in range(5):  # best!
            samples_choosed.append(samples_fitted.iloc[i])
        samples_choosed = pd.DataFrame(samples_choosed)

        try:
            samples_choosed = samples_choosed.drop(
                ["p_choosed", "fitness", "p_variated"], 1
            )
        except:
            samples_choosed = samples_choosed.drop(["p_choosed", "fitness"], 1)
        #         print(samples_choosed)
        self.write_many("samples_choosed", samples_choosed)
        return samples_choosed

    def get_fitness(self, samples_sorted):
        #         print(samples_sorted)
        output_value = np.array(samples_sorted[self.output_name]).reshape(
            self.generation_num, self.dimension_output
        )[:, 0]
        #         print(output_value)
        fitness = 1 / output_value
        samples_sorted["fitness"] = fitness
        #         print(fitness.shape)

        # add p
        p_choosed = []
        p_choosed.append(
            np.float(samples_sorted["fitness"].iloc[0])
            / np.sum(np.array(samples_sorted["fitness"]))
        )
        #         print(np.sum(np.array(samples_fitted["fitness"].iloc[0])), np.sum(np.array(samples_fitted["fitness"].iloc[1])), np.sum(np.array(samples_fitted["fitness"].iloc[:2])))
        for i in range(1, self.generation_num):
            p_choosed.append(
                np.sum(np.array(samples_sorted["fitness"].iloc[: i + 1]))
                / np.sum(np.array(samples_sorted["fitness"]))
            )
        samples_sorted["p_choosed"] = np.array(p_choosed).reshape(
            self.generation_num, 1
        )
        #         print(samples_sorted)

        return samples_sorted

    def inheritance(self, samples_fresh):  # intermediate recombination
        #         print(samples_fresh)
        samples_sorted = self.get_sorted(samples_fresh)
        samples_fitted = self.get_fitness(samples_sorted)
        son = pd.DataFrame(columns=tuple(self.input_name))

        for i in range(self.generation_num):
            u1 = random.random()
            u2 = random.random()
            u3 = random.random()
            father = random.randint(0, self.generation_num - 1)
            mother = random.randint(0, self.generation_num - 1)
            son_input = self.get_son(u1, u2, u3, father, mother, samples_fitted)
            # print(son_input.to_dict())
            son = son.append([son_input.to_dict()], ignore_index=True)

        # print("samples_fitted\n",son.columns,"\n",son)
        output = self.calculate_output(np.array(son[self.input_name]), "INH")
        son[self.output_name] = output
        son = son.drop(["p_choosed", "fitness"], 1)
        self.write_many("samples_inheritanced", son)
        return son

    def get_son(self, u1, u2, u3, father, mother, samples_choosed):
        #         print(samples_choosed.shape)
        #         u1*samples_choosed[father,:]+(1-u1)samples_choosed[mother,:]
        #         print(u1, u2, u3, father, mother)
        #         print(samples_choosed[father,:])
        #         print(samples_choosed[mother,:])
        if u3 < 0.5:
            sample_new = (
                u1 * samples_choosed.loc[father]
                + (1 - u1) * samples_choosed.loc[mother]
            )
        else:
            sample_new = (
                u2 * samples_choosed.loc[father]
                + (1 - u2) * samples_choosed.loc[mother]
            )
        return sample_new

    def write_many(self, title, data):
        #         print("data\n",data)
        #         print(os.getcwd()) #获取当前工作路径

        name = (
            self.location
            + self.relative_location
            + "picture\\"
            + title
            + "_"
            + str(self.count)
            + ".csv"
        )
        #         print("name:",name)
        data.to_csv(name, index=True, sep=",")

    def start(self):
        start_time = time.time()
        self.state_y0 = np.array(
            self.w.runWithParam(self.input_name, self.state_x0, "normal_result")
        )
        samples_fresh = self.produce_sample()
        #         samples_encoded = self.real_num_encoding(samples_fresh)
        #         print(samples_fresh[0])

        while self.judge_end(samples_fresh):
            print("samples_fresh:\n")
            #             print("samples_fitted:\n",samples_fitted)
            samples_choosed = self.choose(samples_fresh)
            print("samples_choosed:\n")

            samples_inheritanced = self.inheritance(samples_fresh)
            print("samples_inheritanced:\n")

            samples_variated = self.variate(samples_fresh)
            print("samples_variated:\n")

            samples_fresh = self.get_next_generation(
                samples_choosed, samples_inheritanced, samples_variated
            )
            # print("samples_fresh::\n",samples_fresh)

        end_time = time.time()
        print(start_time - end_time)

