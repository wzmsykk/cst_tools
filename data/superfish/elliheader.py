class SECHeaderParams:
    def __init__(self) -> None:
        #### default settings

        self.KPROB = 1  # Superfish problem
        self.MAT = 1  # Material air or empty space
        self.FREQ = 480  # Mode frequency, starting frequency in Fish solver
        self.BETA = 1  # Particle velocity, used to compute wave number if KMETHOD = 1
        self.KMETHOD = 1  # SFO will use BETA to compute wave number
        self.NBSUP = 1  # Boundary conditions
        self.NBSLO = 0  # Boundary conditions
        self.NBSRT = 0  # Boundary conditions
        self.NBSLF = 0  # Boundary conditions
        self.LINES = 1  # Fix internal points on line regions
        self.ICYLIN = 1  # X=>Z,Y=>R, cylindrical coordinates
        self.NORM = 1  # Normalize to EZEROT
        self.EZEROT = 1.0e07  # Accelerating field times T
        self.XDRI = 0  # Drive point X coordinate
        self.YDRI = 0  # Drive point Y coordinate
        self.DX = 1  # Mesh spacing in X direction
        self.DY = 1
        self.CONV = 0.1  # In mm

        ##### superconduct params
        self.SCCAV = 1  # Superconducting elliptical cavity
        self.RMASS = -2  # Rest mass value or indicator
        self.EPSO = 1.0e-6  # Mesh optimization convergence parameter
        self.IRTYPE = 1  # Rs method: Superconductor formula
        self.TEMPK = 2  # Superconductor temperature, degrees K
        self.TC = 9.2  # Critical temperature, degrees K
        self.RESIDR = 1.0e-08  # Residual resistance

        self.description = """Auto Generated Superfish File
For Superconduct Elliptical cavity.
DO NOT EDIT."""


class DummyHeaderParams:
    def __init__(self) -> None:
        pass


class SFHeaderGenerator:
    def __init__(self, dict=None) -> None:
        self.myhp = SECHeaderParams()  ###Now Superconduct Elliptical cavity

    def iniparser(self, inifile):
        ### simple parser
        regdict = {}
        with open(inifile, "r") as fp:
            lines = fp.readlines()
            reg_section_start = False
            reg_section_finish = False
            for line in lines:
                if reg_section_finish:
                    break
                if not reg_section_start:
                    if not line.upper().startswith("&REG"): ###CASE INSENSITVE MATCH
                        continue
                    else:
                        line = line[4:]  ### remove &REG
                        reg_section_start = True
                if reg_section_start:
                    t1 = line.split(";")[0]  ### remove comment

                    t2 = t1.strip()
                    if len(t2) == 0:  #### comment line
                        continue
                    if t2.endswith("&"):
                        t2 = t2.rstrip("&")
                        reg_section_finish = True
                    ### multiple kvs in one line
                    kvs = t2.split(",")
                    for ikv in kvs:

                        if len(ikv) == 0:  ### Extra commas
                            continue
                        ikv = ikv.split("=")
                        key = ikv[0].upper()
                        value = ikv[1]
                        regdict[key] = value

        return regdict

    def createHeaderFromSampleINI(self, inifile):
        self.myhp = DummyHeaderParams()
        resultdict = self.iniparser(inifile)
        self.setParams(resultdict)

    def setParams(self, dict=None):
        if dict is not None:
            for key, value in dict.items():
                self.myhp.__setattr__(key, value)

    def createHeaderLines(self):

        lines = []
        lines.append(self.myhp.description)
        lines.append("&REG")
        mems = [
            (attr, getattr(self.myhp, attr))
            for attr in dir(self.myhp)
            if (not attr.startswith("__") and (not attr == "description"))
        ]
        for name, value in mems:
            lines.append(name + "=" + str(value))
        lines.append("&")
        return lines


def test():
    sfh = SFHeaderGenerator()
    lines = sfh.createHeaderLines()
    for line in lines:
        print(line)


def parsertest():
    sfh = SFHeaderGenerator()
    result = sfh.iniparser(r"C:\Users\ykk\Desktop\superfish_test\EPCAV\epcav_cus.am")
    print(result)


if __name__ == "__main__":
    parsertest()
    # test()
