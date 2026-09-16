import json


##判断是否为数字
def is_number(s):
    try:  # 如果能运行float(s)语句，返回True（字符串s是浮点数）
        float(s)
        return True
    except (TypeError, ValueError):  # 不是数字或无法转换为数字
        pass  # 如果引发了ValueError这种异常，不做任何事情（pass：不做任何事情，一般用做占位语句）
    try:
        import unicodedata  # 处理ASCii码的包

        for i in s:
            unicodedata.numeric(i)  # 把一个表示数字的字符串转换为浮点数返回的函数
            # return True
        return True
    except (TypeError, ValueError):
        pass
    return False


##从生成的ascii文件得到参数列表
def custom_ascii_2_json(asciipath, savejsonpath):
    paramslist = []
    par = open(asciipath, "r")
    lines = par.readlines()
    totalparams = int(lines[2])
    for N in range(totalparams):
        linesN = lines[3 + N]
        words = linesN.split()
        paramname = words[1]
        paramvalue = words[2]
        paramdescript = ""
        if len(words) >= 4:
            paramdescript = words[3]
        ##推断类型
        paramtype = "double"
        if not is_number(paramvalue):
            paramtype = "expression"
        dictw = {}
        dictw["id"] = N
        dictw["name"] = paramname
        dictw["value"] = paramvalue
        dictw["type"] = paramtype
        if paramtype == "double":
            dictw["fixed"] = False
        else:
            dictw["fixed"] = True
        dictw["description"] = paramdescript

        paramslist.append(dictw)

    par.close()
    fp = open(savejsonpath, "w")
    json.dump(paramslist, fp=fp,indent=4)
    fp.close()
    pass


def getParamsList(jsonpath):
    paramfile = jsonpath
    f = open(paramfile, "r")
    pamlist = json.load(f)
    f.close()
    return pamlist


def convert_cst_parameters_to_legacy(cst_parameters):
    """Convert ``Model/Parameters.json`` records to the legacy params schema.

    CST stores the source expression (``expr``) separately from its current
    evaluated result (``value``).  The legacy VB path used
    ``GetParameterSValue``, so its ``value`` field actually contained the
    expression.  Preserve that behavior while retaining both modern fields.
    """
    result = []
    seen = set()
    for index, parameter in enumerate(cst_parameters):
        name = str(parameter.get("name", ""))
        if not name:
            raise ValueError("CST parameter at index %d has no name" % index)
        if name in seen:
            raise ValueError("duplicate CST parameter name: %s" % name)
        seen.add(name)
        expression = str(parameter.get("expr", ""))
        evaluated_value = str(parameter.get("value", ""))
        legacy_value = expression if expression.strip() else evaluated_value
        literal = is_number(legacy_value)
        result.append({
            "id": index,
            "name": name,
            "value": legacy_value,
            "type": "double" if literal else "expression",
            "fixed": not literal,
            "description": str(parameter.get("descr", "") or ""),
            "expr": expression,
            "evaluated_value": evaluated_value,
        })
    return result


def convert_json_params_to_list(json_dict_list):
    result_x_list = []
    for i in range(len(json_dict_list)):
        if json_dict_list[i]["fixed"] == False:
            result_x_list.append(float(json_dict_list[i]["value"]))
    return result_x_list


def resort_helper():
    pass
