



class function_struct_list(object):


    idList=[]
    blockList=[]

    def __init__(self):
        super().__init__()

    def create_newid(self):
        pass
        
    

class vba_file_generator(object):

    pass

def create_vb_sub_block_Curve(f_struct,curve_name=None,curve_type=None,**kwargs):
    inten_prefix="defineCurve_Sub"
    inten_id=f_struct.create_newid()
    inten_block_fullname=inten_prefix+str(inten_id)
    blocktext=[]
    blocktext.append("Sub "+inten_block_fullname)
    inten_curve_name0=None
    inten_curve_name1=None
    kwdict={}
    for k,v in kwargs.items():
        kwdict[k]=v
    if(curve_type=="Line"):
        inten_curve_name0="line_%s" % str(inten_id)
        inten_curve_name1="curve_line_%s" % str(inten_id)
        blocktext.append("With Line")
        blocktext.append(".Reset")
        blocktext.append(".Name \"%s\"" % inten_curve_name0)
        blocktext.append(".Curve \"%s\"" % inten_curve_name1)
        blocktext.append(".X1 %s" % str(kwdict["X1"]))
        blocktext.append(".Y1 %s" % str(kwdict["Y1"]))
        blocktext.append(".X2 %s" % str(kwdict["X2"]))
        blocktext.append(".Y2 %s" % str(kwdict["Y2"]))
        blocktext.append(".create")
        blocktext.append("End With")
        pass
    elif (curve_type=="Circle"):
        #X,Y,R
        inten_curve_name0="circle_%s" % str(inten_id)
        inten_curve_name1="curve_circle_%s" % str(inten_id)
        blocktext.append("With Circle")
        blocktext.append(".Reset")
        blocktext.append(".Name \"%s\"" % inten_curve_name0)
        blocktext.append(".Curve \"%s\"" % inten_curve_name1)
        blocktext.append(".Radius \"%s\"" % str(kwdict["R"]))
        blocktext.append(".Xcenter \"%s\"" % str(kwdict["X"]))
        blocktext.append(".Ycenter \"%s\"" % str(kwdict["Y"]))
        blocktext.append(".create")
        blocktext.append("End With")           

        pass
    elif (curve_type=="AnalyticalCurve"):
        inten_curve_name0="AnalyticalCurve_%s" % str(inten_id)
        inten_curve_name1="AnalyticalCurve_%s" % str(inten_id)
        blocktext.append("With AnalyticalCurve")
        blocktext.append(".Reset")
        blocktext.append(".Name \"%s\"" % inten_curve_name0)
        blocktext.append(".Curve \"%s\"" % inten_curve_name1)
        blocktext.append(".LawX \"%s\"" % str(kwdict["LawX"]))
        blocktext.append(".LawY \"%s\"" % str(kwdict["LawY"]))
        blocktext.append(".LawZ \"%s\"" % str(kwdict["LawZ"]))
        blocktext.append(".ParameterRange \"%s\", \"%s\"" % (str(kwdict["T0"]),str(kwdict["T1"])))
        blocktext.append(".create")
        blocktext.append("End With")     
    else:
        pass
    if kwdict.has_key("Transform") and not inten_curve_name0==None :
        blocktext.append("With Transform")
        blocktext.append(".Reset")
        blocktext.append(".Name \"%s:%s\"" % (inten_curve_name1,inten_curve_name0))
        blocktext.append(".Vector \"%s\",\"%s\",\"%s\"" % kwdict["Transform"])
        blocktext.append(".UsePickedPoints \"False\"")
        blocktext.append(".InvertPickedPoints \"False\"")
        blocktext.append(".MultipleObjects \"False\"")
        blocktext.append(".GroupObjects \"False\"")
        blocktext.append(".Repetitions \"1\"")
        blocktext.append(".MultipleSelection \"False\"")
        blocktext.append(".Transform \"Curve\", \"Translate\"")

    #TYPE Circle

    #TYPE AnalyticalCurve

    #TYPE Others


    ##SUB END
    blocktext.append("End Sub")

    pass
    return blocktext