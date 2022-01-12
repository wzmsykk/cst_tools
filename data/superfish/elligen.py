from math import atan,tan,sin,cos,pi
#### Create Boundary Points Command Lines for SF
def createLineCmd(st,ed):    
    x0,y0=st
    x1,y1=ed
    str0=r"&PO X=%f,Y=%f &" % (float(x0),float(y0))
    str1=r"&PO X=%f,Y=%f &" % (float(x1),float(y1))
    lines=[]
    lines.append(str0)
    lines.append(str1)
    return lines
def addPointCmd(pnt):
    x0,y0=pnt
    str0=r"&PO X=%f,Y=%f &" % (float(x0),float(y0))
    lines=[]
    lines.append(str0)
    return lines
def createArcEndPCmd(radius,centor,ed): 
    #The start point of the arc should be defined before this cmdline.
    x0,y0=centor
    x1,y1=ed
    offsetx=x1-x0
    offsety=y1-y0
    str0=r"&PO NT=2,X0=%f,Y0=%f," % (float(x0),float(y0))
    str1=r"X=%f,Y=%f,R=%f &" % (float(offsetx),float(offsety),float(radius))
    lines=[]
    lines.append(str0)
    lines.append(str1)
    return lines
def createArcFullCmd(radius,centor,st,ed):
    xs,ys=st
    x0,y0=centor
    x1,y1=ed
    offsetx=x1-x0
    offsety=y1-y0
    strs=r"&PO X=%f,Y=%f &" % (float(xs),float(ys))
    str0=r"&PO NT=2,X0=%f,Y0=%f," % (float(x0),float(y0))
    str1=r"X=%f,Y=%f,R=%f &" % (float(offsetx),float(offsety),float(radius))
    lines=[]
    lines.append(strs)
    lines.append(str0)
    lines.append(str1)
    return lines
def createEllipseArcEndPCmd(A,B,centor,ed):
    #The start point of the arc should be defined before this cmdline.
    x0,y0=centor
    x1,y1=ed
    offsetx=x1-x0
    offsety=y1-y0
    str0=r"&PO NT=2,X0=%f,Y0=%f," % (float(x0),float(y0))
    str1=r"A=%f,AOVRB=%f," % (float(A),float(A/B))
    str2=r"X=%f,Y=%f &" % (float(offsetx),float(offsety))
    lines=[]
    lines.append(str0)
    lines.append(str1)
    lines.append(str2)
    return lines
def createEllipseArcFullCmd(A,B,centor,st,ed):
    xs,ys=st
    x0,y0=centor
    x1,y1=ed
    offsetx=x1-x0
    offsety=y1-y0
    strs=r"&PO X=%f,Y=%f &" % (float(xs),float(ys))
    str0=r"&PO NT=2,X0=%f,Y0=%f," % (float(x0),float(y0))
    str1=r"A=%f,B=%f," % (float(A),float(B))
    str2=r"X=%f,Y=%f &" % (float(offsetx),float(offsety))
    lines=[]
    lines.append(strs)
    lines.append(str0)
    lines.append(str1)
    lines.append(str2)
    return lines
def newPointByOffset(pt,offsets):
    x0,y0=pt
    xoffset,yoffset=offsets
    np=(x0+xoffset,y0+yoffset)
    return np
def get_left(indict):

    rx1 = indict["a4"]
    ry1 = indict["b4"]
    rx2 = indict["a1"]
    ry2 = indict["b1"]
    xlen2 = indict["D2_l"]
    r1 = indict["R_SBP"]
    r2 = indict["Req"]

    d_alf = 1
    cst_alf = 0
    cst_angle_step = 0.2
    cst_alf1 = 0
    cst_alf2 = 0
    if rx1+rx2<xlen2:
        while cst_alf!=90 and d_alf>0:#两边找切线的角度，cst_alf是切线的角度
            cst_alf = cst_alf+cst_angle_step
            cst_alf1 = cst_alf/180*pi
            cst_slop1=ry1/rx1*tan(cst_alf1)
            cst_alf2=atan(cst_slop1*rx2/ry2)
            cst_slop2=((r2-ry2*(1-cos(cst_alf2)))-(r1+ry1*(1-cos(cst_alf1))))/((xlen2-rx2*sin(cst_alf2))-rx1*sin(cst_alf1))
            d_alf=atan(cst_slop2)-atan(cst_slop1)
            print("d_alf:",d_alf,";cst_alf:",cst_alf)
        
    elif rx1+rx2==xlen2:
        cst_alf1=90/180*pi
        cst_alf2=90/180*pi
    else:
        cst_alf=90
        while d_alf>0 and cst_alf!=180:
            cst_alf =cst_alf+cst_angle_step
            cst_alf1=cst_alf/180*pi
            cst_slop1=ry1/rx1*tan(cst_alf1)
            cst_alf2=atan(cst_slop1*rx2/ry2)*180/pi+180/180*pi
            cst_slop2=((r2-ry2*(1-cos(cst_alf2)))-(r1+ry1*(1-cos(cst_alf1))))/((xlen2-rx2*sin(cst_alf2))-rx1*sin(cst_alf1))
            d_alf=atan(cst_slop2)-atan(cst_slop1)

    ###'Now: calculate the length of the linear part to get the number of points in there.
    ###'Start point of the linear part
    cst_lin_x1 = rx1*sin(cst_alf1)
    cst_lin_y1 = r1+ry1*(1-cos(cst_alf1))
    ###'End point of the linear part
    cst_lin_x2 = xlen2-rx2*sin(cst_alf2)
    cst_lin_y2 = r2-ry2*(1-cos(cst_alf2))

    
    return (cst_lin_x1, cst_lin_y1), (cst_lin_x2, cst_lin_y2)
    
def get_right(indict):
    rx1 = indict["a3"]
    ry1 = indict["b3"]
    rx2 = indict["a1"]
    ry2 = indict["b1"]
    xlen2 = indict["D2_r"]
    r1 = indict["R_SBP"]
    r2 = indict["Req"]

    d_alf = 1
    cst_alf = 0
    cst_angle_step = 0.2
    cst_alf1 = 0
    cst_alf2 = 0
    if rx1+rx2<xlen2:
        while cst_alf!=90 and d_alf>0:#两边找切线的角度，cst_alf是切线的角度
            cst_alf = cst_alf+cst_angle_step
            cst_alf1 = cst_alf/180*pi
            cst_slop1=ry1/rx1*tan(cst_alf1)
            cst_alf2=atan(cst_slop1*rx2/ry2)
            cst_slop2=((r2-ry2*(1-cos(cst_alf2)))-(r1+ry1*(1-cos(cst_alf1))))/((xlen2-rx2*sin(cst_alf2))-rx1*sin(cst_alf1))
            d_alf=atan(cst_slop2)-atan(cst_slop1)
            print("d_alf:",d_alf,";cst_alf:",cst_alf)
        
    elif rx1+rx2==xlen2:
        cst_alf1=90/180*pi
        cst_alf2=90/180*pi
    else:
        cst_alf=90
        while d_alf>0 and cst_alf!=180:
            cst_alf =cst_alf+cst_angle_step
            cst_alf1=cst_alf/180*pi
            cst_slop1=ry1/rx1*tan(cst_alf1)
            cst_alf2=atan(cst_slop1*rx2/ry2)*180/pi+180/180*pi
            cst_slop2=((r2-ry2*(1-cos(cst_alf2)))-(r1+ry1*(1-cos(cst_alf1))))/((xlen2-rx2*sin(cst_alf2))-rx1*sin(cst_alf1))
            d_alf=atan(cst_slop2)-atan(cst_slop1)

    ###'Now: calculate the length of the linear part to get the number of points in there.
    ###'Start point of the linear part
    cst_lin_x1 = rx1*sin(cst_alf1)
    cst_lin_y1 = r1+ry1*(1-cos(cst_alf1))
    ###'End point of the linear part
    cst_lin_x2 = xlen2-rx2*sin(cst_alf2)
    cst_lin_y2 = r2-ry2*(1-cos(cst_alf2))

    return (-cst_lin_x2+xlen2, cst_lin_y2), (-cst_lin_x1+xlen2, cst_lin_y1)
    #return (-1)*np.array([cst_lin_x2, cst_lin_x1])+xlen2, np.array([cst_lin_y2, cst_lin_y1])

sample_input_name = {"R_SBP":110, "R_LBP":150, "Req":262.83, "Leq":266.24, 
              "D2_r":115.02, "D2_l":115.02, "b1":64.936, "a1":64.936, 
              "b3":80, "a3":27.5, "b4":80, "a4":27.5, "r2":30, "r1":30, "H":10.85, "D1":58.43}
class CustomCavParams:
    def __init__(self) -> None:
        self.R_SBP=110
        self.R_LBP=150
        self.Req=262.83
        self.Leq=266.24
        self.D2_r=115.02
        self.D2_l=115.02
        self.b1=64.936
        self.a1=64.936
        self.b3=80
        self.a3=27.5
        self.b4=80
        self.a4=27.5
        self.r2=30
        self.H=10.85
        self.D1=58.43
    @classmethod
    def by_dict(cls,dict:dict):
        icls=cls()
        for key,value in dict.items():
            icls.__setattr__(key,value)
        return icls
def myCustomCavity(indict):
    vertexs=[]
    cmdlines=[]
    circles=[]
    ellipses=[]
    mycp=CustomCavParams.by_dict(indict)

    #### Start Point P0
    x0=(-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H-mycp.D1-mycp.R_LBP*2)
    y0=0
    vt=(x0,y0)
    vertexs.append(vt) 
    lines=addPointCmd(vt)
    cmdlines+=lines

    #### P1 Left Tube End
    yt=mycp.R_LBP
    p1=(x0,yt)
    vertexs.append(p1)
    lines=addPointCmd(p1) 
    cmdlines+=lines

    #### P2 Circle ARC C1 Start Point
    alpha1 = atan((mycp.R_LBP - mycp.R_SBP) / mycp.D1)
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H-mycp.D1-mycp.r1*tan(alpha1/2)
    y0=mycp.R_LBP
    p2=(x0,y0)
    vertexs.append(p2)  ##P2
    lines=addPointCmd(p2)
    cmdlines+=lines

    #### P3 Circle ARC C1 End Point    
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H-mycp.D1-mycp.r1*tan(alpha1/2)
    y0=mycp.R_LBP-mycp.r1
    c1_centor=(x0,y0)
    r=mycp.r1
    circles.append((c1_centor,r))
    xt=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H-mycp.D1 + mycp.r1*tan(alpha1/2)*cos(alpha1)
    yt=mycp.R_LBP - mycp.r1*tan(alpha1/2)*sin(alpha1)
    p3=(xt,yt)
    vertexs.append(p3)
    lines=createArcEndPCmd(r,c1_centor,p3) 
    cmdlines+=lines

    #### P4 Circle ARC C2 Start Point
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H-mycp.r2*tan(alpha1/2)*cos(alpha1)
    y0=mycp.R_SBP + mycp.r2*tan(alpha1/2)*sin(alpha1)
    p4=(x0,y0)
    vertexs.append(p4)
    lines=addPointCmd(p4) 
    cmdlines+=lines

    #### P5 Circle ARC C2 End Point
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H+mycp.r2*tan(alpha1/2)
    y0=mycp.R_SBP+mycp.r2
    c2_centor=(x0,y0)
    r=mycp.r2
    circles.append((c2_centor,r))

    xt=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l-mycp.H+mycp.r2*tan(alpha1/2)
    yt=mycp.R_SBP
    p5=(xt,yt)
    vertexs.append(p5)
    lines=createArcEndPCmd(r,c2_centor,p5) 
    cmdlines+=lines

    #### P6 Epllise Arc E1 Start Point    
    xt=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l
    yt=mycp.R_SBP
    p6=(xt,yt)
    vertexs.append(p6)
    lines=addPointCmd(p6) 
    cmdlines+=lines

    #### Find LEFT Tangent Line T1 For CAV where LTP1 Serves As the End Point of Epllise Arc E1, LTP2 Serves As the Start Point of Epllise Arc E2
    tp1,tp2 = get_left(indict)
    xoffset=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2-mycp.D2_l
    ltp1=newPointByOffset(tp1,(xoffset,0))
    ltp2=newPointByOffset(tp2,(xoffset,0))
    vertexs.append(ltp1)
    vertexs.append(ltp2)

    ######## CMDLine For T1
    a=mycp.a3
    b=mycp.b3
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2 - mycp.D2_l
    y0=mycp.R_SBP+mycp.b3
    e1_centor=(x0,y0)
    ellipses.append((e1_centor,a,b))
    lines=createEllipseArcEndPCmd(a,b,e1_centor,ltp1) 
    cmdlines+=lines
    lines=addPointCmd(ltp2) 
    cmdlines+=lines

    #### P7 Epllise Arc E2 End Point
    a=mycp.a1
    b=mycp.b1
    x0=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2
    y0=mycp.Req-mycp.b1
    e2_centor=(x0,y0)
    ellipses.append((e2_centor,a,b))
    xt=-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2
    yt=mycp.Req
    p7=(xt,yt)
    vertexs.append(p7)
    lines=createEllipseArcEndPCmd(a,b,e2_centor,p7) 
    cmdlines+=lines

    #### P8 Epllise Arc E3 Start Point
    xt=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2
    yt=mycp.Req
    p8=(xt,yt)
    vertexs.append(p8)
    lines=addPointCmd(p8) 
    cmdlines+=lines

    #### Find RIGHT Tangent Line T2 For CAV where RTP1 Serves As the End Point of Epllise Arc E3, RTP2 Serves As the Start Point of Epllise Arc E4
    tp1,tp2 = get_right(indict)
    xoffset=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2
    rtp1=newPointByOffset(tp1,(xoffset,0))
    rtp2=newPointByOffset(tp2,(xoffset,0))
    vertexs.append(rtp1)
    vertexs.append(rtp2)
    ######## CMDLine For T2
    a=mycp.a1
    b=mycp.b1
    x0=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2
    y0=mycp.Req-mycp.b1
    e3_centor=(x0,y0)
    ellipses.append((e3_centor,a,b))
    lines=createEllipseArcEndPCmd(a,b,e3_centor,rtp1) 
    cmdlines+=lines
    lines=addPointCmd(rtp2) 
    cmdlines+=lines

    #### P9 Epllise Arc E4 End Point
    a=mycp.a4
    b=mycp.b4
    x0=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2 + mycp.D2_r
    y0=mycp.R_SBP+mycp.b4
    e4_centor=(x0,y0)
    ellipses.append((e4_centor,a,b))
    xt=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2+mycp.D2_r
    yt=mycp.R_SBP
    p9=(xt,yt)
    vertexs.append(p9)
    lines=createEllipseArcEndPCmd(a,b,e4_centor,p9) 
    cmdlines+=lines

    #### P10 Right Tube End
    xt=(mycp.Leq-mycp.D2_r-mycp.D2_l)/2+mycp.D2_r+mycp.R_SBP*2
    yt=mycp.R_SBP
    p10=(xt,yt)
    vertexs.append(p10)
    lines=addPointCmd(p10) 
    cmdlines+=lines

    #### P11 End Point
    p11=(xt,0)
    vertexs.append(p11)
    lines=addPointCmd(p11) 
    cmdlines+=lines

    #### Closure Command
    lines=addPointCmd(vt) 
    cmdlines+=lines

    return vertexs,cmdlines,circles,ellipses

def test():
    vertexs,cmdlines,circles,ellipses=myCustomCavity(sample_input_name)
    xlist=[]
    ylist=[]
    for vertex in vertexs:
        xcoord,ycoord=vertex
        xlist.append(xcoord)
        ylist.append(ycoord)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse, Circle
    fig = plt.figure()
    ax = fig.add_subplot(111)
    for c in circles:
        centor,r=c
        cpatch=Circle(xy=centor,radius=r,alpha=0.5)
        ax.add_patch(cpatch)
    for e in ellipses:
        centor,a,b=e
        cpatch=Ellipse(xy=centor,width=a*2,height=b*2,alpha=0.5)
        ax.add_patch(cpatch)
    plt.plot(xlist,ylist,color='b',marker='o')
    plt.axis('scaled')
    plt.show()
    print('\n')
    for line in cmdlines:
        print(line)
if __name__ =='__main__':
    test()
#     ell1 = Ellipse(xy = (-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2, mycp.Req-mycp.b1), width = mycp.a1*2, height = mycp.b1*2, angle = 0.0, facecolor= 'yellow', alpha=0.3)
# ax.add_patch(ell1)
# ell2 = Ellipse(xy = (-(mycp.Leq-mycp.D2_r-mycp.D2_l)/2 - mycp.D2_l, mycp.R_SBP+mycp.b3), width = mycp.a3*2, height = mycp.b3*2, angle = 0.0, facecolor= 'blue', alpha=0.3)
# ax.add_patch(ell2)
# ell3 = Ellipse(xy = ((mycp.Leq-mycp.D2_r-mycp.D2_l)/2, mycp.Req-mycp.b1), width = mycp.a1*2, height = mycp.b1*2, angle = 0.0, facecolor= 'yellow', alpha=0.3)
# ax.add_patch(ell3)
# ell4 = Ellipse(xy = ((mycp.Leq-mycp.D2_r-mycp.D2_l)/2 + mycp.D2_r, mycp.R_SBP+mycp.b4), width = mycp.a4*2, height = mycp.b4*2, angle = 0.0, facecolor= 'blue', alpha=0.3)
# ax.add_patch(ell4)



    

